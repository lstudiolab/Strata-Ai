import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    first_question TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )
            db.commit()

    def first(self, session_id: str):
        try:
            with sqlite3.connect(self.path) as db:
                row = db.execute(
                    "SELECT first_question FROM sessions WHERE id=?",
                    (session_id,),
                ).fetchone()
                return row[0] if row else None
        except Exception as exc:
            logger.error(f"Failed to get first question: {exc}")
            return None

    def start(self, session_id: str, first_question: str):
        try:
            with sqlite3.connect(self.path) as db:
                db.execute(
                    "INSERT OR IGNORE INTO sessions(id, first_question) VALUES(?, ?)",
                    (session_id, first_question),
                )
                db.commit()
            return True
        except Exception as exc:
            logger.error(f"Failed to start session: {exc}")
            return False

    def add(self, session_id: str, role: str, content: str):
        try:
            with sqlite3.connect(self.path) as db:
                db.execute(
                    "INSERT INTO messages(session_id, role, content) VALUES(?, ?, ?)",
                    (session_id, role, content),
                )
                db.commit()
            return True
        except Exception as exc:
            logger.error(f"Failed to add message: {exc}")
            return False

    def history(self, session_id: str, limit: int = 20):
        try:
            with sqlite3.connect(self.path) as db:
                rows = db.execute(
                    "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
                return list(reversed(rows))
        except Exception as exc:
            logger.error(f"Failed to read history: {exc}")
            return []
