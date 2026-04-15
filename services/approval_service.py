"""
Approval Service — Safety checkpoint management.

Manages approval requests for risky actions and integrates with the UI
via Qt signals. The orchestrator pauses execution until approval is given.
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal

from models.schemas import ApprovalRequest, ExecutionMode, RiskLevel
from utils.logger import get_logger

logger = get_logger("services.approval", "approval")


# ─────────────────────────────────────────────
# Signal Bridge
# ─────────────────────────────────────────────

class ApprovalSignalBridge(QObject):
    """Qt signal bridge for thread-safe approval request/response."""
    approval_requested = Signal(object)   # ApprovalRequest
    approval_responded = Signal(str, bool)  # request_id, approved


_bridge: Optional[ApprovalSignalBridge] = None


def get_approval_bridge() -> ApprovalSignalBridge:
    global _bridge
    if _bridge is None:
        _bridge = ApprovalSignalBridge()
    return _bridge


# ─────────────────────────────────────────────
# Actions that always require approval per mode
# ─────────────────────────────────────────────

ALWAYS_SAFE_APPROVALS = {
    "email.send_draft", "files.delete", "files.overwrite",
}

SEMI_AUTO_APPROVALS = {
    "email.send_draft", "files.delete",
}

DEMO_APPROVALS = {
    "email.send_draft",
}


class ApprovalService:
    """
    Manages approval checkpoints for risky actions.
    Blocks the calling thread until the user responds via the UI.
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.SAFE):
        self.mode = mode
        self._pending: Dict[str, threading.Event] = {}
        self._responses: Dict[str, bool] = {}
        # Wire up response handler
        get_approval_bridge().approval_responded.connect(self._on_response)

    def set_mode(self, mode: ExecutionMode):
        self.mode = mode
        logger.info(f"Approval mode set to: {mode.value}")

    def needs_approval(
        self,
        tool_name: str,
        risk_level: RiskLevel = RiskLevel.LOW,
        explicit_flag: bool = False,
    ) -> bool:
        """Determine if this action needs approval in the current mode."""
        if explicit_flag:
            return True
        if self.mode == ExecutionMode.DRY_RUN:
            return False  # Dry run simulates everything — no real actions taken

        if self.mode == ExecutionMode.SAFE:
            return risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH) or tool_name in ALWAYS_SAFE_APPROVALS

        if self.mode == ExecutionMode.SEMI_AUTO:
            return risk_level == RiskLevel.HIGH or tool_name in SEMI_AUTO_APPROVALS

        if self.mode == ExecutionMode.DEMO:
            return tool_name in DEMO_APPROVALS

        return False

    def request_approval(self, approval: ApprovalRequest, timeout: float = 300.0) -> bool:
        """
        Emit approval request to UI and block until user responds.
        Returns True if approved, False if denied or timed out.
        """
        logger.info(
            f"Approval required: [{approval.risk_level.value}] {approval.title}"
        )

        event = threading.Event()
        self._pending[approval.id] = event

        # Emit to UI thread
        get_approval_bridge().approval_requested.emit(approval)

        # Block until response or timeout
        responded = event.wait(timeout=timeout)

        if not responded:
            logger.warning(f"Approval timeout for: {approval.id}")
            self._pending.pop(approval.id, None)
            return False

        approved = self._responses.pop(approval.id, False)
        logger.info(f"Approval {approval.id}: {'APPROVED' if approved else 'DENIED'}")
        return approved

    def _on_response(self, request_id: str, approved: bool):
        """Slot called from UI when user approves/denies."""
        self._responses[request_id] = approved
        event = self._pending.pop(request_id, None)
        if event:
            event.set()

    def auto_approve(self, approval: ApprovalRequest) -> bool:
        """Programmatically approve (for Demo/DryRun modes)."""
        logger.info(f"Auto-approving: {approval.title}")
        return True


# Singleton
_approval_service: Optional[ApprovalService] = None


def get_approval_service() -> ApprovalService:
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service
