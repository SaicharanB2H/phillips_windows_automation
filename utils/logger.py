"""
Centralized logging for the Desktop Automation Agent.
Provides file logging, console logging, and UI-safe signal emission.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Signal

# ─────────────────────────────────────────────
# Log Record Storage (for UI log panel)
# ─────────────────────────────────────────────

class LogEntry:
    """Structured log entry for display in the UI."""
    def __init__(self, level: str, message: str, agent: str = "system",
                 timestamp: Optional[datetime] = None):
        self.level = level
        self.message = message
        self.agent = agent
        self.timestamp = timestamp or datetime.utcnow()

    def formatted(self) -> str:
        ts = self.timestamp.strftime("%H:%M:%S.%f")[:-3]
        return f"[{ts}] [{self.level:8}] [{self.agent:12}] {self.message}"


# ─────────────────────────────────────────────
# Qt Signal Bridge (thread-safe UI updates)
# ─────────────────────────────────────────────

class LogSignalBridge(QObject):
    """Emits log entries so the UI thread can update the log panel safely."""
    log_entry = Signal(object)  # LogEntry


_signal_bridge: Optional[LogSignalBridge] = None


def get_signal_bridge() -> LogSignalBridge:
    global _signal_bridge
    if _signal_bridge is None:
        _signal_bridge = LogSignalBridge()
    return _signal_bridge


# ─────────────────────────────────────────────
# Custom Handler that forwards to UI
# ─────────────────────────────────────────────

class UILogHandler(logging.Handler):
    """Python logging handler that forwards records to the Qt signal bridge."""

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord):
        try:
            entry = LogEntry(
                level=record.levelname,
                message=self.format(record),
                agent=getattr(record, "agent", record.name.split(".")[-1]),
                timestamp=datetime.fromtimestamp(record.created),
            )
            get_signal_bridge().log_entry.emit(entry)
        except Exception:
            pass  # Never let logging crash the app


# ─────────────────────────────────────────────
# Logger Factory
# ─────────────────────────────────────────────

_initialized = False
_log_entries: List[LogEntry] = []
_max_entries = 2000


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """Configure root logging. Call once at startup."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler (rich-formatted)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)-20s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console)

    # File handler (rotating)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
        ))
        root.addHandler(file_handler)

    # UI handler
    root.addHandler(UILogHandler())

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def get_logger(name: str, agent: str = "") -> logging.LoggerAdapter:
    """Get a logger adapter that automatically tags entries with agent name."""
    logger = logging.getLogger(name)
    return logging.LoggerAdapter(logger, {"agent": agent or name.split(".")[-1]})


def get_log_entries() -> List[LogEntry]:
    """Return buffered log entries for display."""
    return list(_log_entries)


# Connect signal bridge to buffer
def _buffer_entry(entry: LogEntry):
    _log_entries.append(entry)
    if len(_log_entries) > _max_entries:
        _log_entries.pop(0)


# Wire up buffering — done lazily so QApplication exists first
def init_ui_logging():
    get_signal_bridge().log_entry.connect(_buffer_entry)
