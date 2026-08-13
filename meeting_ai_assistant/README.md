# Mobile Meeting AI Assistant

A mobile-friendly meeting organizer built with Python and FastAPI.

## Features

- Create meeting records from pasted notes or transcripts
- Upload audio or video recordings for Qwen3 speech-to-text transcription
- Generate structured meeting minutes
- Save meeting history in SQLite
- Mobile-first web interface
- Optional OpenAI-compatible AI integration through `OPENAI_API_KEY`
- Mainland China speech-to-text through Alibaba Cloud DashScope `DASHSCOPE_API_KEY`
- Local fallback summarizer when no API key is configured

## Quick Start

```powershell
cd meeting_ai_assistant
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Optional AI Setup

For Qwen3 speech-to-text in mainland China, create a DashScope API key and set:

```powershell
$env:DASHSCOPE_API_KEY="your_dashscope_api_key_here"
```

Optional DashScope settings:

```powershell
$env:DASHSCOPE_ASR_MODEL="qwen3-asr-flash"
$env:DASHSCOPE_LLM_MODEL="qwen3.7-plus"
$env:MEETING_AI_TEMPERATURE="0.1"
$env:MEETING_AI_TOP_P="0.6"
$env:DASHSCOPE_COMPATIBLE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

Set an API key before starting the server:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

Optional settings:

```powershell
$env:OPENAI_MODEL="gpt-4.1-mini"
$env:OPENAI_TRANSCRIBE_MODEL="whisper-1"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
```

## Roadmap

- Speaker identification
- Export to Markdown or Word
- Task reminders
