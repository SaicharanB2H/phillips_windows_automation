"""
App Launcher Panel — searchable grid of installed Windows applications.
Launches apps directly without going through the LLM planning pipeline.
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal, QTimer, QThread, QObject
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from icons.icon_manager import IconButton, get_pixmap
from ui.styles import COLORS
from ui.widgets import HDivider, SectionLabel


# ─────────────────────────────────────────────
# Background worker — loads app list off the UI thread
# ─────────────────────────────────────────────

class _AppLoaderWorker(QObject):
    finished = Signal(list)   # list of {"name": str, "shortcut": str}

    def run(self):
        try:
            from agents.app_launcher_agent import AppLauncherAgent
            agent = AppLauncherAgent()
            result = agent.list_apps()
            self.finished.emit(result.get("apps", []))
        except Exception as e:
            self.finished.emit([])


# ─────────────────────────────────────────────
# App tile button
# ─────────────────────────────────────────────

class _AppTile(QPushButton):
    """A single clickable app tile in the grid."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self._name = name

        # Truncate long names for display
        display = name if len(name) <= 18 else name[:16] + "…"
        self.setText(display)
        self.setToolTip(name)
        self.setFixedSize(108, 52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)

    def _apply_style(self, hovered: bool):
        bg     = COLORS["bg_hover"]      if hovered else COLORS["bg_tertiary"]
        border = COLORS["accent_blue"]   if hovered else COLORS["border"]
        color  = COLORS["text_primary"]  if hovered else COLORS["text_secondary"]
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background: {bg}; color: {color};"
            f"  border: 1px solid {border}; border-radius: 8px;"
            f"  font-size: 11px; font-weight: 500;"
            f"  padding: 4px 6px; text-align: center;"
            f"}}"
        )

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    @property
    def app_name(self) -> str:
        return self._name


# ─────────────────────────────────────────────
# Main Panel
# ─────────────────────────────────────────────

class AppLauncherPanel(QWidget):
    """
    Searchable grid panel listing all installed Windows applications.
    Emits `launch_requested(name)` — wire this to the orchestrator or
    directly to AppLauncherAgent.open_app() for instant launch.
    """

    launch_requested = Signal(str)   # app name to launch

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_apps: List[dict] = []
        self._tiles: List[_AppTile] = []
        self._loaded = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Header ────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("monitor", size=16, color=COLORS["accent_blue"]))
        icon_lbl.setFixedSize(20, 20)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")
        header_row.addWidget(icon_lbl)

        title = QLabel("App Launcher")
        title.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 13px; "
            f"font-weight: 700; background: transparent;"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self._count_lbl = QLabel("Loading…")
        self._count_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
        )
        header_row.addWidget(self._count_lbl)
        layout.addLayout(header_row)

        # ── Search box ────────────────────────────
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search apps…")
        self._search.setFixedHeight(32)
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {COLORS['bg_tertiary']}; color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border']}; border-radius: 6px;"
            f"  padding: 0 10px; font-size: 12px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent_blue']}; }}"
        )
        self._search.textChanged.connect(self._filter_apps)
        search_row.addWidget(self._search, 1)

        refresh_btn = IconButton(
            "refresh-cw", size=13,
            color=COLORS["text_muted"], hover_color=COLORS["accent_blue"],
            btn_size=30,
        )
        refresh_btn.setToolTip("Refresh app list")
        refresh_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['bg_tertiary']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px; }}"
            f"QPushButton:hover {{ border-color: {COLORS['accent_blue']}; }}"
        )
        refresh_btn.clicked.connect(self._load_apps)
        search_row.addWidget(refresh_btn)
        layout.addLayout(search_row)

        # ── Quick-launch bar (type any app name) ──
        ql_row = QHBoxLayout()
        ql_row.setSpacing(6)

        self._custom_input = QLineEdit()
        self._custom_input.setPlaceholderText("Type any app name and press Enter…")
        self._custom_input.setFixedHeight(30)
        self._custom_input.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {COLORS['bg_tertiary']}; color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border']}; border-radius: 6px;"
            f"  padding: 0 10px; font-size: 11px; font-style: italic;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {COLORS['accent_blue']}; "
            f"font-style: normal; }}"
        )
        self._custom_input.returnPressed.connect(self._launch_custom)
        ql_row.addWidget(self._custom_input, 1)

        launch_btn = IconButton(
            "play", size=12,
            color="#FFFFFF", hover_color="#FFFFFF",
            btn_size=30,
        )
        launch_btn.setToolTip("Launch")
        launch_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['accent_blue']}; "
            f"border: none; border-radius: 6px; }}"
            f"QPushButton:hover {{ background: {COLORS.get('accent_blue_hover', '#388BFD')}; }}"
        )
        launch_btn.clicked.connect(self._launch_custom)
        ql_row.addWidget(launch_btn)
        layout.addLayout(ql_row)

        layout.addWidget(HDivider())

        # ── Scrollable app grid ───────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ background: {COLORS['bg_secondary']}; "
            f"width: 6px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {COLORS['border']}; "
            f"border-radius: 3px; min-height: 20px; }}"
        )

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 4, 0, 4)
        self._grid.setSpacing(6)
        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll, 1)

        # ── Loading placeholder ───────────────────
        self._loading_lbl = QLabel("Loading installed apps…")
        self._loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; padding: 20px;"
        )
        self._grid.addWidget(self._loading_lbl, 0, 0, 1, 3)

    # ─────────────────────────────────────────
    # Loading
    # ─────────────────────────────────────────

    def load_apps(self):
        """Start loading apps in background (call once after widget is shown)."""
        if not self._loaded:
            self._load_apps()

    def _load_apps(self):
        """Reload app list from disk in background thread."""
        self._count_lbl.setText("Loading…")
        self._loading_lbl.setText("Scanning installed apps…")
        self._loading_lbl.show()

        self._thread = QThread()
        self._worker = _AppLoaderWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_apps_loaded)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_apps_loaded(self, apps: list):
        self._all_apps = apps
        self._loaded = True
        self._search.setPlaceholderText(f"Search {len(apps)} apps…")
        self._count_lbl.setText(f"{len(apps)} apps")
        self._rebuild_grid(apps)

    def _rebuild_grid(self, apps: list):
        """Rebuild the tile grid from a (filtered) list of apps."""
        # Clear existing tiles
        for tile in self._tiles:
            tile.setParent(None)
            tile.deleteLater()
        self._tiles.clear()

        # Remove loading label if present
        self._loading_lbl.hide()

        if not apps:
            no_result = QLabel("No apps found")
            no_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_result.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 12px; padding: 20px;"
            )
            self._grid.addWidget(no_result, 0, 0, 1, 3)
            return

        COLS = 3
        for i, app in enumerate(apps):
            tile = _AppTile(app["name"])
            tile.clicked.connect(
                lambda checked=False, n=app["name"]: self._launch(n)
            )
            self._tiles.append(tile)
            self._grid.addWidget(tile, i // COLS, i % COLS)

    # ─────────────────────────────────────────
    # Filtering & Launching
    # ─────────────────────────────────────────

    def _filter_apps(self, text: str):
        """Filter the grid by search text."""
        q = text.strip().lower()
        if not q:
            filtered = self._all_apps
        else:
            filtered = [
                a for a in self._all_apps
                if q in a["name"].lower()
            ]
        self._rebuild_grid(filtered)
        count = len(filtered)
        total = len(self._all_apps)
        self._count_lbl.setText(
            f"{count} apps" if not q else f"{count} / {total}"
        )

    def _launch(self, name: str):
        """Emit signal to launch an app by name."""
        self.launch_requested.emit(name)

    def _launch_custom(self):
        """Launch whatever is typed in the custom input field."""
        name = self._custom_input.text().strip()
        if name:
            self.launch_requested.emit(name)
            self._custom_input.clear()
