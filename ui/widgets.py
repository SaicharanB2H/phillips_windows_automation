"""
Custom reusable PySide6 widgets for the Desktop Automation Agent UI.
Includes chat bubbles, step cards, agent badges, toast notifications, etc.
"""
from __future__ import annotations

import textwrap
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, QSize,
    QTimer, Qt, Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget,
)

from ui.styles import COLORS, get_agent_color, get_agent_icon, get_status_color, get_status_icon


# ─────────────────────────────────────────────
# Utility: Add Drop Shadow
# ─────────────────────────────────────────────

def add_shadow(widget: QWidget, blur: int = 16, opacity: float = 0.4):
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, 2)
    shadow.setColor(QColor(0, 0, 0, int(255 * opacity)))
    widget.setGraphicsEffect(shadow)


# ─────────────────────────────────────────────
# Horizontal Divider
# ─────────────────────────────────────────────

class HDivider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background: {COLORS['border']}; border: none;")


# ─────────────────────────────────────────────
# Section Header Label
# ─────────────────────────────────────────────

class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; "
            f"font-weight: 700; letter-spacing: 1px;"
        )


# ─────────────────────────────────────────────
# Chat Bubble (User & Assistant)
# ─────────────────────────────────────────────

class ChatBubble(QFrame):
    """A single chat message bubble — user or assistant."""

    copy_requested = Signal(str)

    def __init__(self, content: str, role: str = "user",
                 timestamp: str = "", parent=None):
        super().__init__(parent)
        self._content = content
        self._role = role
        self._setup_ui(content, role, timestamp)

    def _setup_ui(self, content: str, role: str, timestamp: str):
        is_user = role == "user"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        # Row layout: avatar + bubble
        row = QHBoxLayout()
        row.setSpacing(10)

        if is_user:
            row.addStretch()

        # Avatar
        avatar = QLabel("👤" if is_user else "🤖")
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {COLORS['bg_tertiary']}; border-radius: 16px; font-size: 16px;"
        )

        # Bubble frame
        bubble = QFrame()
        bubble.setObjectName("bubble_user" if is_user else "bubble_bot")
        bubble.setMaximumWidth(700)
        b_layout = QVBoxLayout(bubble)
        b_layout.setContentsMargins(14, 10, 14, 10)
        b_layout.setSpacing(6)

        # Content label (renders markdown-like formatting)
        text_lbl = QLabel()
        text_lbl.setWordWrap(True)
        text_lbl.setTextFormat(Qt.TextFormat.RichText)
        text_lbl.setText(self._format_content(content))
        text_lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; background: transparent; "
            f"font-size: 13px; line-height: 1.6;"
        )
        text_lbl.setOpenExternalLinks(False)
        b_layout.addWidget(text_lbl)

        # Bottom row: timestamp + copy
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        if timestamp:
            ts_lbl = QLabel(timestamp)
            ts_lbl.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
            )
            meta_row.addWidget(ts_lbl)
        meta_row.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("btn_icon")
        copy_btn.setFixedHeight(20)
        copy_btn.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent; border: none;"
            f"padding: 0 4px;"
        )
        copy_btn.clicked.connect(lambda: self.copy_requested.emit(content))
        meta_row.addWidget(copy_btn)
        b_layout.addLayout(meta_row)

        if not is_user:
            row.addWidget(avatar)
        row.addWidget(bubble)
        if is_user:
            row.addWidget(avatar)
        else:
            row.addStretch()

        layout.addLayout(row)

    def _format_content(self, text: str) -> str:
        """Convert simple markdown to HTML for display."""
        import re
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        # Bullet points
        lines = text.split("\n")
        html_lines = []
        for line in lines:
            if line.startswith("• ") or line.startswith("- "):
                line = f"&nbsp;&nbsp;{line}"
            html_lines.append(line)
        text = "<br>".join(html_lines)
        return text


# ─────────────────────────────────────────────
# Step Execution Card
# ─────────────────────────────────────────────

class StepCard(QFrame):
    """Displays a single plan step with status, agent badge, and timing."""

    retry_requested = Signal(str)   # step_id

    def __init__(self, step_id: str, order: int, title: str,
                 description: str, agent: str, parent=None):
        super().__init__(parent)
        self._step_id = step_id
        self._agent = agent
        self._status = "pending"
        self.setObjectName("step_card")
        self.setMinimumHeight(72)
        self._setup_ui(order, title, description, agent)

    def _setup_ui(self, order, title, description, agent):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # Status indicator dot
        self._status_dot = QLabel("⏳")
        self._status_dot.setFixedSize(24, 24)
        self._status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_dot.setStyleSheet("font-size: 14px; background: transparent;")
        layout.addWidget(self._status_dot)

        # Step number
        order_lbl = QLabel(f"{order:02d}")
        order_lbl.setFixedWidth(28)
        order_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; "
            f"font-weight: 700; background: transparent;"
        )
        layout.addWidget(order_lbl)

        # Content
        content_col = QVBoxLayout()
        content_col.setSpacing(2)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 13px; "
            f"font-weight: 600; background: transparent;"
        )
        content_col.addWidget(self._title_lbl)

        self._desc_lbl = QLabel(description)
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 11px; background: transparent;"
        )
        content_col.addWidget(self._desc_lbl)

        # Error label (hidden initially)
        self._error_lbl = QLabel()
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(
            f"color: {COLORS['accent_red']}; font-size: 11px; background: transparent;"
        )
        self._error_lbl.hide()
        content_col.addWidget(self._error_lbl)

        layout.addLayout(content_col, 1)

        # Right column: agent badge + duration
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        agent_badge = QLabel(f"{get_agent_icon(agent)} {agent.upper()}")
        agent_badge.setStyleSheet(
            f"color: {get_agent_color(agent)}; font-size: 10px; "
            f"font-weight: 700; background: transparent; letter-spacing: 0.5px;"
        )
        agent_badge.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(agent_badge)

        self._duration_lbl = QLabel("")
        self._duration_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
        )
        self._duration_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._duration_lbl)

        self._retry_btn = QPushButton("Retry")
        self._retry_btn.setObjectName("btn_icon")
        self._retry_btn.setFixedHeight(22)
        self._retry_btn.setStyleSheet(
            f"color: {COLORS['accent_orange']}; font-size: 10px; "
            f"background: transparent; border: 1px solid {COLORS['accent_orange']}; "
            f"border-radius: 4px; padding: 2px 6px;"
        )
        self._retry_btn.clicked.connect(lambda: self.retry_requested.emit(self._step_id))
        self._retry_btn.hide()
        right_col.addWidget(self._retry_btn)

        layout.addLayout(right_col)

    def set_status(self, status: str, error: str = None, duration_s: float = None):
        """Update the card's visual status."""
        self._status = status
        icon = get_status_icon(status)
        color = get_status_color(status)

        self._status_dot.setText(icon)
        self._status_dot.setStyleSheet(
            f"font-size: 14px; color: {color}; background: transparent;"
        )

        # Update frame border color
        obj_map = {
            "running": "step_card_running",
            "success": "step_card_success",
            "failed":  "step_card_failed",
        }
        self.setObjectName(obj_map.get(status, "step_card"))
        self.setStyle(self.style())  # Force style refresh

        if error:
            self._error_lbl.setText(f"Error: {error}")
            self._error_lbl.show()
            self._retry_btn.show()
        else:
            self._error_lbl.hide()
            self._retry_btn.hide()

        if duration_s is not None:
            self._duration_lbl.setText(f"{duration_s:.1f}s")


# ─────────────────────────────────────────────
# Agent Status Badge (for sidebar/header)
# ─────────────────────────────────────────────

class AgentBadge(QFrame):
    """Compact badge showing an agent's name and current status."""

    def __init__(self, agent_name: str, parent=None):
        super().__init__(parent)
        self._agent = agent_name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        icon = QLabel(get_agent_icon(agent_name))
        icon.setStyleSheet("background: transparent; font-size: 14px;")
        layout.addWidget(icon)

        name_lbl = QLabel(agent_name.replace("_", " ").title())
        name_lbl.setStyleSheet(
            f"color: {get_agent_color(agent_name)}; font-size: 11px; "
            f"font-weight: 600; background: transparent;"
        )
        layout.addWidget(name_lbl)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 8px; background: transparent;"
        )
        layout.addWidget(self._status_dot)

        self.setStyleSheet(
            f"background: {COLORS['bg_tertiary']}; border-radius: 12px; "
            f"border: 1px solid {COLORS['border']};"
        )

    def set_active(self, active: bool):
        color = get_agent_color(self._agent) if active else COLORS["text_muted"]
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 8px; background: transparent;"
        )
        self._status_dot.setText("●" if active else "○")


# ─────────────────────────────────────────────
# Toast Notification
# ─────────────────────────────────────────────

class ToastNotification(QFrame):
    """Brief pop-up notification that auto-dismisses."""

    def __init__(self, message: str, level: str = "info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(350)

        colors = {
            "info":    COLORS["accent_blue"],
            "success": COLORS["accent_green"],
            "warning": COLORS["accent_orange"],
            "error":   COLORS["accent_red"],
        }
        icons = {"info": "ℹ", "success": "✓", "warning": "⚠", "error": "✗"}
        color = colors.get(level, COLORS["accent_blue"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        icon_lbl = QLabel(icons.get(level, "ℹ"))
        icon_lbl.setStyleSheet(f"color: {color}; font-size: 16px; background: transparent;")
        layout.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 13px; background: transparent;"
        )
        layout.addWidget(msg_lbl, 1)

        self.setStyleSheet(
            f"background: {COLORS['bg_secondary']}; "
            f"border: 1px solid {color}; "
            f"border-left: 3px solid {color}; "
            f"border-radius: 8px;"
        )
        add_shadow(self, blur=20)

        QTimer.singleShot(3500, self.close)

    @staticmethod
    def show_toast(parent: QWidget, message: str, level: str = "info"):
        """Static helper to show a toast anchored to parent's bottom-right."""
        toast = ToastNotification(message, level, parent)
        if parent:
            pr = parent.rect()
            x = pr.right() - toast.width() - 20
            y = pr.bottom() - 80
            toast.move(parent.mapToGlobal(toast.pos()) if parent.window() else toast.pos())
        toast.show()
        return toast


# ─────────────────────────────────────────────
# Loading Spinner
# ─────────────────────────────────────────────

class LoadingSpinner(QWidget):
    """Animated spinning indicator."""

    def __init__(self, size: int = 32, color: str = None, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._color = QColor(color or COLORS["accent_blue"])
        self._size = size
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._running = False

    def start(self):
        self._running = True
        self._timer.start(30)
        self.show()

    def stop(self):
        self._running = False
        self._timer.stop()
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event):
        if not self._running:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self._size / 2, self._size / 2)
        painter.rotate(self._angle)

        for i in range(8):
            painter.rotate(45)
            opacity = (i + 1) / 8.0
            color = QColor(self._color)
            color.setAlphaF(opacity)
            pen = QPen(color, 2.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            r = self._size // 2 - 4
            painter.drawLine(0, -r + 4, 0, -r)
        painter.end()


# ─────────────────────────────────────────────
# Artifact Card (Generated Files)
# ─────────────────────────────────────────────

class ArtifactCard(QFrame):
    """Display a generated file artifact with open buttons."""

    open_file_requested    = Signal(str)   # file path
    open_folder_requested  = Signal(str)   # folder path

    def __init__(self, name: str, path: str, artifact_type: str,
                 size_str: str = "", description: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("artifact_card")
        self._path = path
        self._setup_ui(name, path, artifact_type, size_str, description)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _setup_ui(self, name, path, atype, size_str, description):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        icons = {
            "excel": "📊", "word": "📝", "pdf": "📄",
            "csv": "📋", "image": "🖼", "text": "📃", "other": "📎",
        }
        icon_lbl = QLabel(icons.get(atype.lower(), "📎"))
        icon_lbl.setStyleSheet("font-size: 22px; background: transparent;")
        icon_lbl.setFixedWidth(32)
        layout.addWidget(icon_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 12px; "
            f"font-weight: 600; background: transparent;"
        )
        info_col.addWidget(name_lbl)

        meta = size_str
        if description:
            meta = f"{description}  {size_str}".strip()
        if meta:
            meta_lbl = QLabel(meta)
            meta_lbl.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
            )
            info_col.addWidget(meta_lbl)

        layout.addLayout(info_col, 1)

        # Buttons
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        open_btn = QPushButton("Open")
        open_btn.setFixedSize(54, 22)
        open_btn.setStyleSheet(
            f"color: {COLORS['accent_blue']}; font-size: 10px; background: transparent; "
            f"border: 1px solid {COLORS['accent_blue']}; border-radius: 4px; padding: 0;"
        )
        open_btn.clicked.connect(lambda: self.open_file_requested.emit(self._path))
        btn_col.addWidget(open_btn)

        folder_btn = QPushButton("Folder")
        folder_btn.setFixedSize(54, 22)
        folder_btn.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 10px; background: transparent; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 0;"
        )
        folder_btn.clicked.connect(lambda: self.open_folder_requested.emit(self._path))
        btn_col.addWidget(folder_btn)

        layout.addLayout(btn_col)
