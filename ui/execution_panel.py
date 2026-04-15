"""
Execution Panel — right-side tabbed panel showing:
  Tab 1: Live step execution cards
  Tab 2: Plan viewer (tree)
  Tab 3: Generated artifacts
  Tab 4: Execution log
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from icons.icon_manager import get_icon
from models.schemas import Artifact, ExecutionPlan, PlanStep
from ui.artifact_panel import ArtifactPanel
from ui.log_panel import LogPanel
from ui.plan_viewer import PlanViewer
from ui.styles import COLORS
from ui.widgets import AgentBadge, HDivider, SectionLabel


class ExecutionPanel(QTabWidget):
    """
    Tabbed right-side panel for execution monitoring.
    All update methods are thread-safe via Qt signals.
    """

    retry_step_requested = Signal(str)  # step_id
    artifact_opened      = Signal(str)  # file path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabPosition(QTabWidget.TabPosition.North)
        self.setDocumentMode(False)
        self._setup_tabs()

    def _setup_tabs(self):
        _icon_size = 14
        _icon_color = COLORS.get("text_secondary", "#A0A0B0")

        # ── Tab 1: Plan ──────────────────────────
        self._plan_viewer = PlanViewer()
        self._plan_viewer.retry_step_requested.connect(self.retry_step_requested)
        self.addTab(self._plan_viewer, "  Plan")
        self.setTabIcon(0, get_icon("layers", size=_icon_size, color=_icon_color))

        # ── Tab 2: Agents ─────────────────────────
        self._agents_tab = AgentsStatusTab()
        self.addTab(self._agents_tab, "  Agents")
        self.setTabIcon(1, get_icon("cpu", size=_icon_size, color=_icon_color))

        # ── Tab 3: Artifacts ──────────────────────
        self._artifact_panel = ArtifactPanel()
        self._artifact_panel.artifact_opened.connect(self.artifact_opened)
        self.addTab(self._artifact_panel, "  Files")
        self.setTabIcon(2, get_icon("folder", size=_icon_size, color=_icon_color))

        # ── Tab 4: Log ────────────────────────────
        self._log_panel = LogPanel()
        self.addTab(self._log_panel, "  Log")
        self.setTabIcon(3, get_icon("terminal", size=_icon_size, color=_icon_color))

    # ─────────────────────────────────────────
    # Public API called by MainWindow
    # ─────────────────────────────────────────

    def load_plan(self, plan: ExecutionPlan):
        self._plan_viewer.load_plan(plan)
        self.setCurrentIndex(0)

    def update_step(self, step: PlanStep):
        self._plan_viewer.update_step(step)
        self._agents_tab.set_agent_active(step.agent.value, True)

    def step_done(self, step: PlanStep):
        self._plan_viewer.update_step(step)
        self._agents_tab.set_agent_active(step.agent.value, False)

    def add_artifact(self, artifact: Artifact):
        self._artifact_panel.add_artifact(artifact)
        # Switch to Files tab to draw attention
        self.setCurrentIndex(2)

    def clear_session(self):
        self._plan_viewer.clear_plan()
        self._artifact_panel.clear_artifacts()
        self._agents_tab.reset_all()
        self._log_panel.clear()

    @property
    def log_panel(self) -> LogPanel:
        return self._log_panel


# ─────────────────────────────────────────────
# Agents Status Tab
# ─────────────────────────────────────────────

class AgentsStatusTab(QWidget):
    """Shows a live badge for each agent with active/idle state."""

    AGENTS = ["planner", "excel", "word", "email", "file", "ui_automation"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._badges: dict[str, AgentBadge] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(SectionLabel("Active Agents"))
        layout.addWidget(HDivider())
        layout.addSpacing(8)

        for agent in self.AGENTS:
            badge = AgentBadge(agent)
            self._badges[agent] = badge
            layout.addWidget(badge)

        layout.addStretch()

        # Legend
        legend_lbl = SectionLabel("Active / Idle indicator")
        layout.addWidget(legend_lbl)

    def set_agent_active(self, agent: str, active: bool):
        badge = self._badges.get(agent)
        if badge:
            badge.set_active(active)

    def reset_all(self):
        for badge in self._badges.values():
            badge.set_active(False)
