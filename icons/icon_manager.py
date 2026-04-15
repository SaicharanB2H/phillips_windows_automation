"""
Icon Manager — Centralized SVG icon system using Lucide icons.

Features:
- Embedded Lucide-style SVG icons (no external files needed)
- Dynamic color theming via SVG string replacement
- LRU cache for performance
- Size scaling (16, 20, 24, 32px)
- Hover / active / disabled state support
- QIcon and QPixmap generation
- IconButton widget with micro-interactions
"""
from __future__ import annotations

import functools
from typing import Optional

from PySide6.QtCore import QByteArray, QSize, Qt, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton, QWidget

# ─────────────────────────────────────────────
# Theme Colors
# ─────────────────────────────────────────────
ICON_COLOR_DEFAULT  = "#C9D1D9"   # Soft white — default icon
ICON_COLOR_HOVER    = "#4F9DFF"   # Bright blue — hover
ICON_COLOR_ACTIVE   = "#388BFD"   # Accent blue — active/selected
ICON_COLOR_DISABLED = "#484F58"   # Muted — disabled
ICON_COLOR_SUCCESS  = "#3FB950"   # Green — success
ICON_COLOR_ERROR    = "#F85149"   # Red — error
ICON_COLOR_WARNING  = "#D29922"   # Orange — warning
ICON_COLOR_MUTED    = "#8B949E"   # Secondary text

# ─────────────────────────────────────────────
# Lucide SVG Library (embedded, no file I/O)
# All icons: 24x24 viewBox, stroke=currentColor,
# stroke-width=2, round caps & joins
# ─────────────────────────────────────────────
_SVG_HEADER = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
)
_SVG_FOOTER = "</svg>"


def _svg(body: str) -> str:
    return _SVG_HEADER + body + _SVG_FOOTER


ICONS: dict[str, str] = {

    # ── Navigation ─────────────────────────────────────────────────────
    "home": _svg(
        '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<polyline points="9 22 9 12 15 12 15 22"/>'
    ),
    "message-circle": _svg(
        '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
    ),
    "clock": _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<polyline points="12 6 12 12 16 14"/>'
    ),
    "settings": _svg(
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83'
        ' 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1'
        ' 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65'
        ' 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A'
        '1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0'
        ' 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2'
        ' 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65'
        ' 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1'
        ' 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0'
        ' 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0'
        ' 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
    ),
    "cpu": _svg(
        '<rect x="4" y="4" width="16" height="16" rx="2" ry="2"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
        '<line x1="9" y1="1" x2="9" y2="4"/>'
        '<line x1="15" y1="1" x2="15" y2="4"/>'
        '<line x1="9" y1="20" x2="9" y2="23"/>'
        '<line x1="15" y1="20" x2="15" y2="23"/>'
        '<line x1="20" y1="9" x2="23" y2="9"/>'
        '<line x1="20" y1="14" x2="23" y2="14"/>'
        '<line x1="1" y1="9" x2="4" y2="9"/>'
        '<line x1="1" y1="14" x2="4" y2="14"/>'
    ),
    "bot": _svg(
        '<rect x="3" y="11" width="18" height="10" rx="2" ry="2"/>'
        '<circle cx="12" cy="5" r="2"/>'
        '<path d="M12 7v4"/>'
        '<line x1="8" y1="16" x2="8" y2="16"/>'
        '<line x1="16" y1="16" x2="16" y2="16"/>'
    ),
    "layers": _svg(
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/>'
    ),
    "terminal": _svg(
        '<polyline points="4 17 10 11 4 5"/>'
        '<line x1="12" y1="19" x2="20" y2="19"/>'
    ),
    "zap": _svg(
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
    ),

    # ── Actions ────────────────────────────────────────────────────────
    "plus": _svg(
        '<line x1="12" y1="5" x2="12" y2="19"/>'
        '<line x1="5" y1="12" x2="19" y2="12"/>'
    ),
    "plus-circle": _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="8" x2="12" y2="16"/>'
        '<line x1="8" y1="12" x2="16" y2="12"/>'
    ),
    "send": _svg(
        '<line x1="22" y1="2" x2="11" y2="13"/>'
        '<polygon points="22 2 15 22 11 13 2 9 22 2"/>'
    ),
    "play": _svg(
        '<polygon points="5 3 19 12 5 21 5 3"/>'
    ),
    "square": _svg(
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
    ),
    "stop-circle": _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
    ),
    "refresh-cw": _svg(
        '<polyline points="23 4 23 10 17 10"/>'
        '<polyline points="1 20 1 14 7 14"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
    ),
    "trash": _svg(
        '<polyline points="3 6 5 6 21 6"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'
        '<line x1="10" y1="11" x2="10" y2="17"/>'
        '<line x1="14" y1="11" x2="14" y2="17"/>'
    ),
    "pencil": _svg(
        '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>'
        '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>'
    ),
    "copy": _svg(
        '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'
    ),
    "download": _svg(
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" y1="15" x2="12" y2="3"/>'
    ),
    "external-link": _svg(
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
        '<polyline points="15 3 21 3 21 9"/>'
        '<line x1="10" y1="14" x2="21" y2="3"/>'
    ),
    "chevron-right": _svg(
        '<polyline points="9 18 15 12 9 6"/>'
    ),
    "x": _svg(
        '<line x1="18" y1="6" x2="6" y2="18"/>'
        '<line x1="6" y1="6" x2="18" y2="18"/>'
    ),

    # ── Status ─────────────────────────────────────────────────────────
    "check-circle": _svg(
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<polyline points="22 4 12 14.01 9 11.01"/>'
    ),
    "alert-circle": _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="8" x2="12" y2="12"/>'
        '<line x1="12" y1="16" x2="12.01" y2="16"/>'
    ),
    "x-circle": _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="15" y1="9" x2="9" y2="15"/>'
        '<line x1="9" y1="9" x2="15" y2="15"/>'
    ),
    "loader": _svg(
        '<line x1="12" y1="2" x2="12" y2="6"/>'
        '<line x1="12" y1="18" x2="12" y2="22"/>'
        '<line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/>'
        '<line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>'
        '<line x1="2" y1="12" x2="6" y2="12"/>'
        '<line x1="18" y1="12" x2="22" y2="12"/>'
        '<line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/>'
        '<line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>'
    ),
    "info": _svg(
        '<circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="16" x2="12" y2="12"/>'
        '<line x1="12" y1="8" x2="12.01" y2="8"/>'
    ),
    "skip-forward": _svg(
        '<polygon points="5 4 15 12 5 20 5 4"/>'
        '<line x1="19" y1="5" x2="19" y2="19"/>'
    ),
    "pause": _svg(
        '<rect x="6" y="4" width="4" height="16"/>'
        '<rect x="14" y="4" width="4" height="16"/>'
    ),

    # ── Files ──────────────────────────────────────────────────────────
    "file": _svg(
        '<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>'
        '<polyline points="13 2 13 9 20 9"/>'
    ),
    "file-text": _svg(
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="16" y1="13" x2="8" y2="13"/>'
        '<line x1="16" y1="17" x2="8" y2="17"/>'
        '<polyline points="10 9 9 9 8 9"/>'
    ),
    "file-spreadsheet": _svg(
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="8" y1="13" x2="16" y2="13"/>'
        '<line x1="8" y1="17" x2="16" y2="17"/>'
        '<line x1="10" y1="9" x2="10" y2="13"/>'
    ),
    "folder": _svg(
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
    ),
    "folder-open": _svg(
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
    ),
    "paperclip": _svg(
        '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0'
        ' 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>'
    ),
    "image": _svg(
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
        '<circle cx="8.5" cy="8.5" r="1.5"/>'
        '<polyline points="21 15 16 10 5 21"/>'
    ),
    "file-csv": _svg(
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="8" y1="13" x2="16" y2="13"/>'
        '<line x1="8" y1="17" x2="12" y2="17"/>'
    ),

    # ── Chat / Communication ───────────────────────────────────────────
    "mic": _svg(
        '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>'
        '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
        '<line x1="12" y1="19" x2="12" y2="23"/>'
        '<line x1="8" y1="23" x2="16" y2="23"/>'
    ),
    "mail": _svg(
        '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>'
        '<polyline points="22,6 12,13 2,6"/>'
    ),
}


# ─────────────────────────────────────────────
# Core Renderer (LRU cached)
# ─────────────────────────────────────────────

@functools.lru_cache(maxsize=512)
def _render(name: str, size: int, color: str) -> QPixmap:
    """Render an SVG icon to QPixmap with a given color. Cached."""
    svg_src = ICONS.get(name)
    if not svg_src:
        # Fallback: blank pixmap
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        return px

    colored = svg_src.replace("currentColor", color)
    data = QByteArray(colored.encode("utf-8"))
    renderer = QSvgRenderer(data)

    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return px


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def get_pixmap(
    name: str,
    size: int = 20,
    color: str = ICON_COLOR_DEFAULT,
    active: bool = False,
    disabled: bool = False,
) -> QPixmap:
    """Return a colored QPixmap for the given icon name."""
    if disabled:
        color = ICON_COLOR_DISABLED
    elif active:
        color = ICON_COLOR_ACTIVE
    return _render(name, size, color)


def get_icon(
    name: str,
    size: int = 20,
    color: str = ICON_COLOR_DEFAULT,
    active: bool = False,
    disabled: bool = False,
    hover_color: str = ICON_COLOR_HOVER,
) -> QIcon:
    """Return a QIcon with Normal and Active (hover) states."""
    base_color = ICON_COLOR_DISABLED if disabled else (ICON_COLOR_ACTIVE if active else color)
    icon = QIcon()
    icon.addPixmap(_render(name, size, base_color), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_render(name, size, hover_color), QIcon.Mode.Active, QIcon.State.Off)
    icon.addPixmap(_render(name, size, ICON_COLOR_ACTIVE), QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(_render(name, size, ICON_COLOR_DISABLED), QIcon.Mode.Disabled, QIcon.State.Off)
    return icon


# Singleton wrapper
class IconManager:
    """Convenience singleton wrapper around the module-level functions."""

    @staticmethod
    def get(name: str, size: int = 20, color: str = ICON_COLOR_DEFAULT,
            active: bool = False, disabled: bool = False) -> QIcon:
        return get_icon(name, size, color, active, disabled)

    @staticmethod
    def pixmap(name: str, size: int = 20, color: str = ICON_COLOR_DEFAULT,
               active: bool = False, disabled: bool = False) -> QPixmap:
        return get_pixmap(name, size, color, active, disabled)

    @staticmethod
    def available_icons() -> list[str]:
        return sorted(ICONS.keys())


# ─────────────────────────────────────────────
# IconButton Widget
# ─────────────────────────────────────────────

class IconButton(QPushButton):
    """
    A QPushButton that uses an SVG icon with hover/active color transitions.

    Features:
    - SVG icon color changes on hover/press
    - Optional circular hover background
    - Tooltip auto-set from icon name
    - Scale feedback on click
    - Optional text label beside icon
    """

    def __init__(
        self,
        icon_name: str,
        size: int = 20,
        color: str = ICON_COLOR_DEFAULT,
        hover_color: str = ICON_COLOR_HOVER,
        active_color: str = ICON_COLOR_ACTIVE,
        btn_size: int = 32,
        tooltip: str = "",
        circular: bool = True,
        text: str = "",
        parent: QWidget = None,
    ):
        super().__init__(text, parent)
        self._icon_name  = icon_name
        self._icon_size  = size
        self._color      = color
        self._hover_color   = hover_color
        self._active_color  = active_color
        self._btn_size   = btn_size
        self._circular   = circular
        self._is_hovered = False
        self._is_active  = False

        if btn_size is not None:
            self.setFixedSize(btn_size, btn_size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

        self._apply_style()
        self._refresh_icon()

    # ── Icon rendering ────────────────────────────────────────────────

    def _refresh_icon(self, color: str = None):
        c = color or (
            self._active_color if self._is_active
            else self._hover_color if self._is_hovered
            else self._color
        )
        px = get_pixmap(self._icon_name, self._icon_size, c)
        self.setIcon(QIcon(px))
        self.setIconSize(QSize(self._icon_size, self._icon_size))

    def _apply_style(self):
        if self._circular and self._btn_size is not None:
            radius = self._btn_size // 2
        else:
            radius = 6
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {radius}px;
                padding: 0;
            }}
            QPushButton:hover {{
                background: rgba(79, 157, 255, 0.12);
            }}
            QPushButton:pressed {{
                background: rgba(79, 157, 255, 0.22);
            }}
            QPushButton:disabled {{
                opacity: 0.4;
            }}
        """)

    # ── Hover / press events ─────────────────────────────────────────

    def enterEvent(self, event):
        self._is_hovered = True
        self._refresh_icon()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._refresh_icon()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        # Brief scale-down via size trick — purely visual
        if self._circular:
            self.setIconSize(QSize(self._icon_size - 2, self._icon_size - 2))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        super().mouseReleaseEvent(event)

    # ── State setters ─────────────────────────────────────────────────

    def set_active(self, active: bool):
        self._is_active = active
        self._refresh_icon()

    def set_color(self, color: str):
        self._color = color
        self._refresh_icon()

    def set_icon_name(self, name: str):
        self._icon_name = name
        self._refresh_icon()


# ─────────────────────────────────────────────
# StatusIcon — icon + colored dot indicator
# ─────────────────────────────────────────────

class StatusIcon(IconButton):
    """
    An IconButton whose color indicates a status
    (running=blue, success=green, error=red, pending=muted).
    """

    STATUS_COLORS = {
        "pending":  ICON_COLOR_MUTED,
        "running":  ICON_COLOR_ACTIVE,
        "success":  ICON_COLOR_SUCCESS,
        "failed":   ICON_COLOR_ERROR,
        "skipped":  ICON_COLOR_MUTED,
        "waiting":  ICON_COLOR_WARNING,
        "cancelled": ICON_COLOR_MUTED,
    }

    STATUS_ICONS = {
        "pending":  "clock",
        "running":  "loader",
        "success":  "check-circle",
        "failed":   "x-circle",
        "skipped":  "skip-forward",
        "waiting":  "pause",
        "cancelled": "x-circle",
    }

    def __init__(self, status: str = "pending", size: int = 20, parent=None):
        icon_name = self.STATUS_ICONS.get(status, "clock")
        color = self.STATUS_COLORS.get(status, ICON_COLOR_MUTED)
        super().__init__(
            icon_name=icon_name,
            size=size,
            color=color,
            hover_color=color,
            btn_size=size + 8,
            circular=False,
            parent=parent,
        )
        self.setEnabled(False)  # Display-only
        self._status = status

    def set_status(self, status: str):
        self._status = status
        self._icon_name = self.STATUS_ICONS.get(status, "clock")
        self._color = self.STATUS_COLORS.get(status, ICON_COLOR_MUTED)
        self._hover_color = self._color
        self._refresh_icon()
