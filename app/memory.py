import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self, path: str):
        self.path = str(Path(path))
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _init_db(self):
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    first_question TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'model')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id)"
            )
            db.commit()

    def first(self, session_id: str) -> Optional[str]:
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT first_question FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                return row[0] if row else None
        except sqlite3.Error:
            logger.exception("Failed to get first question")
            return None

    def start(self, session_id: str, first_question: str) -> bool:
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO sessions(id, first_question) VALUES(?, ?)",
                    (session_id, first_question),
                )
                db.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to start session")
            return False

    def add(self, session_id: str, role: str, content: str) -> bool:
        if role not in {"user", "model"}:
            raise ValueError(f"Unsupported message role: {role}")
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT INTO messages(session_id, role, content) VALUES(?, ?, ?)",
                    (session_id, role, content),
                )
                db.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to add message")
            return False

    def history(self, session_id: str, limit: int = 20) -> List[Tuple[str, str]]:
        try:
            with self._connect() as db:
                rows = db.execute(
                    """
                    SELECT role, content
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_id, max(1, int(limit))),
                ).fetchall()
                return list(reversed(rows))
        except sqlite3.Error:
            logger.exception("Failed to read history")
            return []


    def list_sessions(self, limit: int = 50) -> List[dict]:
        try:
            with self._connect() as db:
                rows = db.execute(
                    """
                    SELECT
                        s.id,
                        s.first_question,
                        s.created_at,
                        COUNT(m.id) AS message_count
                    FROM sessions AS s
                    LEFT JOIN messages AS m ON m.session_id = s.id
                    GROUP BY s.id
                    ORDER BY s.created_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(int(limit), 100)),),
                ).fetchall()
                return [
                    {
                        "id": row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "message_count": row[3],
                    }
                    for row in rows
                ]
        except sqlite3.Error:
            logger.exception("Failed to list sessions")
            return []

    def conversation(self, session_id: str, limit: int = 100) -> List[Tuple[str, str]]:
        return self.history(session_id, limit=limit)
