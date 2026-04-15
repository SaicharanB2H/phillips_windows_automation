"""
Context Manager — shared memory/state across agents during a session.

Stores:
- Resolved file paths from previous steps
- Computed data (DataFrame summaries, etc.)
- Step results accessible via template variables
- User-provided context (email, preferences)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger("app.context", "context")


class ContextManager:
    """
    In-memory key-value store for agent context sharing.
    Supports template variable resolution like {{step_1.result.path}}.
    """

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._step_results: Dict[int, Dict[str, Any]] = {}  # step_order -> result data

    def set(self, key: str, value: Any):
        """Store a value by key."""
        self._store[key] = value
        logger.debug(f"Context set: {key} = {repr(value)[:80]}")

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key."""
        return self._store.get(key, default)

    def set_step_result(self, step_order: int, result_data: Dict[str, Any]):
        """Store the result of a completed step for template resolution."""
        self._step_results[step_order] = result_data
        # Also flatten key fields into the main store for easy access
        if isinstance(result_data, dict):
            for k, v in result_data.items():
                self._store[f"step_{step_order}_{k}"] = v

    def get_step_result(self, step_order: int) -> Optional[Dict[str, Any]]:
        return self._step_results.get(step_order)

    def resolve_template(self, value: Any) -> Any:
        """
        Resolve {{step_N.result.key}} template variables in strings.
        Also handles nested resolution in dicts and lists.
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        elif isinstance(value, dict):
            return {k: self.resolve_template(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_template(item) for item in value]
        return value

    def resolve_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve all template variables in a tool's argument dict."""
        return {k: self.resolve_template(v) for k, v in arguments.items()}

    def _resolve_string(self, text: str) -> str:
        """Replace {{step_N.result.key}} and {{context_key}} patterns."""
        # Pattern: {{step_N.result.field}} or {{step_N.result.nested.field}}
        step_pattern = re.compile(r"\{\{step_(\d+)\.result\.([^}]+)\}\}")
        for match in step_pattern.finditer(text):
            step_n = int(match.group(1))
            field_path = match.group(2).split(".")
            result = self._step_results.get(step_n, {})
            value = self._nested_get(result, field_path)
            if value is not None:
                text = text.replace(match.group(0), str(value))

        # Pattern: {{context_key}}
        ctx_pattern = re.compile(r"\{\{([^}]+)\}\}")
        for match in ctx_pattern.finditer(text):
            key = match.group(1)
            value = self._store.get(key)
            if value is not None:
                text = text.replace(match.group(0), str(value))

        return text

    def _nested_get(self, data: Any, keys: List[str]) -> Any:
        """Get a nested value from a dict using a list of keys."""
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                return None
        return data

    def clear(self):
        """Clear all context (e.g., on new session)."""
        self._store.clear()
        self._step_results.clear()

    def as_dict(self) -> Dict[str, Any]:
        """Snapshot of the context for debugging."""
        return dict(self._store)

    def update_from_dict(self, data: Dict[str, Any]):
        """Bulk update context from a dict."""
        for k, v in data.items():
            self.set(k, v)
