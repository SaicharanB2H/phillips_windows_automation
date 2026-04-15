"""
Memory Agent — lets the LLM explicitly read and write persistent user memory.

Tools exposed:
  memory.save(key, value, category)  — store a fact permanently
  memory.recall(key)                 — look up a stored fact
  memory.list(category)              — list all remembered facts
  memory.forget(key)                 — delete a fact
  memory.clear()                     — wipe all memories (requires approval)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from models.schemas import AgentType, RiskLevel
from storage.memory_store import get_memory_store
from utils.logger import get_logger

logger = get_logger("agents.memory", "memory")


class MemoryAgent(BaseAgent):
    """Manages persistent cross-session memory for the automation agent."""

    def __init__(self):
        self._store = get_memory_store()
        super().__init__(AgentType.MEMORY)

    def _register_tools(self):
        self.register_tool(
            "memory.save", self.save,
            "Remember a fact permanently across sessions",
            ["key", "value"],
        )
        self.register_tool(
            "memory.recall", self.recall,
            "Look up a previously remembered fact",
            ["key"],
        )
        self.register_tool(
            "memory.list", self.list_all,
            "List all remembered facts",
        )
        self.register_tool(
            "memory.forget", self.forget,
            "Delete a specific remembered fact",
            ["key"],
            risk_level=RiskLevel.MEDIUM,
        )
        self.register_tool(
            "memory.clear", self.clear_all,
            "Wipe all remembered facts",
            risk_level=RiskLevel.HIGH,
        )
        self.register_tool(
            "memory.update", self.save,   # alias
            "Update a remembered fact",
            ["key", "value"],
        )

    # ── Tool implementations ──────────────────────────────────────────────────

    def save(
        self,
        key: str,
        value: str,
        category: str = "facts",
    ) -> Dict[str, Any]:
        """Persistently remember a key-value fact."""
        is_new = self._store.save(key, value, category, source="llm")
        return {
            "saved": True,
            "key": key,
            "value": value,
            "category": category,
            "is_new": is_new,
            "message": f"{'Remembered' if is_new else 'Updated'}: {key} = {value}",
        }

    def recall(self, key: str) -> Dict[str, Any]:
        """Retrieve a remembered fact by key."""
        value = self._store.recall(key)
        return {
            "key": key,
            "value": value,
            "found": value is not None,
            "message": f"{key} = {value}" if value else f"No memory found for '{key}'",
        }

    def list_all(self, category: str = None) -> Dict[str, Any]:
        """Return all stored memories, optionally filtered by category."""
        items = self._store.all(category=category)
        # Group by category for readability
        grouped: Dict[str, List] = {}
        for item in items:
            grouped.setdefault(item["category"], []).append({
                "key": item["key"],
                "value": item["value"],
                "source": item["source"],
                "updated_at": item["updated_at"],
            })
        return {
            "count": len(items),
            "categories": grouped,
            "items": items,
            "summary": self._build_summary(grouped),
        }

    def forget(self, key: str) -> Dict[str, Any]:
        """Delete a remembered fact."""
        deleted = self._store.forget(key)
        return {
            "deleted": deleted,
            "key": key,
            "message": f"Forgot '{key}'" if deleted else f"No memory found for '{key}'",
        }

    def clear_all(self) -> Dict[str, Any]:
        """Wipe all memories — requires user approval."""
        count = self._store.clear_all()
        return {
            "cleared": True,
            "count": count,
            "message": f"All {count} memories cleared",
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_summary(grouped: Dict[str, List]) -> str:
        lines = []
        for cat, items in grouped.items():
            lines.append(f"{cat.title()}:")
            for item in items:
                lines.append(f"  • {item['key']}: {item['value']}")
        return "\n".join(lines) if lines else "No memories stored yet."
