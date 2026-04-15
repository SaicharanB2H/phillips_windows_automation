"""
Approval Dialog — modal popup for risky action confirmations.
Displays action details, risk level, and Approve / Deny buttons.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from models.schemas import ApprovalRequest, RiskLevel
from ui.styles import COLORS
from services.approval_service import get_approval_bridge


class ApprovalDialog(QDialog):
    """
    Shown when an action requires user confirmation.
    Emits the approval response back through the approval service bridge.
    """

    def __init__(self, approval: ApprovalRequest, parent=None):
        super().__init__(parent)
        self._approval = approval
        self.setWindowTitle("Action Requires Approval")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Risk indicator bar
        risk_colors = {
            RiskLevel.LOW:    COLORS["accent_green"],
            RiskLevel.MEDIUM: COLORS["accent_orange"],
            RiskLevel.HIGH:   COLORS["accent_red"],
        }
        risk_icons = {
            RiskLevel.LOW: "🟢", RiskLevel.MEDIUM: "🟡", RiskLevel.HIGH: "🔴"
        }
        risk_color = risk_colors.get(self._approval.risk_level, COLORS["accent_orange"])

        # Header
        header = QFrame()
        header.setStyleSheet(
            f"background: {COLORS['bg_tertiary']}; border-radius: 8px; "
            f"border-left: 4px solid {risk_color};"
        )
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(16, 12, 16, 12)

        risk_row = QHBoxLayout()
        risk_icon = QLabel(risk_icons.get(self._approval.risk_level, "🟡"))
        risk_icon.setStyleSheet("font-size: 18px; background: transparent;")
        risk_row.addWidget(risk_icon)

        risk_lbl = QLabel(f"RISK LEVEL: {self._approval.risk_level.value.upper()}")
        risk_lbl.setStyleSheet(
            f"color: {risk_color}; font-size: 11px; font-weight: 700; "
            f"background: transparent; letter-spacing: 1px;"
        )
        risk_row.addWidget(risk_lbl)
        risk_row.addStretch()
        h_layout.addLayout(risk_row)

        title_lbl = QLabel(self._approval.title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 15px; "
            f"font-weight: 700; background: transparent; margin-top: 4px;"
        )
        h_layout.addWidget(title_lbl)
        layout.addWidget(header)

        # Action summary
        summary_lbl = QLabel(self._approval.action_summary)
        summary_lbl.setWordWrap(True)
        summary_lbl.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 13px; background: transparent;"
        )
        layout.addWidget(summary_lbl)

        # Details section
        if self._approval.details:
            details_frame = QFrame()
            details_frame.setStyleSheet(
                f"background: {COLORS['bg_primary']}; border-radius: 6px; "
                f"border: 1px solid {COLORS['border']};"
            )
            d_layout = QVBoxLayout(details_frame)
            d_layout.setContentsMargins(12, 10, 12, 10)
            d_layout.setSpacing(4)

            detail_header = QLabel("DETAILS")
            detail_header.setStyleSheet(
                f"color: {COLORS['text_muted']}; font-size: 10px; "
                f"font-weight: 700; background: transparent; letter-spacing: 1px;"
            )
            d_layout.addWidget(detail_header)

            for k, v in self._approval.details.items():
                row = QHBoxLayout()
                key_lbl = QLabel(f"{k}:")
                key_lbl.setFixedWidth(80)
                key_lbl.setStyleSheet(
                    f"color: {COLORS['text_muted']}; font-size: 12px; background: transparent;"
                )
                val_lbl = QLabel(str(v) if not isinstance(v, list) else ", ".join(str(i) for i in v))
                val_lbl.setWordWrap(True)
                val_lbl.setStyleSheet(
                    f"color: {COLORS['text_primary']}; font-size: 12px; background: transparent;"
                )
                row.addWidget(key_lbl)
                row.addWidget(val_lbl, 1)
                d_layout.addLayout(row)

            layout.addWidget(details_frame)

        # Warning for high-risk
        if self._approval.risk_level == RiskLevel.HIGH:
            warn = QLabel(
                "⚠️  This action cannot be easily undone. "
                "Please review carefully before approving."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                f"color: {COLORS['accent_orange']}; font-size: 12px; "
                f"background: {COLORS['bg_tertiary']}; border-radius: 6px; padding: 8px;"
            )
            layout.addWidget(warn)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        deny_btn = QPushButton("Deny")
        deny_btn.setObjectName("btn_danger")
        deny_btn.setFixedSize(100, 36)
        deny_btn.clicked.connect(self._deny)

        approve_btn = QPushButton("✓  Approve")
        approve_btn.setObjectName("btn_success")
        approve_btn.setFixedSize(120, 36)
        approve_btn.setDefault(True)
        approve_btn.clicked.connect(self._approve)

        btn_row.addWidget(deny_btn)
        btn_row.addWidget(approve_btn)
        layout.addLayout(btn_row)

    def _approve(self):
        get_approval_bridge().approval_responded.emit(self._approval.id, True)
        self.accept()

    def _deny(self):
        get_approval_bridge().approval_responded.emit(self._approval.id, False)
        self.reject()

    def closeEvent(self, event):
        # Treat window close as deny
        get_approval_bridge().approval_responded.emit(self._approval.id, False)
        super().closeEvent(event)
