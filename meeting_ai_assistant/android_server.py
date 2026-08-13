import os
import shutil
import threading
from pathlib import Path

import uvicorn

_started = False


def start_server(data_dir: str, port: int = 8765) -> None:
    global _started
    if _started:
        return

    base_dir = Path(__file__).resolve().parent
    app_data_dir = Path(data_dir)
    app_data_dir.mkdir(parents=True, exist_ok=True)

    os.environ["MEETING_DATA_DIR"] = str(app_data_dir)
    env_path = app_data_dir / ".env"
    packaged_env = base_dir / ".env"
    if packaged_env.exists() and not env_path.exists():
        shutil.copyfile(packaged_env, env_path)
    os.environ["MEETING_ENV_FILE"] = str(env_path)

    thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    thread.start()
    _started = True


def _run_server(port: int) -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")
