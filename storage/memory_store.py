"""
Persistent Memory Store — remembers user facts, preferences, paths and contacts
across all sessions so the user never has to repeat themselves.

Backed by the same SQLite database as everything else.
Categories:
  user        — name, email, role, company
  contacts    — other people's emails / names
  paths       — frequently used file / folder paths
  preferences — output dir, execution mode, report style
  facts       — anything else the user explicitly asks to remember
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from storage.database import get_db
from utils.logger import get_logger

logger = get_logger("storage.memory", "memory")

# ── Regex patterns for auto-extraction from user text ────────────────────────

_EMAIL_RE    = re.compile(r"\b[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PATH_RE     = re.compile(r"[A-Za-z]:\\(?:[\w\s.()\-]+\\)*[\w\s.()\-]+\.[\w]+")
_UNC_PATH_RE = re.compile(r"\\\\[\w.-]+\\[\w$][\w\s.-]+(?:\\[\w\s.-]+)*")

# Phrases like "my name is John", "I am John", "call me John"
_MY_NAME_RE  = re.compile(r"(?:my name is|i am|call me|i'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.I)
_MY_EMAIL_RE = re.compile(r"my email(?:\s+is|\s+address\s+is)?\s+([\w.+%-]+@[\w.-]+\.[A-Za-z]{2,})", re.I)
_SEND_TO_RE  = re.compile(r"(?:send|email|mail)\s+(?:it\s+)?to\s+([\w.+%-]+@[\w.-]+\.[A-Za-z]{2,})", re.I)
_SAVE_TO_RE  = re.compile(r"save\s+(?:it\s+)?(?:to|in|into)\s+([A-Za-z]:\\(?:[\w\s.()-]+\\?)+)", re.I)
_REMEMBER_RE = re.compile(r"remember\s+(?:that\s+)?(.+?)(?:\s+is|\s+=\s*)(.+)", re.I)


class MemoryStore:
    """
    Key-value memory store with categories.
    All writes are immediately persisted to SQLite.
    """

    CATEGORIES = ("user", "contacts", "paths", "preferences", "facts")

    def __init__(self):
        self._db = get_db()
        self._ensure_table()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _ensure_table(self):
        with self._db._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    category   TEXT NOT NULL DEFAULT 'facts',
                    source     TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_cat ON memory(category)")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(
        self,
        key: str,
        value: Any,
        category: str = "facts",
        source: str = "user",
    ) -> bool:
        """Upsert a memory entry. Returns True if this is a new key."""
        key = self._normalise_key(key)
        category = category if category in self.CATEGORIES else "facts"
        val_str = value if isinstance(value, str) else json.dumps(value)
        now = datetime.utcnow().isoformat()

        existing = self.recall(key)
        with self._db._conn() as conn:
            conn.execute(
                """INSERT INTO memory (key, value, category, source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value,
                       category=excluded.category,
                       source=excluded.source,
                       updated_at=excluded.updated_at""",
                (key, val_str, category, source, now, now),
            )
        action = "saved" if existing is None else "updated"
        logger.info(f"Memory {action}: [{category}] {key} = {val_str[:80]}")
        return existing is None

    def recall(self, key: str) -> Optional[str]:
        """Return the stored value for a key, or None."""
        key = self._normalise_key(key)
        with self._db._conn() as conn:
            row = conn.execute(
                "SELECT value FROM memory WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def forget(self, key: str) -> bool:
        """Delete a memory entry. Returns True if it existed."""
        key = self._normalise_key(key)
        with self._db._conn() as conn:
            cur = conn.execute("DELETE FROM memory WHERE key = ?", (key,))
            deleted = cur.rowcount > 0
        if deleted:
            logger.info(f"Memory deleted: {key}")
        return deleted

    def all(self, category: str = None) -> List[Dict[str, str]]:
        """Return all memory entries, optionally filtered by category."""
        with self._db._conn() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM memory WHERE category=? ORDER BY key",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory ORDER BY category, key"
                ).fetchall()
            return [dict(r) for r in rows]

    def count(self) -> int:
        with self._db._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]

    def clear_all(self) -> int:
        """Wipe all memories. Returns count deleted."""
        with self._db._conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
            conn.execute("DELETE FROM memory")
        logger.warning(f"All {n} memories cleared")
        return n

    # ── Context injection ─────────────────────────────────────────────────────

    def as_context_dict(self) -> Dict[str, str]:
        """Flat dict of all memories — merged into ContextManager on every request."""
        return {r["key"]: r["value"] for r in self.all()}

    def as_prompt_block(self) -> str:
        """
        Format all memories as a structured block injected into the LLM system prompt.
        The LLM reads this and treats it as pre-known user context.
        """
        rows = self.all()
        if not rows:
            return ""

        by_cat: Dict[str, List] = {}
        for r in rows:
            by_cat.setdefault(r["category"], []).append(r)

        lines = [
            "## Persistent User Memory",
            "These facts were remembered from previous sessions.",
            "Use them directly — do NOT ask the user to repeat this information.\n",
        ]
        for cat in self.CATEGORIES:
            items = by_cat.get(cat, [])
            if items:
                lines.append(f"### {cat.title()}")
                for item in items:
                    lines.append(f"  - {item['key']}: {item['value']}")
                lines.append("")

        return "\n".join(lines)

    # ── Auto-extraction from user text ────────────────────────────────────────

    def auto_extract(self, text: str) -> List[Tuple[str, str, str]]:
        """
        Parse a user message for facts worth remembering automatically.
        Returns list of (key, value, category) tuples that were saved.
        """
        saved: List[Tuple[str, str, str]] = []

        # "my name is John Doe"
        for m in _MY_NAME_RE.finditer(text):
            name = m.group(1).strip()
            if self.save("user_name", name, "user", "auto"):
                saved.append(("user_name", name, "user"))

        # "my email is john@example.com"
        for m in _MY_EMAIL_RE.finditer(text):
            email = m.group(1).strip()
            if self.save("user_email", email, "user", "auto"):
                saved.append(("user_email", email, "user"))

        # "send/email to someone@example.com" — save as a contact
        for m in _SEND_TO_RE.finditer(text):
            email = m.group(1).strip()
            key = f"contact_{email.split('@')[0]}"
            if self.save(key, email, "contacts", "auto"):
                saved.append((key, email, "contacts"))

        # "save to C:\Users\..." — save as preferred output path
        for m in _SAVE_TO_RE.finditer(text):
            path = m.group(1).strip().rstrip("\\")
            if self.save("preferred_output_dir", path, "preferences", "auto"):
                saved.append(("preferred_output_dir", path, "preferences"))

        # Explicit "remember that X is Y"
        for m in _REMEMBER_RE.finditer(text):
            key = self._normalise_key(m.group(1).strip())
            val = m.group(2).strip()
            if key and val:
                if self.save(key, val, "facts", "user"):
                    saved.append((key, val, "facts"))

        if saved:
            logger.info(f"Auto-extracted {len(saved)} memory fact(s) from user message")

        return saved

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_key(key: str) -> str:
        """Lowercase, strip, replace spaces/hyphens with underscores."""
        return re.sub(r"[\s\-]+", "_", key.lower().strip())


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
