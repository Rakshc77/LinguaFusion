import sqlite3
from datetime import datetime

from backend.config.paths import STORAGE_DIR, ensure_runtime_dirs

ensure_runtime_dirs()
DB_PATH = STORAGE_DIR / "linguafusion.db"


def get_connection():
    return sqlite3.connect(DB_PATH, timeout=15)


def init_notes_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                language TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()


def create_note(title: str, content: str, language: str):
    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO notes (title, content, language, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, content, language, now, now)
        )
        conn.commit()

        return {
            "id": cursor.lastrowid,
            "title": title,
            "content": content,
            "language": language,
            "created_at": now,
            "updated_at": now
        }


def list_notes():
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, title, content, language, created_at, updated_at
            FROM notes
            ORDER BY updated_at DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]


def get_note(note_id: int):
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT id, title, content, language, created_at, updated_at
            FROM notes
            WHERE id = ?
            """,
            (note_id,)
        ).fetchone()

        return dict(row) if row else None


def delete_note(note_id: int):
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM notes WHERE id = ?",
            (note_id,)
        )
        conn.commit()

        return cursor.rowcount > 0


init_notes_db()