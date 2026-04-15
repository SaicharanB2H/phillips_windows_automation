"""
Context Manager — shared memory/state across agents during a session.

Stores:
- Resolved file paths from previous steps
- Computed data (DataFrame summaries, etc.)
- Step results accessible via template variables
- User-provided context (email, preferences)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger("app.context", "context")

# Single-template pattern: the entire string is one {{...}} expression
_SOLE_STEP_PATTERN  = re.compile(r"^\{\{step_(\d+)\.result\.([^}]+)\}\}$")
_SOLE_ARR_PATTERN   = re.compile(r"^\{\{step_(\d+)\.result\[(\d+)\]\}\}$")
_SOLE_CTX_PATTERN   = re.compile(r"^\{\{([^}]+)\}\}$")

# Inline patterns (for substitution inside a larger string)
_STEP_PATTERN = re.compile(r"\{\{step_(\d+)\.result\.([^}]+)\}\}")
_ARR_PATTERN  = re.compile(r"\{\{step_(\d+)\.result\[(\d+)\]\}\}")
_CTX_PATTERN  = re.compile(r"\{\{([^}]+)\}\}")


class ContextManager:
    """
    In-memory key-value store for agent context sharing.
    Supports template variable resolution like {{step_1.result.path}}.

    Key behaviour
    -------------
    When an argument value is EXACTLY one template (e.g. "{{step_4.result.table_data}}"),
    the raw Python object (list, dict, …) is returned without stringification.
    When a template is embedded inside a longer string (e.g. "Report_{{current_date}}.docx"),
    the value is converted to str and substituted inline.
    """

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._step_results: Dict[int, Dict[str, Any]] = {}  # step_order -> result data
        # Pre-populate built-in paths
        self._store["output_dir"] = str(Path.home() / "Desktop")
        self._store["desktop"] = str(Path.home() / "Desktop")
        self._store["downloads"] = str(Path.home() / "Downloads")
        self._store["documents"] = str(Path.home() / "Documents")

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

    # ─────────────────────────────────────────
    # Public resolution API
    # ─────────────────────────────────────────

    def resolve_template(self, value: Any) -> Any:
        """
        Resolve {{step_N.result.key}} template variables.

        - If `value` is a string containing exactly one template expression and
          nothing else, the raw Python object is returned (preserving list/dict types).
        - If `value` is a string with the template embedded among other text,
          the template is replaced by str(resolved_value).
        - Non-string values (dict, list) are recursively resolved.
        """
        if isinstance(value, str):
            return self._resolve_value(value)
        elif isinstance(value, dict):
            return {k: self.resolve_template(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve_template(item) for item in value]
        return value

    def resolve_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve all template variables in a tool's argument dict."""
        return {k: self.resolve_template(v) for k, v in arguments.items()}

    # ─────────────────────────────────────────
    # Internal resolution
    # ─────────────────────────────────────────

    def _resolve_value(self, text: str) -> Any:
        """
        If `text` is solely a single template expression, return the raw value.
        Otherwise fall through to inline string substitution.
        """
        from datetime import date as _date, datetime as _dt

        # ── Whole-value: {{step_N.result.field}} ──────────────────────────
        m = _SOLE_STEP_PATTERN.match(text)
        if m:
            step_n = int(m.group(1))
            field_path = m.group(2).split(".")
            result = self._step_results.get(step_n, {})
            value = self._nested_get(result, field_path)
            if value is not None:
                # Single-item list → unwrap to scalar (e.g. sheet names list)
                if isinstance(value, list) and len(value) == 1:
                    return value[0]
                return value
            return text  # unresolved — leave as-is

        # ── Whole-value: {{step_N.result[0]}} ────────────────────────────
        m = _SOLE_ARR_PATTERN.match(text)
        if m:
            step_n = int(m.group(1))
            idx = int(m.group(2))
            result = self._step_results.get(step_n)
            if isinstance(result, list) and idx < len(result):
                return result[idx]
            if isinstance(result, dict):
                for list_key in ("sheets", "files", "rows", "items", "groups", "table_data"):
                    lst = result.get(list_key)
                    if isinstance(lst, list) and idx < len(lst):
                        return lst[idx]
            return text

        # ── Whole-value: {{context_key}} ─────────────────────────────────
        m = _SOLE_CTX_PATTERN.match(text)
        if m:
            key = m.group(1).strip()
            value = self._resolve_builtin(key)
            if value is not None:
                return value
            return text  # unresolved

        # ── Inline substitution inside a larger string ────────────────────
        return self._resolve_string(text)

    def _resolve_string(self, text: str) -> str:
        """Replace template patterns inside a larger string (returns str)."""
        from datetime import date as _date

        # {{step_N.result.field}}
        for match in _STEP_PATTERN.finditer(text):
            step_n = int(match.group(1))
            field_path = match.group(2).split(".")
            result = self._step_results.get(step_n, {})
            value = self._nested_get(result, field_path)
            if value is not None:
                if isinstance(value, list):
                    value = value[0] if len(value) == 1 else ", ".join(str(v) for v in value)
                text = text.replace(match.group(0), str(value))

        # {{step_N.result[0]}}
        for match in _ARR_PATTERN.finditer(text):
            step_n = int(match.group(1))
            idx = int(match.group(2))
            result = self._step_results.get(step_n)
            value = None
            if isinstance(result, list) and idx < len(result):
                value = result[idx]
            elif isinstance(result, dict):
                for list_key in ("sheets", "files", "rows", "items", "groups", "table_data"):
                    lst = result.get(list_key)
                    if isinstance(lst, list) and idx < len(lst):
                        value = lst[idx]
                        break
            if value is not None:
                text = text.replace(match.group(0), str(value))

        # {{context_key}}
        for match in _CTX_PATTERN.finditer(text):
            key = match.group(1).strip()
            value = self._resolve_builtin(key)
            if value is not None:
                text = text.replace(match.group(0), str(value))

        return text

    def _resolve_builtin(self, key: str) -> Any:
        """Return built-in dynamic values or stored context values.

        Also supports dot-notation keys like 'excel_group_by.table_data'
        where 'excel_group_by' is stored as a dict in the context.
        """
        from datetime import date as _date, datetime as _dt
        if key == "current_date":
            return _date.today().strftime("%Y-%m-%d")
        if key == "current_datetime":
            return _dt.now().strftime("%Y-%m-%d_%H%M%S")
        if key == "output_dir":
            return self._store.get("output_dir", str(Path.home() / "Desktop"))
        if key == "desktop":
            return str(Path.home() / "Desktop")
        if key == "downloads":
            return str(Path.home() / "Downloads")
        if key == "documents":
            return str(Path.home() / "Documents")

        # Support dot-notation: "excel_group_by.table_data"
        # → look up self._store["excel_group_by"]["table_data"]
        if "." in key:
            parts = key.split(".", 1)
            root = self._store.get(parts[0])
            if isinstance(root, dict):
                value = root.get(parts[1])
                if value is not None:
                    return value

        return self._store.get(key)

    def _nested_get(self, data: Any, keys: List[str]) -> Any:
        """Get a nested value from a dict/list using a list of key/index segments."""
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key)
            elif isinstance(data, list):
                try:
                    data = data[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return data

    def clear(self):
        """Clear step results and user context, but keep built-in paths."""
        self._step_results.clear()
        builtins = {k: self._store[k] for k in ("output_dir", "desktop", "downloads", "documents") if k in self._store}
        self._store.clear()
        self._store.update(builtins)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._store)

    def update_from_dict(self, data: Dict[str, Any]):
        for k, v in data.items():
            self.set(k, v)
