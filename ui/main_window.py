"""
Main Window — top-level PySide6 window.

Layout:
┌─────────────────────────────────────────────────────────┐
│  Sidebar (240px) │  Chat Panel (flex) │ Execution (380px)│
│                  │                    │  Plan / Agents   │
│  Sessions        │  Messages          │  Files / Log     │
│  Mode Selector   │  Input Box         │                  │
│  Quick Prompts   │                    │                  │
└─────────────────────────────────────────────────────────┘
│  Status Bar                                              │
└─────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QMainWindow, QMessageBox,
    QSizePolicy, QSplitter, QStatusBar, QWidget,
)

from app.orchestrator import Orchestrator
from models.schemas import (
    Artifact, ExecutionMode, ExecutionPlan, Message,
    MessageRole, PlanStep, SessionState, StepStatus, UserRequest,
)
from services.approval_service import get_approval_bridge
from ui.approval_dialog import ApprovalDialog
from ui.chat_panel import ChatPanel
from ui.execution_panel import ExecutionPanel
from ui.sidebar import SidebarPanel
from ui.styles import COLORS, MAIN_STYLESHEET
from ui.widgets import ToastNotification
from utils.helpers import is_office_available, short_id
from utils.logger import get_logger, init_ui_logging

logger = get_logger("ui.main_window", "ui")


class MainWindow(QMainWindow):
    """
    Top-level application window.
    Wires together: Orchestrator ↔ Chat ↔ Sidebar ↔ ExecutionPanel.
    All inter-component communication uses Qt signals/slots.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Desktop Automation Agent  —  Powered by Grok")
        self.setMinimumSize(1200, 720)
        self.resize(1440, 900)

        # Initialize logging UI sink
        init_ui_logging()

        # Apply stylesheet
        self.setStyleSheet(MAIN_STYLESHEET)

        # Core backend
        self._orchestrator = Orchestrator()
        self._current_session: SessionState | None = None

        # Build UI
        self._setup_ui()
        self._connect_signals()
        self._setup_status_bar()

        # Start first session
        QTimer.singleShot(0, self._init_first_session)

        logger.info("Desktop Automation Agent started")

    # ─────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar (fixed width)
        self._sidebar = SidebarPanel()
        main_layout.addWidget(self._sidebar)

        # Splitter for chat + execution panel
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)
        self._splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {COLORS['border']}; }}"
            f"QSplitter::handle:hover {{ background: {COLORS['accent_blue']}; }}"
        )

        # Chat panel
        self._chat = ChatPanel()
        self._chat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._splitter.addWidget(self._chat)

        # Execution panel
        self._exec_panel = ExecutionPanel()
        self._exec_panel.setMinimumWidth(340)
        self._splitter.addWidget(self._exec_panel)

        # Set initial split ratio: 60% chat, 40% execution
        self._splitter.setSizes([860, 580])

        main_layout.addWidget(self._splitter, 1)

    def _setup_status_bar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        from PySide6.QtWidgets import QLabel
        self._sb_mode_lbl = QLabel("Mode: Safe")
        self._sb_mode_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 0 8px;")
        self._status_bar.addPermanentWidget(self._sb_mode_lbl)

        self._sb_api_lbl = QLabel("API: Checking…")
        self._sb_api_lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; padding: 0 8px;")
        self._status_bar.addPermanentWidget(self._sb_api_lbl)

        self._sb_office_lbl = QLabel("")
        self._sb_office_lbl.setStyleSheet(f"color: {COLORS['text_muted']}; padding: 0 8px;")
        self._status_bar.addPermanentWidget(self._sb_office_lbl)

        # Check API and Office availability after UI is shown
        QTimer.singleShot(500, self._check_environment)

    # ─────────────────────────────────────────
    # Signal Wiring
    # ─────────────────────────────────────────

    def _connect_signals(self):
        orch = self._orchestrator
        sig = orch.signals

        # ── Orchestrator → UI ────────────────────
        sig.plan_ready.connect(self._on_plan_ready)
        sig.plan_started.connect(lambda _: self._chat.set_processing(True))
        sig.plan_completed.connect(self._on_plan_completed)

        sig.step_started.connect(self._on_step_started)
        sig.step_completed.connect(self._on_step_completed)
        sig.step_failed.connect(self._on_step_failed)

        sig.message_ready.connect(self._on_message_ready)
        sig.clarification_needed.connect(self._on_clarification_needed)
        sig.approval_needed.connect(self._on_approval_needed)
        sig.artifact_created.connect(self._on_artifact_created)
        sig.status_update.connect(self._on_status_update)
        sig.error_occurred.connect(self._on_error)
        sig.cancelled.connect(lambda: self._chat.set_processing(False))

        # ── Approval bridge ──────────────────────
        get_approval_bridge().approval_requested.connect(self._show_approval_dialog)

        # ── Chat panel → Orchestrator ────────────
        self._chat.message_submitted.connect(self._on_user_message)
        self._chat.stop_requested.connect(orch.cancel)
        self._chat.plan_preview_requested.connect(
            lambda: self._exec_panel.setCurrentIndex(0)
        )

        # ── Sidebar ──────────────────────────────
        self._sidebar.new_session_requested.connect(self._new_session)
        self._sidebar.session_selected.connect(self._switch_session)
        self._sidebar.mode_changed.connect(self._on_mode_changed)
        self._sidebar.prompt_selected.connect(self._chat.set_input_text)

        # ── Execution panel ──────────────────────
        self._exec_panel.retry_step_requested.connect(self._retry_step)

    # ─────────────────────────────────────────
    # Orchestrator Slots
    # ─────────────────────────────────────────

    @Slot(object)
    def _on_plan_ready(self, plan: ExecutionPlan):
        self._exec_panel.load_plan(plan)
        self._chat.set_status(f"Plan ready — {len(plan.steps)} steps")
        logger.info(f"Plan loaded: {plan.intent_summary}")

    @Slot(str, bool)
    def _on_plan_completed(self, plan_id: str, success: bool):
        self._chat.set_processing(False)
        level = "success" if success else "warning"
        msg = "Execution complete ✓" if success else "Execution finished with errors"
        ToastNotification.show_toast(self, msg, level)
        self._status_bar.showMessage(msg, 5000)

    @Slot(object)
    def _on_step_started(self, step: PlanStep):
        self._exec_panel.update_step(step)
        self._chat.set_status(f"Running: {step.title}")

    @Slot(object)
    def _on_step_completed(self, step: PlanStep):
        self._exec_panel.step_done(step)

    @Slot(object, str)
    def _on_step_failed(self, step: PlanStep, error: str):
        self._exec_panel.step_done(step)
        logger.error(f"Step failed: {step.title} — {error}")

    @Slot(object)
    def _on_message_ready(self, message: Message):
        self._chat.add_message(message)
        if self._current_session:
            self._current_session.messages.append(message)

    @Slot(str, list)
    def _on_clarification_needed(self, question: str, missing: list):
        self._chat.add_assistant_message(question)
        self._chat.set_processing(False)
        ToastNotification.show_toast(
            self, "Clarification needed — please answer in the chat", "warning"
        )

    @Slot(object)
    def _on_approval_needed(self, approval):
        # Show dialog on the main thread (already on main thread via signal)
        dlg = ApprovalDialog(approval, self)
        dlg.exec()

    @Slot(object)
    def _on_artifact_created(self, artifact: Artifact):
        self._exec_panel.add_artifact(artifact)
        if self._current_session:
            self._current_session.artifacts.append(artifact)
        ToastNotification.show_toast(
            self, f"File created: {artifact.name}", "info"
        )

    @Slot(str)
    def _on_status_update(self, status: str):
        self._chat.set_status(status)
        self._status_bar.showMessage(status, 3000)

    @Slot(str, str)
    def _on_error(self, title: str, detail: str):
        self._chat.set_processing(False)
        self._chat.add_assistant_message(
            f"**Error:** {title}\n\n```\n{detail[:500]}\n```"
        )
        ToastNotification.show_toast(self, title, "error")

    @Slot(object)
    def _show_approval_dialog(self, approval):
        """Show approval dialog — already on main thread via queued connection."""
        dlg = ApprovalDialog(approval, self)
        dlg.exec()

    # ─────────────────────────────────────────
    # User Actions
    # ─────────────────────────────────────────

    @Slot(str, list)
    def _on_user_message(self, text: str, attachments: list):
        if not self._current_session:
            self._new_session()

        # Show user bubble immediately
        from models.schemas import Message as Msg, MessageRole
        user_msg = Msg(
            id=short_id(),
            session_id=self._current_session.id,
            role=MessageRole.USER,
            content=text,
            attachments=attachments,
        )
        self._chat.add_message(user_msg)

        # Build and submit request
        mode = self._sidebar.get_current_mode()
        request = UserRequest(
            id=short_id(),
            session_id=self._current_session.id,
            text=text,
            attachments=attachments,
            execution_mode=mode,
        )
        self._orchestrator.submit_request(request)

    @Slot()
    def _new_session(self):
        session = self._orchestrator.create_session()
        self._current_session = session
        self._sidebar.add_session(session)
        self._sidebar.set_active_session(session.id)
        self._chat.clear_messages()
        self._exec_panel.clear_session()
        logger.info(f"New session started: {session.id}")

    @Slot(str)
    def _switch_session(self, session_id: str):
        session = self._orchestrator.get_session(session_id)
        if not session:
            return
        self._current_session = session
        self._orchestrator.set_active_session(session_id)
        self._chat.load_history(session.messages)
        self._exec_panel.clear_session()
        for artifact in session.artifacts:
            self._exec_panel.add_artifact(artifact)
        if session.active_plan:
            self._exec_panel.load_plan(session.active_plan)

    @Slot(str)
    def _on_mode_changed(self, mode_value: str):
        mode = ExecutionMode(mode_value)
        self._orchestrator.set_execution_mode(mode)
        self._sb_mode_lbl.setText(f"Mode: {mode_value.replace('_', ' ').title()}")
        logger.info(f"Execution mode changed to: {mode_value}")

    @Slot(str)
    def _retry_step(self, step_id: str):
        ToastNotification.show_toast(
            self, "Retry not yet implemented for individual steps", "warning"
        )

    # ─────────────────────────────────────────
    # Initialization
    # ─────────────────────────────────────────

    def _init_first_session(self):
        """Create initial session and load saved sessions from DB."""
        saved = self._orchestrator.load_sessions_from_db()
        for s in saved:
            self._sidebar.add_session(s)

        self._new_session()

    def _check_environment(self):
        """Check API key and Office availability, update status bar."""
        api_key = os.getenv("GROK_API_KEY", "")
        if api_key and not api_key.startswith("xai-your"):
            self._sb_api_lbl.setText("API: Grok ✓")
            self._sb_api_lbl.setStyleSheet(
                f"color: {COLORS['accent_green']}; padding: 0 8px;"
            )
            self._sidebar.set_api_status(True, "Grok Connected")
        else:
            self._sb_api_lbl.setText("API: No Key ⚠")
            self._sb_api_lbl.setStyleSheet(
                f"color: {COLORS['accent_orange']}; padding: 0 8px;"
            )
            self._sidebar.set_api_status(False, "No API Key")
            self._chat.add_assistant_message(
                "**⚠️  No API Key Found**\n\n"
                "Copy `.env.example` to `.env` and add your Grok API key:\n"
                "```\nGROK_API_KEY=xai-your-key-here\n```\n\n"
                "Set `MOCK_LLM=true` to test without an API key."
            )

        office = is_office_available()
        parts = []
        for app, available in office.items():
            icon = "✓" if available else "✗"
            parts.append(f"{app.title()}{icon}")
        self._sb_office_lbl.setText("  ".join(parts))

    # ─────────────────────────────────────────
    # Window Events
    # ─────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        """Save splitter state and confirm close."""
        reply = QMessageBox.question(
            self,
            "Quit",
            "Close the Desktop Automation Agent?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._orchestrator.cancel()
            event.accept()
        else:
            event.ignore()
