"""
Base Agent — shared interface for all specialized agents.

Every agent:
- Registers tools with schema validation
- Executes tools and returns structured ToolResult
- Logs all actions with timestamps
- Supports dry-run simulation
- Reports to the UI via signals
"""
from __future__ import annotations

import os
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from models.schemas import (
    AgentType, StepStatus, ToolCall, ToolResult, RiskLevel
)
from utils.logger import get_logger


# ─────────────────────────────────────────────
# Agent Signal Bridge (thread-safe UI updates)
# ─────────────────────────────────────────────

class AgentSignalBridge(QObject):
    """Signals emitted by agents for UI updates."""
    tool_started   = Signal(str, str)       # agent_name, tool_name
    tool_completed = Signal(str, str, bool) # agent_name, tool_name, success
    status_changed = Signal(str, str)       # agent_name, status_message
    log_message    = Signal(str, str, str)  # agent_name, level, message


_agent_bridge: Optional[AgentSignalBridge] = None


def get_agent_bridge() -> AgentSignalBridge:
    global _agent_bridge
    if _agent_bridge is None:
        _agent_bridge = AgentSignalBridge()
    return _agent_bridge


# ─────────────────────────────────────────────
# Tool Registration Schema
# ─────────────────────────────────────────────

class ToolSchema:
    """Metadata for a registered tool."""
    def __init__(
        self,
        name: str,
        description: str,
        fn: Callable,
        required_args: List[str] = None,
        optional_args: List[str] = None,
        risk_level: RiskLevel = RiskLevel.LOW,
    ):
        self.name = name
        self.description = description
        self.fn = fn
        self.required_args = required_args or []
        self.optional_args = optional_args or []
        self.risk_level = risk_level


# ─────────────────────────────────────────────
# Base Agent
# ─────────────────────────────────────────────

class BaseAgent(ABC):
    """
    Abstract base class for all automation agents.
    Subclasses must implement _register_tools() and name property.
    """

    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type
        self._tools: Dict[str, ToolSchema] = {}
        self._dry_run = os.getenv("EXECUTION_MODE", "safe") == "dry_run"
        self._logger = get_logger(f"agents.{agent_type.value}", agent_type.value)
        self._bridge = get_agent_bridge()
        self._execution_log: List[Dict[str, Any]] = []
        self._register_tools()

    @abstractmethod
    def _register_tools(self):
        """Register all tools this agent exposes."""
        ...

    def register_tool(
        self,
        name: str,
        fn: Callable,
        description: str = "",
        required_args: List[str] = None,
        risk_level: RiskLevel = RiskLevel.LOW,
    ):
        """Register a callable as a named tool."""
        self._tools[name] = ToolSchema(
            name=name,
            fn=fn,
            description=description,
            required_args=required_args or [],
            risk_level=risk_level,
        )

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def _resolve_tool_name(self, name: str) -> str:
        """
        Normalize LLM-generated tool names to registered names.
        Handles common LLM mistakes like 'file.X' vs 'files.X'.
        Uses multiple fallback strategies to maximize match rate.
        """
        # Strip any accidental whitespace from LLM output
        name = name.strip()

        # 1. Exact match
        if name in self._tools:
            return name

        # 2. Explicit prefix variations
        candidates = [
            name.replace("file.", "files."),         # file.search → files.search
            name.replace("files.", "file."),          # files.search → file.search
            name.replace("ui.", "ui_automation."),    # ui.click → ui_automation.click
            name.replace("ui_automation.", "ui."),
        ]
        for candidate in candidates:
            if candidate in self._tools:
                self._logger.info(f"Tool resolved by prefix: '{name}' → '{candidate}'")
                return candidate

        # 3. Suffix-based fallback — match by the part after the first dot
        #    e.g. "file.search" → suffix "search" → finds "files.search"
        if "." in name:
            suffix = name.split(".", 1)[1]  # "search" from "file.search"
            for registered in self._tools:
                if registered.endswith("." + suffix):
                    self._logger.info(f"Tool resolved by suffix: '{name}' → '{registered}'")
                    return registered

        # 4. Case-insensitive exact match
        name_lower = name.lower()
        for registered in self._tools:
            if registered.lower() == name_lower:
                self._logger.info(f"Tool resolved by case: '{name}' → '{registered}'")
                return registered

        # Nothing matched — log all registered tools to help diagnose
        self._logger.error(
            f"Cannot resolve tool '{name}'. "
            f"Registered tools: {sorted(self._tools.keys())}"
        )
        return name

    def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a tool by name with the given arguments.
        Validates args, handles dry-run, logs everything.
        """
        name = self._resolve_tool_name(tool_call.tool_name)
        args = tool_call.arguments
        start = time.time()

        self._bridge.tool_started.emit(self.agent_type.value, name)
        self._logger.info(f"→ {name}({args})")

        if name not in self._tools:
            return self._make_error(tool_call, f"Unknown tool: {name}", start)

        schema = self._tools[name]

        # Validate required arguments
        missing = [r for r in schema.required_args if r not in args]
        if missing:
            return self._make_error(
                tool_call,
                f"Missing required arguments for {name}: {missing}",
                start,
            )

        # Dry-run simulation
        if self._dry_run:
            self._logger.info(f"  [DRY RUN] Would execute: {name}")
            result = ToolResult(
                tool_call_id=tool_call.id,
                tool_name=name,
                success=True,
                data={"dry_run": True, "simulated": f"Would call {name} with {args}"},
                duration_ms=(time.time() - start) * 1000,
            )
            self._bridge.tool_completed.emit(self.agent_type.value, name, True)
            return result

        # Execute
        try:
            data = schema.fn(**args)
            duration = (time.time() - start) * 1000
            self._logger.info(f"  ✓ {name} completed in {duration:.0f}ms")
            self._bridge.tool_completed.emit(self.agent_type.value, name, True)

            result = ToolResult(
                tool_call_id=tool_call.id,
                tool_name=name,
                success=True,
                data=data,
                duration_ms=duration,
            )
            self._log_execution(name, args, result)
            return result

        except Exception as e:
            tb = traceback.format_exc()
            self._logger.error(f"  ✗ {name} failed: {e}\n{tb}")
            self._bridge.tool_completed.emit(self.agent_type.value, name, False)
            return self._make_error(tool_call, str(e), start, tb)

    def _make_error(
        self, tool_call: ToolCall, message: str,
        start: float, tb: str = None
    ) -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.tool_name,
            success=False,
            error=message,
            duration_ms=(time.time() - start) * 1000,
        )

    def _log_execution(self, tool_name: str, args: Dict, result: ToolResult):
        """Append to internal execution log."""
        self._execution_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "tool": tool_name,
            "args": args,
            "success": result.success,
            "error": result.error,
            "duration_ms": result.duration_ms,
        })

    def emit_status(self, message: str):
        """Emit a status update visible in the UI."""
        self._bridge.status_changed.emit(self.agent_type.value, message)

    def get_execution_log(self) -> List[Dict[str, Any]]:
        return list(self._execution_log)
