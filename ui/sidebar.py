"""
Sidebar Panel — left navigation with session history, mode selector,
quick-prompt library, and app branding.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from models.schemas import ExecutionMode, SessionState
from prompts.planner_prompts import SAMPLE_PROMPTS
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

    session_selected      = Signal(str)     # session_id
    new_session_requested = Signal()
    mode_changed          = Signal(str)     # ExecutionMode value
    prompt_selected       = Signal(str)     # prompt text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._sessions: dict[str, SessionState] = {}
        self._active_session_id: str | None = None
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

        logo = QLabel("🤖")
        logo.setStyleSheet("font-size: 26px; background: transparent;")
        b_layout.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        app_name = QLabel("Desktop Agent")
        app_name.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 14px; "
            f"font-weight: 700; background: transparent;"
        )
        version = QLabel("v1.0  ·  Grok Powered")
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

        new_btn = QPushButton("+ New Session")
        new_btn.setObjectName("btn_primary")
        new_btn.setFixedHeight(34)
        new_btn.clicked.connect(self.new_session_requested)
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
            f"QListWidget::item {{ padding: 8px 16px; border-radius: 6px; margin: 1px 6px; }}"
            f"QListWidget::item:selected {{ background: {COLORS['bg_selected']}; }}"
            f"QListWidget::item:hover {{ background: {COLORS['bg_hover']}; }}"
        )
        self._session_list.setMaximumHeight(160)
        self._session_list.itemClicked.connect(self._on_session_clicked)
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

        # ── API Status Footer ─────────────────────
        footer = QWidget()
        footer.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(12, 6, 12, 8)
        f_layout.setSpacing(6)

        self._api_dot = QLabel("●")
        self._api_dot.setStyleSheet(f"color: {COLORS['accent_green']}; font-size: 10px;")
        f_layout.addWidget(self._api_dot)

        self._api_lbl = QLabel("Grok API")
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
        item = QListWidgetItem(f"💬  {session.name}")
        item.setData(Qt.ItemDataRole.UserRole, session.id)
        self._session_list.insertItem(0, item)

    def set_active_session(self, session_id: str):
        self._active_session_id = session_id
        for i in range(self._session_list.count()):
            item = self._session_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == session_id:
                self._session_list.setCurrentItem(item)
                break

    def set_api_status(self, connected: bool, label: str = None):
        color = COLORS["accent_green"] if connected else COLORS["accent_red"]
        self._api_dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        if label:
            self._api_lbl.setText(label)

    def get_current_mode(self) -> ExecutionMode:
        val = self._mode_combo.currentData()
        return ExecutionMode(val) if val else ExecutionMode.SAFE

    def _on_session_clicked(self, item: QListWidgetItem):
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id:
            self.session_selected.emit(session_id)

    def _on_mode_changed(self, index: int):
        val = self._mode_combo.itemData(index)
        if val:
            self.mode_changed.emit(val)
