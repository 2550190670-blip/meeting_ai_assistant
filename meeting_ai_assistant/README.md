# AI 会议纪要整理系统

基于 Python / FastAPI 开发的 AI 会议整理工具原型，面向活动执行策划场景，支持会议记录录入、AI 结构化总结、待办提取、风险识别、收藏、编辑、删除、文件夹管理和重新生成。

> 说明：`docs/` 是 GitHub Pages 静态展示页；完整系统包含 Python 后端、SQLite 数据库和模型 API 调用，不能直接在 GitHub Pages 上运行。

## 项目重点

- 使用 FastAPI 搭建会议整理 Web 应用。
- 使用 SQLite 保存会议、收藏状态和文件夹数据。
- 接入 DashScope / Qwen，将会议记录整理为结构化 JSON。
- 针对活动执行策划场景迭代 Prompt，重点提取负责人、截止时间、物料、供应商、场地、风险和后续跟进。
- 借助 AI Coding 完成需求拆解、代码生成、Bug 修复、交互优化和 UI 迭代。

## 本地运行

```powershell
cd C:\Files\work\Python\meeting_ai_assistant
pip install -r requirements.txt
$env:DASHSCOPE_API_KEY="your_dashscope_api_key_here"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

默认登录账号：

```text
用户名：adm
密码：1
```

## GitHub Pages 展示页

本仓库可以用 `docs/` 目录作为 GitHub Pages 静态展示页。

设置路径：

```text
GitHub 仓库 -> Settings -> Pages -> Build and deployment
Source: Deploy from a branch
Branch: main
Folder: /docs
```

发布后，GitHub 会生成一个项目展示链接。这个链接适合放在简历或作品集中，用于说明项目背景、功能和 AI Coding 实践过程。

## 环境变量

```powershell
$env:DASHSCOPE_API_KEY="your_dashscope_api_key_here"
$env:DASHSCOPE_LLM_MODEL="qwen-plus"
$env:MEETING_AI_TEMPERATURE="0.5"
$env:MEETING_AI_TOP_P="0.6"
```
