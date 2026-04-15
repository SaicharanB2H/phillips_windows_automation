"""
Custom reusable PySide6 widgets for the Desktop Automation Agent UI.
All icons use the centralized IconManager (Lucide SVG system).
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QSize,
    QTimer, Qt, Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from icons.icon_manager import (
    IconButton, StatusIcon, get_icon, get_pixmap,
    ICON_COLOR_DEFAULT, ICON_COLOR_HOVER, ICON_COLOR_SUCCESS,
    ICON_COLOR_ERROR, ICON_COLOR_WARNING, ICON_COLOR_MUTED,
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

        row = QHBoxLayout()
        row.setSpacing(10)

        if is_user:
            row.addStretch()

        # Avatar using SVG icon
        avatar = QLabel()
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {COLORS['bg_tertiary']}; border-radius: 16px;"
        )
        icon_name = "bot" if not is_user else "cpu"
        icon_color = COLORS["accent_blue"] if not is_user else COLORS["text_secondary"]
        px = get_pixmap(icon_name, 16, icon_color)
        avatar.setPixmap(px)

        # Bubble frame
        bubble = QFrame()
        bubble.setObjectName("bubble_user" if is_user else "bubble_bot")
        bubble.setMaximumWidth(700)
        b_layout = QVBoxLayout(bubble)
        b_layout.setContentsMargins(14, 10, 14, 10)
        b_layout.setSpacing(6)

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

        # Bottom row: timestamp + copy icon button
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        if timestamp:
            ts_lbl = QLabel(timestamp)
            ts_lbl.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
            )
            meta_row.addWidget(ts_lbl)
        meta_row.addStretch()

        copy_btn = IconButton(
            "copy", size=13, color=COLORS["text_muted"],
            hover_color=ICON_COLOR_HOVER, btn_size=22,
            tooltip="Copy message", circular=False,
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
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        lines = text.split("\n")
        html_lines = []
        for line in lines:
            if line.startswith("• ") or line.startswith("- "):
                line = f"&nbsp;&nbsp;{line}"
            html_lines.append(line)
        return "<br>".join(html_lines)


# ─────────────────────────────────────────────
# Step Execution Card
# ─────────────────────────────────────────────

class StepCard(QFrame):
    """Displays a single plan step with status icon, agent badge, and timing."""

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

        # Status icon (SVG, updates with status)
        self._status_icon = StatusIcon("pending", size=18)
        layout.addWidget(self._status_icon)

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

        self._error_lbl = QLabel()
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setStyleSheet(
            f"color: {COLORS['accent_red']}; font-size: 11px; background: transparent;"
        )
        self._error_lbl.hide()
        content_col.addWidget(self._error_lbl)

        layout.addLayout(content_col, 1)

        # Right column: agent icon badge + duration
        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Agent badge with SVG icon
        agent_row = QHBoxLayout()
        agent_row.setSpacing(4)
        agent_row.setAlignment(Qt.AlignmentFlag.AlignRight)

        agent_icon_name = get_agent_icon(agent)
        agent_color = get_agent_color(agent)
        agent_px = get_pixmap(agent_icon_name, 12, agent_color)
        agent_icon_lbl = QLabel()
        agent_icon_lbl.setPixmap(agent_px)
        agent_icon_lbl.setFixedSize(14, 14)
        agent_icon_lbl.setStyleSheet("background: transparent;")

        agent_name_lbl = QLabel(agent.upper())
        agent_name_lbl.setStyleSheet(
            f"color: {agent_color}; font-size: 10px; "
            f"font-weight: 700; background: transparent; letter-spacing: 0.5px;"
        )
        agent_row.addWidget(agent_icon_lbl)
        agent_row.addWidget(agent_name_lbl)
        right_col.addLayout(agent_row)

        self._duration_lbl = QLabel("")
        self._duration_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
        )
        self._duration_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._duration_lbl)

        self._retry_btn = IconButton(
            "refresh-cw", size=13, color=COLORS["accent_orange"],
            hover_color="#E8A020", btn_size=60, circular=False,
            text=" Retry",
        )
        self._retry_btn.setStyleSheet(
            f"QPushButton {{ color: {COLORS['accent_orange']}; font-size: 10px; "
            f"background: transparent; border: 1px solid {COLORS['accent_orange']}; "
            f"border-radius: 4px; padding: 2px 6px; }}"
            f"QPushButton:hover {{ background: rgba(210, 153, 34, 0.15); }}"
        )
        self._retry_btn.clicked.connect(lambda: self.retry_requested.emit(self._step_id))
        self._retry_btn.hide()
        right_col.addWidget(self._retry_btn)

        layout.addLayout(right_col)

    def set_status(self, status: str, error: str = None, duration_s: float = None):
        """Update the card's visual status."""
        self._status = status
        self._status_icon.set_status(status)

        obj_map = {
            "running": "step_card_running",
            "success": "step_card_success",
            "failed":  "step_card_failed",
        }
        self.setObjectName(obj_map.get(status, "step_card"))
        self.setStyle(self.style())

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
# Agent Status Badge
# ─────────────────────────────────────────────

class AgentBadge(QFrame):
    """Compact badge showing an agent's name, SVG icon, and status dot."""

    def __init__(self, agent_name: str, parent=None):
        super().__init__(parent)
        self._agent = agent_name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 10, 4)
        layout.setSpacing(6)

        # SVG agent icon
        icon_name = get_agent_icon(agent_name)
        agent_color = get_agent_color(agent_name)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setPixmap(get_pixmap(icon_name, 14, ICON_COLOR_MUTED))
        icon_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(icon_lbl)
        self._icon_lbl = icon_lbl

        name_lbl = QLabel(agent_name.replace("_", " ").title())
        name_lbl.setStyleSheet(
            f"color: {ICON_COLOR_MUTED}; font-size: 11px; "
            f"font-weight: 600; background: transparent;"
        )
        layout.addWidget(name_lbl)
        self._name_lbl = name_lbl
        self._agent_color = agent_color

        # Status dot — CSS circle, no emoji
        self._dot = QLabel()
        self._dot.setFixedSize(7, 7)
        self._dot.setStyleSheet(
            f"background: {COLORS['text_muted']}; border-radius: 3px;"
        )
        layout.addWidget(self._dot)

        self.setStyleSheet(
            f"background: {COLORS['bg_tertiary']}; border-radius: 12px; "
            f"border: 1px solid {COLORS['border']};"
        )

    def set_active(self, active: bool):
        icon_name = get_agent_icon(self._agent)
        color = self._agent_color if active else ICON_COLOR_MUTED
        self._icon_lbl.setPixmap(get_pixmap(icon_name, 14, color))
        self._name_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        dot_color = color if active else COLORS["text_muted"]
        self._dot.setStyleSheet(
            f"background: {dot_color}; border-radius: 3px;"
        )


# ─────────────────────────────────────────────
# Toast Notification
# ─────────────────────────────────────────────

class ToastNotification(QFrame):
    """Brief pop-up notification with SVG icon that auto-dismisses."""

    _ICON_MAP = {
        "info":    ("info",          ICON_COLOR_HOVER),
        "success": ("check-circle",  ICON_COLOR_SUCCESS),
        "warning": ("alert-circle",  ICON_COLOR_WARNING),
        "error":   ("x-circle",      ICON_COLOR_ERROR),
    }

    def __init__(self, message: str, level: str = "info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(350)

        icon_name, color = self._ICON_MAP.get(level, ("info", ICON_COLOR_HOVER))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # SVG icon
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(20, 20)
        icon_lbl.setPixmap(get_pixmap(icon_name, 18, color))
        icon_lbl.setStyleSheet("background: transparent;")
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
        toast = ToastNotification(message, level, parent)
        toast.show()
        return toast


# ─────────────────────────────────────────────
# Loading Spinner
# ─────────────────────────────────────────────

class LoadingSpinner(QWidget):
    """Animated spinning indicator (custom painted arcs)."""

    def __init__(self, size: int = 32, color: str = None, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._color = QColor(color or COLORS["accent_blue"])
        self._size = size
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._running = False
        self.hide()

    def start(self):
        self._running = True
        self._timer.start(28)
        self.show()

    def stop(self):
        self._running = False
        self._timer.stop()
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 14) % 360
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
            r = self._size // 2 - 3
            painter.drawLine(0, -r + 4, 0, -r)
        painter.end()


# ─────────────────────────────────────────────
# Artifact Card (Generated Files)
# ─────────────────────────────────────────────

class ArtifactCard(QFrame):
    """Display a generated file artifact with SVG type icon and action buttons."""

    open_file_requested   = Signal(str)
    open_folder_requested = Signal(str)

    # Map artifact type → (lucide icon name, color)
    _TYPE_ICONS: dict[str, tuple[str, str]] = {
        "excel":  ("file-spreadsheet", COLORS["accent_teal"]),
        "word":   ("file-text",        COLORS["accent_yellow"]),
        "pdf":    ("file",             COLORS["accent_red"]),
        "csv":    ("file-spreadsheet", COLORS["accent_green"]),
        "image":  ("image",            COLORS["accent_purple"]),
        "text":   ("file-text",        COLORS["text_secondary"]),
        "other":  ("file",             COLORS["text_muted"]),
    }

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

        # File type SVG icon
        icon_name, icon_color = self._TYPE_ICONS.get(
            atype.lower(), ("file", ICON_COLOR_MUTED)
        )
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(get_pixmap(icon_name, 22, icon_color))
        icon_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(icon_lbl)

        # File info
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 12px; "
            f"font-weight: 600; background: transparent;"
        )
        info_col.addWidget(name_lbl)

        meta = f"{description}  {size_str}".strip() if description else size_str
        if meta:
            meta_lbl = QLabel(meta)
            meta_lbl.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
            )
            info_col.addWidget(meta_lbl)

        layout.addLayout(info_col, 1)

        # Action buttons
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        open_btn = IconButton(
            "external-link", size=13,
            color=COLORS["accent_blue"], hover_color=ICON_COLOR_HOVER,
            btn_size=54, circular=False, text=" Open",
        )
        open_btn.setStyleSheet(
            f"QPushButton {{ color: {COLORS['accent_blue']}; font-size: 10px; "
            f"background: transparent; border: 1px solid {COLORS['accent_blue']}; "
            f"border-radius: 4px; padding: 2px 4px; }}"
            f"QPushButton:hover {{ background: rgba(56, 139, 253, 0.15); }}"
        )
        open_btn.clicked.connect(lambda: self.open_file_requested.emit(self._path))
        btn_col.addWidget(open_btn)

        folder_btn = IconButton(
            "folder", size=13,
            color=COLORS["text_secondary"], hover_color=ICON_COLOR_HOVER,
            btn_size=54, circular=False, text=" Folder",
        )
        folder_btn.setStyleSheet(
            f"QPushButton {{ color: {COLORS['text_secondary']}; font-size: 10px; "
            f"background: transparent; border: 1px solid {COLORS['border']}; "
            f"border-radius: 4px; padding: 2px 4px; }}"
            f"QPushButton:hover {{ background: {COLORS['bg_hover']}; "
            f"border-color: {COLORS['border_accent']}; }}"
        )
        folder_btn.clicked.connect(lambda: self.open_folder_requested.emit(self._path))
        btn_col.addWidget(folder_btn)

        layout.addLayout(btn_col)
