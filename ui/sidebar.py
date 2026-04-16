"""
Sidebar Panel — left navigation with session history, mode selector,
quick-prompt library, and app branding.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from icons.icon_manager import IconButton, get_icon, get_pixmap
from models.schemas import ExecutionMode, SessionState
from prompts.planner_prompts import SAMPLE_PROMPTS
from storage.memory_store import get_memory_store
from ui.styles import COLORS
from ui.widgets import HDivider, SectionLabel


class SidebarPanel(QWidget):
    """
    Left sidebar with:
    - App logo and title
    - New Session button
    - Session history list
    - Execution mode selector
    - Quick prompt library
    """

    session_selected      = Signal(str)        # session_id
    new_session_requested = Signal(str)        # session name chosen by user
    session_renamed       = Signal(str, str)   # session_id, new_name
    session_deleted       = Signal(str)        # session_id
    mode_changed          = Signal(str)        # ExecutionMode value
    prompt_selected       = Signal(str)        # prompt text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._sessions: dict[str, SessionState] = {}
        self._active_session_id: str | None = None
        self._session_icon = get_icon("message-circle", size=14, color=COLORS["text_muted"])
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Logo / Branding ───────────────────────
        brand = QWidget()
        brand.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        brand.setFixedHeight(64)
        b_layout = QHBoxLayout(brand)
        b_layout.setContentsMargins(16, 0, 16, 0)
        b_layout.setSpacing(10)

        # SVG bot logo
        logo = QLabel()
        logo.setPixmap(get_pixmap("bot", size=26, color=COLORS["accent_blue"]))
        logo.setFixedSize(30, 30)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("background: transparent;")
        b_layout.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        app_name = QLabel("Desktop Agent")
        app_name.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 14px; "
            f"font-weight: 700; background: transparent;"
        )
        version = QLabel("v1.0  ·  gpt-oss-120b")
        version.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; background: transparent;"
        )
        title_col.addWidget(app_name)
        title_col.addWidget(version)
        b_layout.addLayout(title_col)
        b_layout.addStretch()
        layout.addWidget(brand)
        layout.addWidget(HDivider())

        # ── New Session Button ─────────────────────
        new_btn_wrap = QWidget()
        new_btn_wrap.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        n_layout = QHBoxLayout(new_btn_wrap)
        n_layout.setContentsMargins(12, 10, 12, 10)

        new_btn = IconButton(
            icon_name="plus",
            size=15,
            color="#FFFFFF",
            hover_color="#FFFFFF",
            btn_size=None,
            text="  New Session",
            parent=new_btn_wrap,
        )
        new_btn.setObjectName("btn_primary")
        new_btn.setFixedHeight(34)
        new_btn.setMinimumWidth(160)
        new_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['accent_blue']}; color: #FFFFFF; "
            f"font-size: 12px; font-weight: 600; border: none; border-radius: 6px; "
            f"padding: 0 14px; }}"
            f"QPushButton:hover {{ background: {COLORS.get('accent_blue_hover', '#388BFD')}; }}"
            f"QPushButton:pressed {{ background: {COLORS.get('accent_blue_active', '#2563EB')}; }}"
        )
        new_btn.clicked.connect(self._on_new_session_clicked)
        n_layout.addWidget(new_btn)
        layout.addWidget(new_btn_wrap)

        # ── Sessions List ─────────────────────────
        sessions_header = QWidget()
        sessions_header.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        sh_layout = QHBoxLayout(sessions_header)
        sh_layout.setContentsMargins(16, 6, 16, 6)
        sh_layout.addWidget(SectionLabel("Sessions"))
        sh_layout.addStretch()
        layout.addWidget(sessions_header)

        self._session_list = QListWidget()
        self._session_list.setStyleSheet(
            f"QListWidget {{ background: {COLORS['bg_secondary']}; border: none; }}"
            f"QListWidget::item {{ padding: 8px 16px; border-radius: 6px; margin: 1px 6px; "
            f"color: {COLORS['text_secondary']}; font-size: 12px; }}"
            f"QListWidget::item:selected {{ background: {COLORS['bg_selected']}; "
            f"color: {COLORS['text_primary']}; }}"
            f"QListWidget::item:hover {{ background: {COLORS['bg_hover']}; }}"
        )
        self._session_list.setMaximumHeight(160)
        self._session_list.itemClicked.connect(self._on_session_clicked)
        self._session_list.itemDoubleClicked.connect(self._on_session_double_clicked)
        self._session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._session_list.customContextMenuRequested.connect(self._on_session_context_menu)
        layout.addWidget(self._session_list)
        layout.addWidget(HDivider())

        # ── Execution Mode ────────────────────────
        mode_widget = QWidget()
        mode_widget.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        m_layout = QVBoxLayout(mode_widget)
        m_layout.setContentsMargins(12, 10, 12, 10)
        m_layout.setSpacing(6)
        m_layout.addWidget(SectionLabel("Execution Mode"))

        self._mode_combo = QComboBox()
        for mode in ExecutionMode:
            self._mode_combo.addItem(mode.value.replace("_", " ").title(), mode.value)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        m_layout.addWidget(self._mode_combo)

        mode_desc = QLabel(
            "Safe: confirms risky actions\n"
            "Semi-Auto: confirms email/delete\n"
            "Demo: auto-approve (no send)\n"
            "Dry-Run: simulate only"
        )
        mode_desc.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; line-height: 1.5;"
        )
        m_layout.addWidget(mode_desc)
        layout.addWidget(mode_widget)
        layout.addWidget(HDivider())

        # ── Quick Prompts ─────────────────────────
        qp_header = QWidget()
        qp_header.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        qp_layout_h = QHBoxLayout(qp_header)
        qp_layout_h.setContentsMargins(16, 6, 16, 6)
        qp_layout_h.addWidget(SectionLabel("Quick Prompts"))
        layout.addWidget(qp_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"background: {COLORS['bg_secondary']}; border: none;"
        )

        prompts_container = QWidget()
        prompts_container.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        p_layout = QVBoxLayout(prompts_container)
        p_layout.setContentsMargins(8, 4, 8, 8)
        p_layout.setSpacing(4)

        current_cat = None
        for prompt_def in SAMPLE_PROMPTS:
            cat = prompt_def["category"]
            if cat != current_cat:
                current_cat = cat
                cat_lbl = QLabel(cat.upper())
                cat_lbl.setStyleSheet(
                    f"color: {COLORS['text_muted']}; font-size: 9px; "
                    f"font-weight: 700; letter-spacing: 0.8px; "
                    f"padding: 6px 6px 2px 6px;"
                )
                p_layout.addWidget(cat_lbl)

            btn = QPushButton(prompt_def["label"])
            btn.setStyleSheet(
                f"QPushButton {{ background: {COLORS['bg_tertiary']}; "
                f"color: {COLORS['text_secondary']}; font-size: 11px; "
                f"border: 1px solid {COLORS['border']}; border-radius: 6px; "
                f"padding: 6px 10px; text-align: left; }}"
                f"QPushButton:hover {{ background: {COLORS['bg_hover']}; "
                f"color: {COLORS['text_primary']}; "
                f"border-color: {COLORS['border_accent']}; }}"
            )
            btn.setToolTip(prompt_def["prompt"])
            btn.clicked.connect(
                lambda checked, p=prompt_def["prompt"]: self.prompt_selected.emit(p)
            )
            p_layout.addWidget(btn)

        p_layout.addStretch()
        scroll.setWidget(prompts_container)
        layout.addWidget(scroll, 1)
        layout.addWidget(HDivider())

        # ── Memory Status Bar ─────────────────────
        mem_bar = QWidget()
        mem_bar.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        mem_layout = QHBoxLayout(mem_bar)
        mem_layout.setContentsMargins(12, 4, 12, 4)
        mem_layout.setSpacing(6)

        mem_icon = QLabel()
        mem_icon.setPixmap(get_pixmap("cpu", size=12, color=COLORS["accent_blue"]))
        mem_icon.setFixedSize(14, 14)
        mem_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mem_icon.setStyleSheet("background: transparent;")
        mem_layout.addWidget(mem_icon)

        self._mem_lbl = QLabel()
        self._mem_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px;"
        )
        mem_layout.addWidget(self._mem_lbl)
        mem_layout.addStretch()

        mem_clear_btn = IconButton(
            icon_name="trash", size=10,
            color=COLORS["text_muted"], hover_color=COLORS["accent_red"],
            btn_size=None, text="  Clear",
        )
        mem_clear_btn.setFixedHeight(20)
        mem_clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {COLORS['text_muted']}; "
            f"font-size: 9px; border: none; border-radius: 3px; padding: 0 4px; }}"
            f"QPushButton:hover {{ color: {COLORS['accent_red']}; }}"
        )
        mem_clear_btn.clicked.connect(self._clear_memory)
        mem_layout.addWidget(mem_clear_btn)

        layout.addWidget(mem_bar)
        self._refresh_memory_count()

        # ── API Status Footer ─────────────────────
        footer = QWidget()
        footer.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(12, 6, 12, 8)
        f_layout.setSpacing(6)

        self._api_dot = QLabel()
        self._api_dot.setPixmap(
            get_pixmap("check-circle", size=12, color=COLORS["accent_green"])
        )
        self._api_dot.setFixedSize(14, 14)
        self._api_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._api_dot.setStyleSheet("background: transparent;")
        f_layout.addWidget(self._api_dot)

        self._api_lbl = QLabel("gpt-oss-120b")
        self._api_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
        )
        f_layout.addWidget(self._api_lbl)
        f_layout.addStretch()
        layout.addWidget(footer)

    # ─────────────────────────────────────────
    # Public Methods
    # ─────────────────────────────────────────

    def add_session(self, session: SessionState):
        """Add a session entry to the list."""
        self._sessions[session.id] = session
        item = QListWidgetItem(self._session_icon, f"  {session.name}")
        item.setData(Qt.ItemDataRole.UserRole, session.id)
        item.setToolTip("Double-click to rename · Right-click for options")
        self._session_list.insertItem(0, item)

    def rename_session_item(self, session_id: str, new_name: str):
        """Update the displayed name of a session item in the list."""
        for i in range(self._session_list.count()):
            item = self._session_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == session_id:
                item.setText(f"  {new_name}")
                break

    def set_active_session(self, session_id: str):
        self._active_session_id = session_id
        for i in range(self._session_list.count()):
            item = self._session_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == session_id:
                self._session_list.setCurrentItem(item)
                break

    def set_api_status(self, connected: bool, label: str = None):
        icon_name = "check-circle" if connected else "x-circle"
        color = COLORS["accent_green"] if connected else COLORS["accent_red"]
        self._api_dot.setPixmap(get_pixmap(icon_name, size=12, color=color))
        if label:
            self._api_lbl.setText(label)

    def get_current_mode(self) -> ExecutionMode:
        val = self._mode_combo.currentData()
        return ExecutionMode(val) if val else ExecutionMode.SAFE

    def refresh_memory_count(self):
        """Call this after any memory save/forget to keep the badge up to date."""
        self._refresh_memory_count()

    def _refresh_memory_count(self):
        try:
            store = get_memory_store()
            n = store.count()
            if n == 0:
                self._mem_lbl.setText("No memories yet")
            elif n == 1:
                self._mem_lbl.setText("1 memory stored")
            else:
                self._mem_lbl.setText(f"{n} memories stored")
        except Exception:
            self._mem_lbl.setText("Memory unavailable")

    def _clear_memory(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Clear All Memories",
            "This will permanently delete all remembered facts.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            get_memory_store().clear_all()
            self._refresh_memory_count()

    def _on_new_session_clicked(self):
        """Prompt for a session name before creating."""
        name, ok = QInputDialog.getText(
            self,
            "New Session",
            "Session name:",
            text="New Session",
        )
        if ok:
            name = name.strip() or "New Session"
            self.new_session_requested.emit(name)

    def _on_session_clicked(self, item: QListWidgetItem):
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)

    def _on_session_double_clicked(self, item: QListWidgetItem):
        """Rename a session on double-click."""
        self._rename_item(item)

    def _on_session_context_menu(self, pos):
        """Right-click context menu on a session item."""
        item = self._session_list.itemAt(pos)
        if not item:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {COLORS['bg_tertiary']}; color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 20px; border-radius: 4px; font-size: 12px; }}"
            f"QMenu::item:selected {{ background: {COLORS['bg_hover']}; }}"
        )
        rename_action = menu.addAction("✏️  Rename")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️  Delete")

        action = menu.exec(self._session_list.mapToGlobal(pos))
        if action == rename_action:
            self._rename_item(item)
        elif action == delete_action:
            self._delete_item(item)

    def _rename_item(self, item: QListWidgetItem):
        """Show inline rename dialog for a session item."""
        session_id = item.data(Qt.ItemDataRole.UserRole)
        current_name = item.text().strip()
        name, ok = QInputDialog.getText(
            self,
            "Rename Session",
            "New name:",
            text=current_name,
        )
        if ok:
            name = name.strip() or current_name
            item.setText(f"  {name}")
            if session_id in self._sessions:
                self._sessions[session_id].name = name
            self.session_renamed.emit(session_id, name)

    def _delete_item(self, item: QListWidgetItem):
        """Delete a session after confirmation."""
        from PySide6.QtWidgets import QMessageBox
        session_id = item.data(Qt.ItemDataRole.UserRole)
        name = item.text().strip()
        reply = QMessageBox.question(
            self,
            "Delete Session",
            f"Delete session \"{name}\"?\n\nThis will remove all messages and history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            row = self._session_list.row(item)
            self._session_list.takeItem(row)
            self._sessions.pop(session_id, None)
            self.session_deleted.emit(session_id)

    def _on_mode_changed(self, index: int):
        val = self._mode_combo.itemData(index)
        if val:
            self.mode_changed.emit(val)
