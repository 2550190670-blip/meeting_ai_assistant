import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv(os.getenv("MEETING_ENV_FILE", Path(__file__).resolve().parents[2] / ".env"))


SYSTEM_PROMPT = """# Role: 资深活动执行策划会议助理

## Background
你是一位拥有10年以上大型线下活动、快闪店及展会执行经验的资深项目统筹。你的核心能力是能够从冗长、口语化、甚至逻辑跳跃的会议录音转写稿中，精准提取对“活动落地”至关重要的信息，并转化为结构化、可执行、高敏锐度的项目执行文档。

## Task
请仔细阅读用户提供的【会议录音转写文本】，严格按照活动执行的逻辑进行深度分析，并仅以指定的 JSON 格式输出结果。

## Workflow & Rules
1. **信息降噪**：自动过滤会议中的寒暄、重复确认、口语冗余（如“嗯”、“啊”、“那个”），只保留与活动执行相关的核心信息。
2. **执行导向**：在提取待办事项（action_items）时，必须确保每个任务都具备“可执行性”。严禁出现“跟进进度”、“后续落实”等模糊表述，必须包含“动作 + 责任人 + 截止时间”。
3. **风险敏锐度**：活动执行充满不确定性。请特别留意文本中关于“供应商交期”、“场地合规（用电/消防/报批）”、“技术稳定性（网络/设备）”、“人员及库存”等维度的隐患，将其提炼为风险点（risks）。
4. **严格推理**：所有结论必须基于原文。对于时间、人名、数字等关键信息，若原文表述模糊（如“下周三”、“大概三天”），请结合上下文进行合理推算，若无法推算，则保留原文的模糊表述，绝不可虚构。
5. **格式约束**：你的输出必须是且仅是一个合法的 JSON 对象，不要包含任何 Markdown 标记（如 ```json 等），不要有任何前置或后置的解释性文字。

## Output Format
请严格输出以下 JSON 结构：
{
  "summary": "2-4句话概括会议背景、核心结论和执行方向",
  "topics": ["关键议题1", "关键议题2"],
  "decisions": ["决策结论1", "决策结论2"],
  "action_items": [
    {
      "owner": "负责人/部门",
      "task": "具体待办事项",
      "due_date": "截止时间"
    }
  ],
  "risks": ["风险点1", "风险点2"],
  "follow_up": ["[ ] 负责人：后续跟进事项1", "[ ] 负责人：后续跟进事项2"]
}"""


async def analyze_meeting(raw_text: str) -> dict[str, Any]:
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    if dashscope_key:
        return await analyze_with_qwen3(raw_text, dashscope_key)

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return await analyze_with_openai(raw_text, openai_key)

    raise HTTPException(status_code=400, detail="未配置 DASHSCOPE_API_KEY，无法调用 Qwen 生成会议纪要。")


async def analyze_with_qwen3(raw_text: str, api_key: str) -> dict[str, Any]:
    base_url = os.getenv("DASHSCOPE_COMPATIBLE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = os.getenv("DASHSCOPE_LLM_MODEL", "qwen-plus")
    return await call_chat_json(base_url, api_key, model, raw_text)


async def analyze_with_openai(raw_text: str, api_key: str) -> dict[str, Any]:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    return await call_chat_json(base_url, api_key, model, raw_text)


async def call_chat_json(base_url: str, api_key: str, model: str, raw_text: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(raw_text)},
        ],
        "temperature": float(os.getenv("MEETING_AI_TEMPERATURE", "0.5")),
        "top_p": float(os.getenv("MEETING_AI_TOP_P", "0.6")),
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return normalize_analysis(json.loads(content))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="模型返回内容不是合法 JSON，请调整 prompt 或重试。") from exc
    except httpx.HTTPStatusError as exc:
        message = exc.response.text[:300]
        raise HTTPException(status_code=502, detail=f"Qwen 接口调用失败：{message}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"会议纪要生成失败：{exc}") from exc


def build_user_prompt(raw_text: str) -> str:
    return f"## Input\n【会议录音转写文本】：\n{raw_text}"


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": str(data.get("summary") or "暂无摘要。"),
        "topics": ensure_list(data.get("topics")),
        "decisions": ensure_list(data.get("decisions")),
        "action_items": ensure_action_items(data.get("action_items")),
        "risks": ensure_list(data.get("risks")),
        "follow_up": ensure_list(data.get("follow_up")),
    }


def ensure_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def ensure_action_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    items = []
    for item in value:
        if isinstance(item, dict):
            items.append(
                {
                    "owner": str(item.get("owner") or "待确认"),
                    "task": str(item.get("task") or ""),
                    "due_date": str(item.get("due_date") or "待确认"),
                }
            )
        else:
            items.append({"owner": "待确认", "task": str(item), "due_date": "待确认"})
    return [item for item in items if item["task"].strip()]
