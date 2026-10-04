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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    memory_summary TEXT NOT NULL DEFAULT '',
                    memory_summary_through INTEGER NOT NULL DEFAULT 0
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
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()}
            if "memory_summary" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN memory_summary TEXT NOT NULL DEFAULT ''")
            if "memory_summary_through" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN memory_summary_through INTEGER NOT NULL DEFAULT 0")
            if "project_id" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN project_id TEXT NOT NULL DEFAULT ''")
            db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_feedback_session_id ON feedback(session_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id)")

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

    def start(self, session_id: str, first_question: str, project_id: str = "") -> bool:
        try:
            with self._connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO sessions(id, first_question, project_id) VALUES(?, ?, ?)",
                    (session_id, first_question, str(project_id or "")),
                )
                db.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to start session")
            return False

    def create_project(self, project_id: str, name: str, description: str = "") -> bool:
        try:
            with self._connect() as db:
                db.execute("INSERT INTO projects(id, name, description) VALUES(?, ?, ?)",
                           (project_id, str(name).strip()[:120], str(description or "").strip()[:1000]))
                db.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to create project")
            return False

    def list_projects(self, limit: int = 100) -> List[dict]:
        try:
            with self._connect() as db:
                rows = db.execute("""SELECT p.id, p.name, p.description, p.created_at, p.updated_at,
                    COUNT(s.id) FROM projects p LEFT JOIN sessions s ON s.project_id = p.id
                    GROUP BY p.id ORDER BY p.updated_at DESC, p.created_at DESC LIMIT ?""",
                    (max(1, min(int(limit), 200)),)).fetchall()
                return [{"id": r[0], "name": r[1], "description": r[2], "created_at": r[3],
                         "updated_at": r[4], "conversation_count": r[5]} for r in rows]
        except sqlite3.Error:
            logger.exception("Failed to list projects")
            return []

    def get_project(self, project_id: str) -> Optional[dict]:
        try:
            with self._connect() as db:
                row = db.execute("SELECT id, name, description, created_at, updated_at FROM projects WHERE id = ?",
                                 (project_id,)).fetchone()
                return {"id": row[0], "name": row[1], "description": row[2],
                        "created_at": row[3], "updated_at": row[4]} if row else None
        except sqlite3.Error:
            logger.exception("Failed to get project")
            return None

    def project_conversations(self, project_id: str, limit: int = 100) -> List[dict]:
        try:
            with self._connect() as db:
                rows = db.execute("""SELECT s.id, s.first_question, s.created_at, COUNT(m.id)
                    FROM sessions s LEFT JOIN messages m ON m.session_id = s.id
                    WHERE s.project_id = ? GROUP BY s.id ORDER BY s.created_at DESC LIMIT ?""",
                    (project_id, max(1, min(int(limit), 200)))).fetchall()
                return [{"id": r[0], "title": r[1], "created_at": r[2], "message_count": r[3]} for r in rows]
        except sqlite3.Error:
            logger.exception("Failed to list project conversations")
            return []

    def project_id_for_session(self, session_id: str) -> str:
        try:
            with self._connect() as db:
                row = db.execute("SELECT project_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
                return str(row[0] or "") if row else ""
        except sqlite3.Error:
            return ""

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


    def count_messages(self, session_id: str) -> int:
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                return int(row[0] or 0) if row else 0
        except sqlite3.Error:
            logger.exception("Failed to count messages")
            return 0

    def memory_summary(self, session_id: str) -> Tuple[str, int]:
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT memory_summary, memory_summary_through FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                return (str(row[0] or ""), int(row[1] or 0)) if row else ("", 0)
        except sqlite3.Error:
            logger.exception("Failed to get memory summary")
            return "", 0

    def update_memory_summary(self, session_id: str, summary: str, through_id: int) -> bool:
        try:
            with self._connect() as db:
                db.execute(
                    "UPDATE sessions SET memory_summary = ?, memory_summary_through = ? WHERE id = ?",
                    (summary, int(through_id), session_id),
                )
                db.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to update memory summary")
            return False

    def history_after(self, session_id: str, after_id: int, limit: int = 200) -> List[Tuple[int, str, str]]:
        try:
            with self._connect() as db:
                rows = db.execute(
                    """
                    SELECT id, role, content
                    FROM messages
                    WHERE session_id = ? AND id > ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (session_id, int(after_id), max(1, int(limit))),
                ).fetchall()
                return [(int(row[0]), row[1], row[2]) for row in rows]
        except sqlite3.Error:
            logger.exception("Failed to read messages after summary")
            return []


    def relevant_messages(self, session_id: str, query: str, limit: int = 8) -> List[Tuple[int, str, str]]:
        """Retrieve older conversation turns that are lexically relevant to the current request."""
        try:
            words = {
                word.lower()
                for word in __import__("re").findall(r"[A-Za-z0-9_]{4,}", str(query or ""))
                if word.lower() not in {
                    "what", "when", "where", "which", "with", "that", "this",
                    "from", "have", "will", "would", "could", "should", "about",
                    "please", "make", "help", "need", "want", "your", "into",
                }
            }
            if not words:
                return []
            with self._connect() as db:
                rows = db.execute(
                    """
                    SELECT id, role, content
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id ASC
                    """,
                    (session_id,),
                ).fetchall()
            ranked = []
            for row_id, role, content in rows:
                text = str(content or "")
                lower = text.lower()
                score = sum(lower.count(word) for word in words)
                if score:
                    ranked.append((score, int(row_id), role, text))
            ranked.sort(key=lambda item: (-item[0], -item[1]))
            return [(row_id, role, content) for _, row_id, role, content in ranked[:max(1, int(limit))]]
        except sqlite3.Error:
            logger.exception("Failed to retrieve relevant messages")
            return []

    def add_feedback(self, session_id: str, rating: str, note: str = "", message_id: int = 0) -> bool:
        """Store explicit user feedback for future response-quality improvements."""
        if rating not in {"positive", "negative"}:
            raise ValueError(f"Unsupported feedback rating: {rating}")
        try:
            with self._connect() as db:
                db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feedback (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        message_id INTEGER NOT NULL DEFAULT 0,
                        rating TEXT NOT NULL CHECK(rating IN ('positive', 'negative')),
                        note TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                    """
                )
                db.execute(
                    "INSERT INTO feedback(session_id, message_id, rating, note) VALUES(?, ?, ?, ?)",
                    (session_id, int(message_id or 0), rating, str(note or "")[:1000]),
                )
                db.commit()
            return True
        except sqlite3.Error:
            logger.exception("Failed to store feedback")
            return False

    def feedback(self, session_id: str, limit: int = 10) -> List[Tuple[str, str]]:
        """Return recent user feedback notes for the current conversation."""
        try:
            with self._connect() as db:
                rows = db.execute(
                    """
                    SELECT rating, note
                    FROM feedback
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (session_id, max(1, int(limit))),
                ).fetchall()
                return [(row[0], row[1]) for row in rows]
        except sqlite3.Error:
            logger.exception("Failed to read feedback")
            return []

    def latest_message_id(self, session_id: str) -> int:
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT COALESCE(MAX(id), 0) FROM messages WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                return int(row[0] or 0) if row else 0
        except sqlite3.Error:
            logger.exception("Failed to get latest message id")
            return 0

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
