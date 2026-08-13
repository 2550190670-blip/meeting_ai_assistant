import base64
import os
import tempfile
from pathlib import Path

import httpx
from fastapi import HTTPException, UploadFile

DATA_DIR = Path(os.getenv("MEETING_DATA_DIR", Path(tempfile.gettempdir()) / "meeting_ai_assistant"))
UPLOAD_DIR = DATA_DIR / "uploads"
MAX_UPLOAD_SIZE = 20 * 1024 * 1024


async def transcribe_upload(upload: UploadFile) -> str:
    data = await upload.read()
    if not data:
        return ""
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="录音文件过大，请先上传 20MB 以内的文件。")

    saved_path = save_upload(upload.filename or "recording", data)
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="录音转文字需要配置 DASHSCOPE_API_KEY。你也可以先粘贴会议文本。")

    return await transcribe_with_qwen3(saved_path, api_key)


def resolve_local_recording(path_value: str) -> Path:
    path = Path(path_value)
    data_root = DATA_DIR.resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(data_root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="?????????") from exc
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=400, detail="????????")
    if resolved.stat().st_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="??????????? 20MB ??????")
    return resolved


async def transcribe_local_file(path_value: str) -> str:
    resolved = resolve_local_recording(path_value)
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="????????? DASHSCOPE_API_KEY?????????????")
    return await transcribe_with_qwen3(resolved, api_key)

async def transcribe_with_qwen3(path: Path, api_key: str) -> str:
    base_url = os.getenv("DASHSCOPE_COMPATIBLE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = os.getenv("DASHSCOPE_ASR_MODEL", "qwen3-asr-flash")
    audio_data = base64.b64encode(path.read_bytes()).decode("ascii")
    data_uri = f"data:{guess_mime_type(path)};base64,{audio_data}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": data_uri}},
                ],
            }
        ],
        "stream": False,
        "asr_options": {"enable_itn": True},
    }

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Qwen3 录音转文字调用失败。") from exc

    return extract_text(response.json())


def save_upload(filename: str, data: bytes) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "recording"
    path = UPLOAD_DIR / safe_name
    counter = 1
    while path.exists():
        path = UPLOAD_DIR / f"{path.stem}-{counter}{path.suffix}"
        counter += 1
    path.write_bytes(data)
    return path


def guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "video/mp4",
        ".aac": "audio/aac",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
    }.get(suffix, "application/octet-stream")


def extract_text(result: dict) -> str:
    message = result.get("choices", [{}])[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("transcript") or ""))
        return "\n".join(part for part in parts if part.strip()).strip()
    return ""
