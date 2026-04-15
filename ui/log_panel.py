"""
Log Panel — real-time timestamped execution log display.
Thread-safe updates via signal connection to the logger bridge.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QTextCursor, QColor
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from icons.icon_manager import IconButton
from ui.styles import COLORS
from ui.widgets import SectionLabel, HDivider
from utils.logger import get_signal_bridge, LogEntry


class LogPanel(QWidget):
    """Scrollable log panel with level filtering and copy/clear controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll = True
        self._paused = False
        self._filters = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ───────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)
        h_layout.setSpacing(8)

        h_layout.addWidget(SectionLabel("Execution Log"))
        h_layout.addStretch()

        # Level filter checkboxes
        for level, color in [
            ("INFO", COLORS["accent_blue"]),
            ("WARNING", COLORS["accent_orange"]),
            ("ERROR", COLORS["accent_red"]),
        ]:
            cb = QCheckBox(level)
            cb.setChecked(True)
            cb.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: 600;"
            )
            cb.stateChanged.connect(lambda state, l=level: self._toggle_filter(l, state))
            h_layout.addWidget(cb)

        # Controls — icon buttons
        _btn_ss = (
            f"QPushButton {{ background: transparent; color: {COLORS['text_secondary']}; "
            f"font-size: 11px; border: none; border-radius: 4px; padding: 2px 8px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; "
            f"color: {COLORS['text_primary']}; }}"
            f"QPushButton:checked {{ color: {COLORS['accent_blue']}; }}"
        )

        self._pause_btn = IconButton(
            icon_name="pause",
            size=12,
            color=COLORS["text_secondary"],
            hover_color=COLORS["text_primary"],
            btn_size=None,
            text="  Pause",
        )
        self._pause_btn.setObjectName("btn_icon")
        self._pause_btn.setFixedHeight(24)
        self._pause_btn.setCheckable(True)
        self._pause_btn.setStyleSheet(_btn_ss)
        self._pause_btn.toggled.connect(self._toggle_pause)
        h_layout.addWidget(self._pause_btn)

        clear_btn = IconButton(
            icon_name="trash",
            size=12,
            color=COLORS["text_secondary"],
            hover_color=COLORS["accent_red"],
            btn_size=None,
            text="  Clear",
        )
        clear_btn.setObjectName("btn_icon")
        clear_btn.setFixedHeight(24)
        clear_btn.setStyleSheet(_btn_ss)
        clear_btn.clicked.connect(self.clear)
        h_layout.addWidget(clear_btn)

        copy_btn = IconButton(
            icon_name="copy",
            size=12,
            color=COLORS["text_secondary"],
            hover_color=COLORS["text_primary"],
            btn_size=None,
            text="  Copy",
        )
        copy_btn.setObjectName("btn_icon")
        copy_btn.setFixedHeight(24)
        copy_btn.setStyleSheet(_btn_ss)
        copy_btn.clicked.connect(self._copy_all)
        h_layout.addWidget(copy_btn)

        layout.addWidget(header)
        layout.addWidget(HDivider())

        # ── Log Text Area ─────────────────────────
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setObjectName("log_view")
        self._log_view.setFont(QFont("Consolas", 11))
        self._log_view.setStyleSheet(
            f"background: {COLORS['bg_primary']}; "
            f"color: {COLORS['text_primary']}; "
            f"border: none; padding: 8px;"
        )
        # Set document max block count to prevent memory issues
        self._log_view.document().setMaximumBlockCount(5000)
        layout.addWidget(self._log_view)

    def _connect_signals(self):
        """Connect to the global logger signal bridge."""
        bridge = get_signal_bridge()
        bridge.log_entry.connect(self._append_entry)

    @Slot(object)
    def _append_entry(self, entry: LogEntry):
        """Append a log entry to the text area (called from any thread via signal)."""
        if self._paused:
            return
        if entry.level not in self._filters:
            return

        level_colors = {
            "DEBUG":    COLORS["text_muted"],
            "INFO":     COLORS["text_primary"],
            "WARNING":  COLORS["accent_orange"],
            "ERROR":    COLORS["accent_red"],
            "CRITICAL": COLORS["accent_red"],
        }
        color = level_colors.get(entry.level, COLORS["text_primary"])

        ts = entry.timestamp.strftime("%H:%M:%S.%f")[:-3]
        agent = f"[{entry.agent:12}]" if entry.agent else ""
        level_str = f"{entry.level:8}"

        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Insert with formatting
        fmt = cursor.charFormat()
        fmt.setForeground(QColor(COLORS["text_muted"]))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{ts} ")

        fmt.setForeground(QColor(color))
        fmt.setFontWeight(700 if entry.level in ("ERROR", "WARNING") else 400)
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{level_str}")

        fmt.setForeground(QColor(COLORS["accent_blue"]))
        fmt.setFontWeight(400)
        cursor.setCharFormat(fmt)
        cursor.insertText(f" {agent} ")

        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(f"{entry.message}\n")

        if self._auto_scroll:
            self._log_view.setTextCursor(cursor)
            self._log_view.ensureCursorVisible()

    def clear(self):
        self._log_view.clear()

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._log_view.toPlainText())

    def _toggle_pause(self, paused: bool):
        self._paused = paused
        self._auto_scroll = not paused
        # Swap icon to reflect state
        self._pause_btn.set_icon_name("play" if paused else "pause")

    def _toggle_filter(self, level: str, state: int):
        if state:
            self._filters.add(level)
        else:
            self._filters.discard(level)

    def append_text(self, text: str, color: str = None):
        """Directly append arbitrary text (for non-logger messages)."""
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor(color or COLORS["text_primary"]))
        cursor.setCharFormat(fmt)
        cursor.insertText(text + "\n")
        if self._auto_scroll:
            self._log_view.setTextCursor(cursor)
            self._log_view.ensureCursorVisible()
