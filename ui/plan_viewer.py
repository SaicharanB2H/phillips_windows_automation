"""
Plan Viewer — expandable tree showing the full execution plan.
Updates in real time as steps change status.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from models.schemas import ExecutionPlan, PlanStep, StepStatus
from ui.styles import COLORS, get_agent_color, get_agent_icon, get_status_color, get_status_icon
from ui.widgets import HDivider, SectionLabel, StepCard


class PlanViewer(QWidget):
    """
    Displays the active execution plan as an expandable step list.
    Each step shows title, agent, status, duration, and error.
    """

    retry_step_requested = Signal(str)   # step_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, StepCard] = {}
        self._current_plan: ExecutionPlan | None = None
        self._setup_ui()

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

        h_layout.addWidget(SectionLabel("Execution Plan"))
        h_layout.addStretch()

        self._progress_lbl = QLabel("—")
        self._progress_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
        )
        h_layout.addWidget(self._progress_lbl)

        layout.addWidget(header)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)

        layout.addWidget(HDivider())

        # ── Intent Summary ────────────────────────
        self._intent_widget = QWidget()
        self._intent_widget.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        i_layout = QVBoxLayout(self._intent_widget)
        i_layout.setContentsMargins(12, 8, 12, 8)
        i_layout.setSpacing(4)

        intent_header = QLabel("GOAL")
        intent_header.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 10px; "
            f"font-weight: 700; letter-spacing: 1px;"
        )
        i_layout.addWidget(intent_header)

        self._intent_lbl = QLabel("No plan loaded")
        self._intent_lbl.setWordWrap(True)
        self._intent_lbl.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px;"
        )
        i_layout.addWidget(self._intent_lbl)

        layout.addWidget(self._intent_widget)
        layout.addWidget(HDivider())

        # ── Step Cards ────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._steps_container = QWidget()
        self._steps_container.setStyleSheet("background: transparent;")
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(8, 8, 8, 8)
        self._steps_layout.setSpacing(6)
        self._steps_layout.addStretch()

        # Empty state
        self._empty_lbl = QLabel(
            "No plan loaded.\nSubmit a request to generate an execution plan."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 12px; padding: 32px;"
        )
        self._steps_layout.insertWidget(0, self._empty_lbl)

        scroll.setWidget(self._steps_container)
        layout.addWidget(scroll, 1)

        # ── Agent Summary Row ─────────────────────
        self._agent_row = QWidget()
        self._agent_row.setStyleSheet(f"background: {COLORS['bg_secondary']};")
        a_layout = QHBoxLayout(self._agent_row)
        a_layout.setContentsMargins(12, 6, 12, 6)
        a_layout.setSpacing(8)
        self._agent_row.hide()
        layout.addWidget(self._agent_row)

    def load_plan(self, plan: ExecutionPlan):
        """Display a new execution plan, replacing any existing one."""
        self._current_plan = plan
        self._clear_cards()
        self._empty_lbl.hide()

        # Intent
        self._intent_lbl.setText(plan.intent_summary)

        # Agent badges in footer
        while self._agent_row.layout().count():
            item = self._agent_row.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for agent in plan.required_agents:
            badge = QLabel(f"{get_agent_icon(agent.value)} {agent.value.replace('_',' ').title()}")
            badge.setStyleSheet(
                f"color: {get_agent_color(agent.value)}; font-size: 10px; "
                f"font-weight: 600; background: {COLORS['bg_tertiary']}; "
                f"border-radius: 10px; padding: 2px 8px;"
            )
            self._agent_row.layout().addWidget(badge)
        self._agent_row.layout().addStretch()
        self._agent_row.show()

        # Step cards
        for step in sorted(plan.steps, key=lambda s: s.order):
            card = StepCard(
                step_id=step.id,
                order=step.order,
                title=step.title,
                description=step.description,
                agent=step.agent.value,
            )
            card.retry_requested.connect(self.retry_step_requested)
            if step.status != StepStatus.PENDING:
                card.set_status(
                    step.status.value,
                    error=step.error,
                    duration_s=step.duration_seconds,
                )
            self._cards[step.id] = card
            self._steps_layout.insertWidget(
                self._steps_layout.count() - 1, card
            )

        self._update_progress()

    def update_step(self, step: PlanStep):
        """Update an existing step card's status."""
        card = self._cards.get(step.id)
        if card:
            card.set_status(
                step.status.value,
                error=step.error,
                duration_s=step.duration_seconds,
            )
        self._update_progress()

    def _update_progress(self):
        if not self._current_plan:
            return
        total = len(self._current_plan.steps)
        done = sum(
            1 for s in self._current_plan.steps
            if s.status in (StepStatus.SUCCESS, StepStatus.FAILED, StepStatus.SKIPPED)
        )
        success = sum(
            1 for s in self._current_plan.steps
            if s.status == StepStatus.SUCCESS
        )
        pct = int((done / total * 100)) if total > 0 else 0
        self._progress_bar.setValue(pct)
        self._progress_lbl.setText(f"{success}/{total} complete")

    def clear_plan(self):
        """Reset to empty state."""
        self._clear_cards()
        self._current_plan = None
        self._intent_lbl.setText("No plan loaded")
        self._progress_bar.setValue(0)
        self._progress_lbl.setText("—")
        self._empty_lbl.show()
        self._agent_row.hide()

    def _clear_cards(self):
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
