import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .services.ai import analyze_meeting
from .services.storage import (
    create_folder,
    create_meeting,
    delete_meeting,
    get_meeting,
    init_db,
    list_folders,
    list_meetings,
    delete_folder,
    rename_folder,
    toggle_favorite,
    update_analysis,
    update_meeting,
)
from .services.transcription import guess_mime_type, resolve_local_recording, transcribe_local_file, transcribe_upload

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(os.getenv("MEETING_ENV_FILE", BASE_DIR.parent / ".env"))

app = FastAPI(title="Mobile Meeting AI Assistant")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def is_logged_in(request: Request) -> bool:
    return request.cookies.get("meeting_auth") == "ok"


def require_login(request: Request) -> None:
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="请先登录。")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = "") -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    if username == "adm" and password == "1":
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("meeting_auth", "ok", httponly=True, samesite="lax")
        return response
    return RedirectResponse(url="/login?error=用户名或密码错误", status_code=303)


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("meeting_auth")
    return response


@app.post("/folders")
def add_folder(request: Request, name: str = Form(...)) -> RedirectResponse:
    require_login(request)
    create_folder(name)
    return RedirectResponse(url="/", status_code=303)


@app.post("/folders/rename")
def rename_folder_route(request: Request, old_name: str = Form(...), new_name: str = Form(...)) -> RedirectResponse:
    require_login(request)
    rename_folder(old_name, new_name)
    return RedirectResponse(url="/", status_code=303)


@app.post("/folders/delete")
def delete_folder_route(request: Request, name: str = Form(...)) -> RedirectResponse:
    require_login(request)
    delete_folder(name)
    return RedirectResponse(url="/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, folder: str = "", favorites: bool = False) -> HTMLResponse:
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "meetings": list_meetings(folder=folder, favorites_only=favorites),
            "folders": list_folders(),
            "current_folder": folder,
            "favorites": favorites,
        },
    )


@app.get("/meetings/new", response_class=HTMLResponse)
def new_meeting(request: Request, error: str = "") -> HTMLResponse:
    require_login(request)
    return templates.TemplateResponse("new.html", {"request": request, "error": error, "folders": list_folders()})


@app.post("/meetings")
async def save_meeting(
    request: Request,
    title: str = Form(...),
    raw_text: str = Form(""),
    folder: str = Form("默认文件夹"),
    native_recording_path: str = Form(""),
    recording: UploadFile | None = File(None),
):
    require_login(request)
    transcript_text = await build_transcript(raw_text, recording, native_recording_path)
    if not transcript_text.strip():
        return templates.TemplateResponse(
            "new.html",
            {
                "request": request,
                "error": "请至少添加一种会议内容：现场录音、上传录音/视频，或填写会议文本。",
                "title": title,
                "raw_text": raw_text,
                "folder": folder,
                "native_recording_path": native_recording_path,
                "folders": list_folders(),
            },
            status_code=400,
        )

    analysis = await analyze_meeting(transcript_text)
    meeting_id = create_meeting(title=title.strip() or "Untitled Meeting", raw_text=transcript_text, analysis=analysis, folder=folder)
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@app.get("/recordings/native")
def native_recording(request: Request, path: str) -> FileResponse:
    require_login(request)
    recording_path = resolve_local_recording(path)
    return FileResponse(recording_path, media_type=guess_mime_type(recording_path), filename=recording_path.name)


@app.get("/meetings/{meeting_id}", response_class=HTMLResponse)
def meeting_detail(meeting_id: int, request: Request) -> HTMLResponse:
    require_login(request)
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return templates.TemplateResponse("detail.html", {"request": request, "meeting": meeting, "folders": list_folders()})


@app.get("/meetings/{meeting_id}/edit", response_class=HTMLResponse)
def edit_meeting(meeting_id: int, request: Request) -> HTMLResponse:
    require_login(request)
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return templates.TemplateResponse("edit.html", {"request": request, "meeting": meeting, "folders": list_folders()})


@app.post("/meetings/{meeting_id}/edit")
async def save_meeting_edit(
    meeting_id: int,
    request: Request,
    title: str = Form(...),
    raw_text: str = Form(...),
    folder: str = Form("默认文件夹"),
):
    require_login(request)
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    analysis = await analyze_meeting(raw_text)
    update_meeting(meeting_id, title.strip() or meeting["title"], raw_text, analysis, folder)
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@app.post("/meetings/{meeting_id}/regenerate")
async def regenerate_meeting(meeting_id: int, request: Request) -> RedirectResponse:
    require_login(request)
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    analysis = await analyze_meeting(meeting["raw_text"])
    update_meeting(meeting_id, meeting["title"], meeting["raw_text"], analysis, meeting["folder"])
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@app.post("/meetings/{meeting_id}/folder")
def change_meeting_folder(meeting_id: int, request: Request, folder: str = Form("默认文件夹")) -> RedirectResponse:
    require_login(request)
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    update_meeting(meeting_id, meeting["title"], meeting["raw_text"], meeting["analysis"], folder)
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@app.post("/meetings/{meeting_id}/favorite")
def favorite_meeting(meeting_id: int, request: Request, ajax: bool = Form(False)):
    require_login(request)
    toggle_favorite(meeting_id)
    if ajax:
        meeting = get_meeting(meeting_id)
        return {"favorite": bool(meeting and meeting["favorite"])}
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@app.post("/meetings/{meeting_id}/delete")
def remove_meeting(meeting_id: int, request: Request, ajax: bool = Form(False)):
    require_login(request)
    delete_meeting(meeting_id)
    if ajax:
        return {"deleted": True}
    return RedirectResponse(url="/", status_code=303)


@app.post("/meetings/bulk-delete")
def bulk_delete_meetings(request: Request, meeting_ids: list[int] = Form([])) -> RedirectResponse:
    require_login(request)
    for meeting_id in meeting_ids:
        delete_meeting(meeting_id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/meetings/{meeting_id}/analysis")
def save_analysis_edit(
    meeting_id: int,
    request: Request,
    title: str = Form(""),
    summary: str = Form(""),
    topics: str = Form(""),
    decisions: str = Form(""),
    risks: str = Form(""),
    follow_up: str = Form(""),
    action_owner: list[str] = Form([]),
    action_task: list[str] = Form([]),
    action_due_date: list[str] = Form([]),
) -> RedirectResponse:
    require_login(request)
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    action_items = []
    for owner, task, due_date in zip(action_owner, action_task, action_due_date):
        if task.strip():
            action_items.append({"owner": owner.strip() or "待确认", "task": task.strip(), "due_date": due_date.strip() or "待确认"})
    analysis = {
        "summary": summary.strip() or meeting["analysis"].get("summary", ""),
        "topics": split_lines(topics),
        "decisions": split_lines(decisions),
        "action_items": action_items,
        "risks": split_lines(risks),
        "follow_up": split_lines(follow_up),
    }
    new_title = title.strip() or meeting["title"]
    if new_title != meeting["title"]:
        update_meeting(meeting_id, new_title, meeting["raw_text"], analysis, meeting["folder"])
    else:
        update_analysis(meeting_id, analysis)
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@app.get("/meetings/{meeting_id}/stream")
async def stream_meeting_detail(meeting_id: int, request: Request) -> StreamingResponse:
    require_login(request)
    meeting = get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    async def event_stream():
        for event in build_stream_events(meeting):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.28)
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def build_transcript(raw_text: str, recording: UploadFile | None, native_recording_path: str = "") -> str:
    transcript_parts = []
    if raw_text.strip():
        transcript_parts.append(raw_text.strip())
    if native_recording_path.strip():
        transcript = await transcribe_local_file(native_recording_path.strip())
        if transcript.strip():
            transcript_parts.append(transcript.strip())
    if recording and recording.filename:
        transcript = await transcribe_upload(recording)
        if transcript.strip():
            transcript_parts.append(transcript.strip())
    return "\n\n".join(transcript_parts)


def build_stream_events(meeting: dict) -> list[dict]:
    analysis = meeting["analysis"]
    return [
        {"type": "summary", "payload": analysis.get("summary", "")},
        {"type": "topics", "payload": analysis.get("topics", [])},
        {"type": "action_items", "payload": analysis.get("action_items", [])},
        {"type": "decisions", "payload": analysis.get("decisions", [])},
        {"type": "risks", "payload": analysis.get("risks", [])},
        {"type": "follow_up", "payload": analysis.get("follow_up", [])},
        {"type": "transcript", "payload": meeting.get("raw_text", "")},
    ]


def split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]
