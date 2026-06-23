# utils.py
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_FILE = "legal_agent.db"


def _connect() -> sqlite3.Connection:
    """
    Centralized connection helper. WAL mode + busy_timeout lets multiple
    Streamlit sessions/threads read and write without throwing
    'database is locked' errors, which the original per-call
    sqlite3.connect() with default journal mode was prone to.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db():
    """Initialize SQLite schema on first run."""
    conn = _connect()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            thread_id TEXT PRIMARY KEY,
            title TEXT,
            mode TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
        )
    """)
    conn.commit()
    conn.close()


def create_thread(title: str, mode: str) -> str:
    thread_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO threads (thread_id, title, mode, created_at) VALUES (?, ?, ?, ?)",
        (thread_id, title, mode, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return thread_id


def update_thread_title(thread_id: str, title: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE threads SET title = ? WHERE thread_id = ?", (title, thread_id))
    conn.commit()
    conn.close()


def save_message(thread_id: str, role: str, content: str):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (thread_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (thread_id, role, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_thread(thread_id: str) -> list[dict]:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY timestamp",
        (thread_id,),
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": role, "content": content} for role, content in rows]


def get_all_threads() -> list[tuple]:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT thread_id, title, mode, created_at FROM threads ORDER BY created_at DESC")
    threads = c.fetchall()
    conn.close()
    return threads


def delete_thread(thread_id: str):
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
    c.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
    conn.commit()
    conn.close()


def get_thread_message_count(thread_id: str) -> int:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE thread_id = ?", (thread_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def export_thread_as_markdown(thread_id: str) -> str:
    """Export a thread's conversation to markdown format."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT title, mode, created_at FROM threads WHERE thread_id = ?", (thread_id,))
    meta = c.fetchone()
    c.execute(
        "SELECT role, content, timestamp FROM messages WHERE thread_id = ? ORDER BY timestamp",
        (thread_id,),
    )
    rows = c.fetchall()
    conn.close()

    if not meta:
        return "Thread not found."

    title, mode, created_at = meta
    lines = [
        f"# {title}",
        f"**Mode:** {mode.title()} | **Created:** {created_at[:19]}",
        "",
        "---",
        "",
    ]
    for role, content, ts in rows:
        label = "👤 User" if role == "user" else "Legal AI"
        lines.append(f"### {label} — {ts[:19]}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)