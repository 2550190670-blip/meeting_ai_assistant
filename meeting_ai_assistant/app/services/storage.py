import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.getenv("MEETING_DATA_DIR", Path(tempfile.gettempdir()) / "meeting_ai_assistant"))
DB_PATH = DATA_DIR / "meetings.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        ensure_column(connection, "meetings", "favorite", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "meetings", "folder", "TEXT NOT NULL DEFAULT '默认文件夹'")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS folders (
                name TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO folders (name, created_at)
            VALUES ('默认文件夹', ?)
            """,
            (datetime.now().strftime("%Y-%m-%d %H:%M"),),
        )


def ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_meeting(title: str, raw_text: str, analysis: dict[str, Any], folder: str = "默认文件夹") -> int:
    init_db()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    create_folder(folder or "默认文件夹")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO meetings (title, raw_text, analysis_json, created_at, folder)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, raw_text, json.dumps(analysis, ensure_ascii=False), created_at, folder or "默认文件夹"),
        )
        return int(cursor.lastrowid)


def list_meetings(folder: str = "", favorites_only: bool = False) -> list[dict[str, Any]]:
    init_db()
    with get_connection() as connection:
        filters = []
        params: list[Any] = []
        if folder:
            filters.append("folder = ?")
            params.append(folder)
        if favorites_only:
            filters.append("favorite = 1")
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        rows = connection.execute(
            f"""
            SELECT id, title, created_at, analysis_json, favorite, folder
            FROM meetings
            {where}
            ORDER BY id DESC
            """,
            params,
        ).fetchall()

    meetings = []
    for row in rows:
        analysis = json.loads(row["analysis_json"])
        meetings.append(
            {
                "id": row["id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "summary": analysis.get("summary", ""),
                "favorite": bool(row["favorite"]),
                "folder": row["folder"],
            }
        )
    return meetings


def list_folders() -> list[str]:
    init_db()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT name AS folder
            FROM folders
            ORDER BY name
            """
        ).fetchall()
    folders = [row["folder"] for row in rows if row["folder"]]
    return folders or ["默认文件夹"]


def create_folder(name: str) -> None:
    init_db()
    clean_name = name.strip() or "默认文件夹"
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO folders (name, created_at)
            VALUES (?, ?)
            """,
            (clean_name, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )


def rename_folder(old_name: str, new_name: str) -> None:
    init_db()
    old_clean = old_name.strip()
    new_clean = new_name.strip() or "默认文件夹"
    if not old_clean or old_clean == new_clean:
        return
    create_folder(new_clean)
    with get_connection() as connection:
        connection.execute("UPDATE meetings SET folder = ? WHERE folder = ?", (new_clean, old_clean))
        if old_clean != "默认文件夹":
            connection.execute("DELETE FROM folders WHERE name = ?", (old_clean,))


def delete_folder(name: str) -> None:
    init_db()
    clean_name = name.strip()
    if not clean_name or clean_name == "默认文件夹":
        return
    create_folder("默认文件夹")
    with get_connection() as connection:
        connection.execute("UPDATE meetings SET folder = '默认文件夹' WHERE folder = ?", (clean_name,))
        connection.execute("DELETE FROM folders WHERE name = ?", (clean_name,))


def get_meeting(meeting_id: int) -> dict[str, Any] | None:
    init_db()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, title, raw_text, analysis_json, created_at, favorite, folder
            FROM meetings
            WHERE id = ?
            """,
            (meeting_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "analysis": json.loads(row["analysis_json"]),
        "created_at": row["created_at"],
        "favorite": bool(row["favorite"]),
        "folder": row["folder"],
    }


def update_meeting(meeting_id: int, title: str, raw_text: str, analysis: dict[str, Any], folder: str) -> None:
    init_db()
    create_folder(folder or "默认文件夹")
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE meetings
            SET title = ?, raw_text = ?, analysis_json = ?, folder = ?
            WHERE id = ?
            """,
            (title, raw_text, json.dumps(analysis, ensure_ascii=False), folder or "默认文件夹", meeting_id),
        )


def delete_meeting(meeting_id: int) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))


def toggle_favorite(meeting_id: int) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE meetings
            SET favorite = CASE favorite WHEN 1 THEN 0 ELSE 1 END
            WHERE id = ?
            """,
            (meeting_id,),
        )


def update_analysis(meeting_id: int, analysis: dict[str, Any]) -> None:
    init_db()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE meetings
            SET analysis_json = ?
            WHERE id = ?
            """,
            (json.dumps(analysis, ensure_ascii=False), meeting_id),
        )
