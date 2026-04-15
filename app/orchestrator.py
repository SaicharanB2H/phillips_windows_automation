"""
Central Orchestrator — the execution engine of the system.

Responsibilities:
- Receive user requests from the frontend
- Invoke the Planner Agent to generate an ExecutionPlan
- Route each PlanStep to the correct specialized agent
- Resolve template variables between steps
- Request approvals for risky actions
- Handle failures and trigger re-planning
- Emit real-time progress signals to the UI
- Log all actions with full detail
"""
from __future__ import annotations

import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from agents.excel_agent import ExcelAgent
from agents.email_agent import EmailAgent
from agents.file_agent import FileAgent
from agents.memory_agent import MemoryAgent
from agents.planner_agent import PlannerAgent
from agents.ui_automation_agent import UIAutomationAgent
from agents.word_agent import WordAgent
from app.context_manager import ContextManager
from storage.memory_store import get_memory_store
from models.schemas import (
    AgentResult, AgentType, Artifact, ArtifactType,
    ExecutionMode, ExecutionPlan, Message, MessageRole,
    PlanStep, RiskLevel, SessionState, StepStatus,
    ToolCall, ToolResult, UserRequest,
)
from services.approval_service import ApprovalRequest, get_approval_service
from storage.database import get_db
from utils.helpers import is_office_available, short_id, human_size
from utils.logger import get_logger

logger = get_logger("app.orchestrator", "orchestrator")


# ─────────────────────────────────────────────
# Orchestrator Signals
# ─────────────────────────────────────────────

class OrchestratorSignals(QObject):
    """All signals emitted by the orchestrator for UI consumption."""
    # Plan lifecycle
    plan_ready          = Signal(object)   # ExecutionPlan
    plan_started        = Signal(str)      # plan_id
    plan_completed      = Signal(str, bool)  # plan_id, success

    # Step lifecycle
    step_started        = Signal(object)   # PlanStep
    step_completed      = Signal(object)   # PlanStep (with updated status)
    step_failed         = Signal(object, str)  # PlanStep, error_message

    # Messages
    message_ready       = Signal(object)   # Message (assistant response)
    clarification_needed = Signal(str, list)  # question, missing_info list

    # Approval
    approval_needed     = Signal(object)   # ApprovalRequest

    # Artifacts
    artifact_created    = Signal(object)   # Artifact

    # Status
    status_update       = Signal(str)      # status message
    error_occurred      = Signal(str, str) # title, detail

    # Cancellation
    cancelled           = Signal()


# ─────────────────────────────────────────────
# Background Worker
# ─────────────────────────────────────────────

class ExecutionWorker(QRunnable):
    """Runs the full execution pipeline on a background thread."""

    def __init__(self, orchestrator: "Orchestrator", request: UserRequest):
        super().__init__()
        self.orchestrator = orchestrator
        self.request = request
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        try:
            self.orchestrator._execute_pipeline(self.request)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Unhandled orchestrator error: {e}\n{tb}")
            self.orchestrator.signals.error_occurred.emit(
                "Execution Error", f"{e}\n\n{tb}"
            )


# ─────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────

class Orchestrator:
    """
    Central coordinator for multi-agent desktop automation.
    All execution happens on a QThreadPool background thread.
    """

    def __init__(self):
        self.signals = OrchestratorSignals()
        self._thread_pool = QThreadPool.globalInstance()
        self._thread_pool.setMaxThreadCount(1)  # Sequential for safety

        # Initialize agents (shared across requests)
        self._planner   = PlannerAgent()
        self._excel     = ExcelAgent()
        self._word      = WordAgent()
        self._email     = EmailAgent()
        self._file      = FileAgent()
        self._ui_auto   = UIAutomationAgent()
        self._memory    = MemoryAgent()

        # Agent routing map
        self._agent_map = {
            AgentType.EXCEL:         self._excel,
            AgentType.WORD:          self._word,
            AgentType.EMAIL:         self._email,
            AgentType.FILE:          self._file,
            AgentType.UI_AUTOMATION: self._ui_auto,
            AgentType.MEMORY:        self._memory,
        }

        # Persistent memory store
        self._memory_store = get_memory_store()

        # Services
        self._approval  = get_approval_service()
        self._db        = get_db()

        # Session state
        self._sessions: Dict[str, SessionState] = {}
        self._active_session_id: Optional[str] = None
        self._cancelled: bool = False
        self._context   = ContextManager()

        # Detect Office availability once
        self._office_status = is_office_available()
        self._planner.set_office_status(self._office_status)
        logger.info(f"Office availability: {self._office_status}")

    # ─────────────────────────────────────────
    # Session Management
    # ─────────────────────────────────────────

    def create_session(self, name: str = "New Session") -> SessionState:
        session = SessionState(name=name)
        self._sessions[session.id] = session
        self._active_session_id = session.id
        self._db.create_session(session.id, name)
        logger.info(f"Session created: {session.id} — {name}")
        return session

    def get_session(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def get_active_session(self) -> Optional[SessionState]:
        if self._active_session_id:
            return self._sessions.get(self._active_session_id)
        return None

    def set_active_session(self, session_id: str):
        self._active_session_id = session_id

    def set_execution_mode(self, mode: ExecutionMode):
        self._approval.set_mode(mode)
        if session := self.get_active_session():
            session.execution_mode = mode

    def load_sessions_from_db(self) -> List[SessionState]:
        """Load saved sessions from database on startup."""
        loaded = []
        for row in self._db.list_sessions():
            s = SessionState(
                id=row["id"],
                name=row["name"],
                execution_mode=ExecutionMode(row.get("mode", "safe")),
            )
            # Load messages
            for msg_row in self._db.get_messages(s.id):
                s.messages.append(Message(
                    id=msg_row["id"],
                    session_id=s.id,
                    role=MessageRole(msg_row["role"]),
                    content=msg_row["content"],
                    attachments=msg_row.get("attachments", []),
                ))
            self._sessions[s.id] = s
            loaded.append(s)
        return loaded

    # ─────────────────────────────────────────
    # Request Entry Point
    # ─────────────────────────────────────────

    def submit_request(self, request: UserRequest):
        """
        Receive a user request and start background execution.
        Non-blocking — execution happens on a worker thread.
        """
        self._cancelled = False
        session = self._sessions.get(request.session_id)
        if not session:
            session = self.create_session()
            request = request.model_copy(update={"session_id": session.id})

        # Set mode from request
        self._approval.set_mode(request.execution_mode)

        # ── Auto-extract facts from the user's message ───────────────────
        extracted = self._memory_store.auto_extract(request.text)
        if extracted:
            logger.info(f"Auto-saved {len(extracted)} memory fact(s) from user message")

        # ── Inject all memories into the planner and context ─────────────
        memories = self._memory_store.as_context_dict()
        if memories:
            self._planner.set_memory(memories)
            for k, v in memories.items():
                self._context.set(k, v)

        # ── Inject attached files — make them unavoidable for the planner ──
        if request.attachments:
            self._planner.set_context("attached_files", request.attachments)
            # Index-based context keys: {{attached_file_0}}, {{attached_file_1}} …
            for i, path in enumerate(request.attachments):
                self._context.set(f"attached_file_{i}", path)
                # Also by filename stem for convenience: {{report_pdf}}
                stem = path.replace("\\", "/").split("/")[-1]
                safe_stem = stem.replace(" ", "_").replace(".", "_")
                self._context.set(f"attached_{safe_stem}", path)
            # Always expose the first attachment as {{attached_file}} shorthand
            self._context.set("attached_file", request.attachments[0])

        # Save user message
        self._save_message(request.session_id, MessageRole.USER, request.text, request.attachments)
        self.signals.status_update.emit("Analyzing request...")

        worker = ExecutionWorker(self, request)
        self._thread_pool.start(worker)

    def cancel(self):
        """Signal the running execution to stop after the current step."""
        self._cancelled = True
        self.signals.status_update.emit("Cancellation requested...")
        self.signals.cancelled.emit()
        logger.info("Execution cancelled by user")

    # ─────────────────────────────────────────
    # Main Execution Pipeline
    # ─────────────────────────────────────────

    def _execute_pipeline(self, request: UserRequest):
        """Full pipeline: plan → execute → report. Runs on worker thread."""
        session = self._sessions.get(request.session_id)
        run_id = short_id()
        self._db.create_task_run(run_id, request.session_id)
        logs: List[str] = []

        try:
            # ── Step 1: Generate Plan ────────────────
            self.signals.status_update.emit("Generating execution plan with Grok...")
            plan = self._planner.plan(request)
            session.plans.append(plan)
            session.active_plan_id = plan.id
            self._db.save_plan(
                plan.id, request.session_id, request.id,
                plan.intent_summary,
                [s.model_dump() for s in plan.steps],
            )

            # ── Clarification needed? ────────────────
            if plan.clarification_needed:
                question = self._planner.generate_clarification_question(plan.missing_info)
                self._save_message(request.session_id, MessageRole.ASSISTANT, question)
                self.signals.clarification_needed.emit(question, plan.missing_info)
                self.signals.status_update.emit("Waiting for clarification...")
                self._db.finish_task_run(run_id, "needs_clarification")
                return

            # ── Emit plan to UI ──────────────────────
            self.signals.plan_ready.emit(plan)
            self.signals.plan_started.emit(plan.id)
            self.signals.status_update.emit(f"Plan ready: {len(plan.steps)} steps")

            # ── Step 2: Execute Steps ────────────────
            completed_step_ids: List[str] = []
            overall_success = True

            for step in sorted(plan.steps, key=lambda s: s.order):
                if self._cancelled:
                    step.status = StepStatus.CANCELLED
                    break

                # Check dependencies
                if not self._dependencies_met(step, plan, completed_step_ids):
                    logger.warning(f"Skipping step {step.order} — dependencies not met")
                    step.status = StepStatus.SKIPPED
                    self.signals.step_completed.emit(step)
                    continue

                # ── Approval check ───────────────────
                if self._needs_approval(step, request.execution_mode):
                    step.status = StepStatus.WAITING
                    self.signals.step_started.emit(step)

                    approval = ApprovalRequest(
                        step_id=step.id,
                        title=f"Approval Required: {step.title}",
                        description=step.description,
                        action_summary=step.approval_message or step.description,
                        risk_level=step.risk_level,
                        details={"agent": step.agent.value, "tools": [tc.tool_name for tc in step.tool_calls]},
                    )
                    self.signals.approval_needed.emit(approval)
                    approved = self._approval.request_approval(approval)

                    if not approved:
                        step.status = StepStatus.SKIPPED
                        self.signals.step_completed.emit(step)
                        logs.append(f"[SKIPPED] {step.title} — denied by user")
                        continue

                # ── Execute step ─────────────────────
                result = self._execute_step(step, plan)
                logs.append(f"[{'OK' if result.success else 'FAIL'}] {step.title}")

                if result.success:
                    completed_step_ids.append(step.id)
                    # Store result in context for template resolution
                    self._context.set_step_result(step.order, result.output or {})

                    # Register artifacts
                    for artifact in result.artifacts:
                        artifact.session_id = request.session_id
                        session.artifacts.append(artifact)
                        self._db.save_artifact(
                            artifact.id, request.session_id,
                            artifact.name, artifact.path,
                            artifact.artifact_type.value,
                            artifact.size_bytes or 0,
                            artifact.description or "",
                            step.id,
                        )
                        self.signals.artifact_created.emit(artifact)
                else:
                    overall_success = False
                    # Attempt re-planning for failed step
                    revised = self._try_replan(plan, step, result.error or "Unknown error", completed_step_ids)
                    if revised:
                        logger.info("Re-planning succeeded — continuing with revised plan")
                        plan = revised
                    else:
                        logger.warning(f"Step failed and re-planning not possible: {step.title}")

            # ── Step 3: Generate Summary ─────────────
            summary = self._build_summary(plan, session, overall_success)
            self._save_message(request.session_id, MessageRole.ASSISTANT, summary)
            self.signals.message_ready.emit(
                Message(
                    id=short_id(),
                    session_id=request.session_id,
                    role=MessageRole.ASSISTANT,
                    content=summary,
                    plan_id=plan.id,
                )
            )

            self.signals.plan_completed.emit(plan.id, overall_success)
            self.signals.status_update.emit(
                "Completed successfully" if overall_success else "Completed with errors"
            )
            self._db.finish_task_run(run_id, "success" if overall_success else "partial", logs=logs)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Pipeline error: {e}\n{tb}")
            error_msg = f"Execution failed: {e}"
            self._save_message(request.session_id, MessageRole.ASSISTANT, error_msg)
            self.signals.error_occurred.emit("Pipeline Error", f"{e}\n\n{tb}")
            self.signals.status_update.emit("Failed")
            self._db.finish_task_run(run_id, "failed", error=str(e), logs=logs)

    # ─────────────────────────────────────────
    # Step Execution
    # ─────────────────────────────────────────

    def _execute_step(self, step: PlanStep, plan: ExecutionPlan) -> AgentResult:
        """Execute a single plan step via the appropriate agent."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.utcnow()
        self.signals.step_started.emit(step)
        logger.info(f"Executing step {step.order}: {step.title} [{step.agent.value}]")

        agent = self._agent_map.get(step.agent)
        if not agent:
            step.status = StepStatus.FAILED
            step.error = f"No agent registered for type: {step.agent}"
            self.signals.step_failed.emit(step, step.error)
            return AgentResult(
                step_id=step.id,
                agent=step.agent,
                success=False,
                error=step.error,
            )

        tool_results: List[ToolResult] = []
        last_output: Any = None
        step_success = True
        step_error: Optional[str] = None
        artifacts: List[Artifact] = []

        for tool_call in step.tool_calls:
            if self._cancelled:
                break

            # Resolve template variables in arguments
            tool_call.arguments = self._context.resolve_arguments(tool_call.arguments)

            # Execute the tool
            result = agent.execute_tool(tool_call)
            tool_results.append(result)

            if result.success:
                last_output = result.data
                # Auto-detect artifacts from tool output
                detected = self._detect_artifacts(result, step)
                artifacts.extend(detected)

                # ── Tool-name-based context keys ──────────────────────────
                # Store each successful tool result under a stable key derived
                # from the tool name so later steps can reference it without
                # depending on fragile step-number ordering.
                # e.g. excel.group_by result → context key "excel_group_by"
                #      used as {{excel_group_by.table_data}} in planner JSON
                if result.data and isinstance(result.data, dict):
                    safe_key = tool_call.tool_name.replace(".", "_")
                    self._context.set(safe_key, result.data)
                    # Also store under short agent-level key for convenience
                    # e.g. "excel_last" always points to latest excel tool result
                    agent_key = f"{step.agent.value}_last"
                    self._context.set(agent_key, result.data)
            else:
                step_success = False
                step_error = result.error
                logger.warning(f"Tool failed: {tool_call.tool_name} — {result.error}")
                break  # Stop step on first tool failure

        step.completed_at = datetime.utcnow()
        step.status = StepStatus.SUCCESS if step_success else StepStatus.FAILED
        step.error = step_error

        if step_success:
            self.signals.step_completed.emit(step)
        else:
            self.signals.step_failed.emit(step, step_error or "Unknown error")

        return AgentResult(
            step_id=step.id,
            agent=step.agent,
            success=step_success,
            output=last_output,
            artifacts=artifacts,
            error=step_error,
            tool_results=tool_results,
        )

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _needs_approval(self, step: PlanStep, mode: ExecutionMode) -> bool:
        """Check if a step needs approval in the current mode."""
        if step.requires_approval:
            return self._approval.needs_approval(
                tool_name=step.tool_calls[0].tool_name if step.tool_calls else "",
                risk_level=step.risk_level,
                explicit_flag=True,
            )
        return self._approval.needs_approval(
            tool_name=step.tool_calls[0].tool_name if step.tool_calls else "",
            risk_level=step.risk_level,
        )

    def _dependencies_met(
        self, step: PlanStep, plan: ExecutionPlan, completed_ids: List[str]
    ) -> bool:
        """Check if all dependency steps have completed successfully."""
        for dep_id in step.dependencies:
            dep_step = next((s for s in plan.steps if s.id == dep_id
                             or str(s.order) == dep_id.replace("step_", "")), None)
            if dep_step and dep_step.status != StepStatus.SUCCESS:
                return False
        return True

    def _try_replan(
        self,
        plan: ExecutionPlan,
        failed_step: PlanStep,
        error: str,
        completed_ids: List[str],
    ) -> Optional[ExecutionPlan]:
        """Attempt to re-plan remaining steps after failure."""
        try:
            self.signals.status_update.emit(f"Re-planning after failed step: {failed_step.title}")
            revised = self._planner.replan(plan, failed_step, error, completed_ids)
            if revised:
                self.signals.plan_ready.emit(revised)
            return revised
        except Exception as e:
            logger.error(f"Re-planning failed: {e}")
            return None

    def _detect_artifacts(self, result: ToolResult, step: PlanStep) -> List[Artifact]:
        """Auto-detect file artifacts from tool output."""
        artifacts = []
        if not isinstance(result.data, dict):
            return artifacts

        # Look for 'path' or 'saved' keys in tool output
        path = result.data.get("path") or result.data.get("saved_path")
        if path and isinstance(path, str):
            from pathlib import Path
            p = Path(path)
            if p.exists():
                ext = p.suffix.lower()
                type_map = {
                    ".xlsx": ArtifactType.EXCEL, ".xls": ArtifactType.EXCEL,
                    ".docx": ArtifactType.WORD, ".doc": ArtifactType.WORD,
                    ".pdf": ArtifactType.PDF, ".csv": ArtifactType.CSV,
                    ".png": ArtifactType.IMAGE, ".jpg": ArtifactType.IMAGE,
                    ".txt": ArtifactType.TEXT,
                }
                artifact = Artifact(
                    name=p.name,
                    path=str(p),
                    artifact_type=type_map.get(ext, ArtifactType.OTHER),
                    size_bytes=p.stat().st_size,
                    description=f"Generated by {step.title}",
                    step_id=step.id,
                )
                artifacts.append(artifact)
                logger.info(f"Artifact detected: {p.name} ({human_size(p.stat().st_size)})")
        return artifacts

    def _build_summary(
        self, plan: ExecutionPlan, session: SessionState, success: bool
    ) -> str:
        """Build a human-readable execution summary for the chat."""
        completed = sum(1 for s in plan.steps if s.status == StepStatus.SUCCESS)
        failed = sum(1 for s in plan.steps if s.status == StepStatus.FAILED)
        skipped = sum(1 for s in plan.steps if s.status in (StepStatus.SKIPPED, StepStatus.CANCELLED))

        status_emoji = "✅" if success else "⚠️"
        lines = [
            f"{status_emoji} **Execution {'Complete' if success else 'Finished with issues'}**",
            f"",
            f"**Goal:** {plan.intent_summary}",
            f"",
            f"**Results:** {completed} succeeded · {failed} failed · {skipped} skipped",
            f"",
        ]

        if session.artifacts:
            lines.append("**Generated Files:**")
            for art in session.artifacts[-5:]:
                size = human_size(art.size_bytes) if art.size_bytes else ""
                lines.append(f"  • {art.name} {f'({size})' if size else ''}")
            lines.append("")

        if failed > 0:
            lines.append("**Failed Steps:**")
            for s in plan.steps:
                if s.status == StepStatus.FAILED:
                    lines.append(f"  • {s.title}: {s.error or 'Unknown error'}")
            lines.append("")

        lines.append("You can view the full execution log and artifacts in the panels on the right.")
        return "\n".join(lines)

    def _save_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        attachments: List[str] = None,
    ):
        """Persist a message to DB and session state."""
        session = self._sessions.get(session_id)
        msg = Message(
            id=short_id(),
            session_id=session_id,
            role=role,
            content=content,
            attachments=attachments or [],
        )
        if session:
            session.messages.append(msg)
        self._db.save_message(
            msg.id, session_id, role.value, content, attachments or []
        )
        return msg
