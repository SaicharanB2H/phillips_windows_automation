"""
Planner Agent — the LLM-powered brain of the system.

Responsibilities:
- Parse natural language user requests
- Generate structured JSON execution plans
- Detect missing information and ask follow-up questions
- Re-plan when steps fail
- Maintain execution context across steps
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.schemas import (
    AgentType, ArtifactType, ExecutionPlan, PlanStep,
    RiskLevel, StepStatus, ToolCall, UserRequest,
)
from prompts.planner_prompts import (
    PLANNER_SYSTEM_PROMPT, CLARIFICATION_PROMPT, REPLAN_SYSTEM_PROMPT
)
from services.llm_service import get_llm_service
from utils.helpers import extract_json, short_id
from utils.logger import get_logger

logger = get_logger("agents.planner", "planner")


def _parse_agent(agent_str: str) -> AgentType:
    """Safely parse agent string to AgentType enum."""
    mapping = {
        "file": AgentType.FILE,
        "excel": AgentType.EXCEL,
        "word": AgentType.WORD,
        "email": AgentType.EMAIL,
        "ui": AgentType.UI_AUTOMATION,
        "ui_automation": AgentType.UI_AUTOMATION,
        "planner": AgentType.PLANNER,
    }
    return mapping.get(agent_str.lower().strip(), AgentType.FILE)


def _parse_risk(risk_str: str) -> RiskLevel:
    mapping = {"low": RiskLevel.LOW, "medium": RiskLevel.MEDIUM, "high": RiskLevel.HIGH}
    return mapping.get((risk_str or "low").lower(), RiskLevel.LOW)


class PlannerAgent:
    """
    Interprets user requests via Grok and produces ExecutionPlan objects.
    Maintains context for multi-turn conversations.
    """

    def __init__(self):
        self.llm = get_llm_service()
        self._logger = logger
        self._context: Dict[str, Any] = {}
        self._office_status: Dict[str, bool] = {}
        self._memory: Dict[str, str] = {}   # persistent user memory

    def set_context(self, key: str, value: Any):
        """Store context values that can inform planning (e.g. attached file paths)."""
        self._context[key] = value

    def set_memory(self, memory: Dict[str, str]):
        """Inject persistent user memory so the LLM knows it without being asked."""
        self._memory = memory

    def set_office_status(self, status: Dict[str, bool]):
        """Tell the planner which Office apps are available."""
        self._office_status = status

    def plan(self, request: UserRequest) -> ExecutionPlan:
        """
        Generate a full execution plan for a user request.
        Returns ExecutionPlan — check .clarification_needed before executing.
        """
        logger.info(f"Planning request: {request.text[:100]}...")

        # Build rich context for the system prompt
        system = self._build_system_prompt()
        user_msg = self._build_user_message(request)

        # Call LLM
        raw = self.llm.plan(system, user_msg)

        if raw is None:
            logger.error("Planner received no valid JSON from LLM")
            return self._fallback_plan(request)

        return self._parse_plan(raw, request)

    def replan(
        self,
        original_plan: ExecutionPlan,
        failed_step: PlanStep,
        error_message: str,
        completed_step_ids: List[str],
    ) -> Optional[ExecutionPlan]:
        """
        Generate a revised plan for remaining steps after a failure.
        Returns None if re-planning is not possible.
        """
        logger.info(f"Re-planning after failure: {failed_step.title}")

        remaining_steps = [
            s for s in original_plan.steps
            if s.id not in completed_step_ids and s.id != failed_step.id
        ]

        context = json.dumps({
            "original_intent": original_plan.intent_summary,
            "failed_step": failed_step.title,
            "failed_step_description": failed_step.description,
            "error": error_message,
            "remaining_steps": [s.title for s in remaining_steps],
            "office_availability": self._office_status,
        }, indent=2)

        messages = [
            {"role": "system", "content": REPLAN_SYSTEM_PROMPT + "\n\n" + PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Recovery context:\n{context}\n\nGenerate revised plan:"},
        ]

        try:
            raw_str = self.llm.complete(messages, json_mode=True)
            raw = extract_json(raw_str)
            if raw:
                return self._parse_plan(raw, request=None, session_id=original_plan.session_id)
        except Exception as e:
            logger.error(f"Re-planning failed: {e}")
        return None

    def generate_clarification_question(self, missing_info: List[str]) -> str:
        """Ask Grok to formulate a friendly question about missing information."""
        if not missing_info:
            return ""
        messages = [
            {"role": "system", "content": CLARIFICATION_PROMPT},
            {"role": "user", "content": f"Missing information needed:\n" + "\n".join(f"- {m}" for m in missing_info)},
        ]
        return self.llm.complete(messages)

    # ─────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Add runtime context and persistent memory to the base system prompt."""
        extras = []
        extras.append(f"Current date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        extras.append(f"Output directory: {Path.home() / 'Desktop'}")

        if self._office_status:
            avail = [k for k, v in self._office_status.items() if v]
            unavail = [k for k, v in self._office_status.items() if not v]
            if avail:
                extras.append(f"Available Office apps (use COM): {', '.join(avail)}")
            if unavail:
                extras.append(f"Unavailable Office apps (use file libraries): {', '.join(unavail)}")

        extra_block = "\n".join(f"- {e}" for e in extras)
        prompt = f"{PLANNER_SYSTEM_PROMPT}\n\n## Runtime Context\n{extra_block}"

        # ── Attached files — injected as a loud, unmissable block ───────────
        if self._context.get("attached_files"):
            files = self._context["attached_files"]
            attach_lines = [
                "\n## ATTACHED FILES — CRITICAL",
                "The user has already provided the following file(s). They are saved on disk.",
                "RULES:",
                "  1. Use these EXACT paths in your plan — do NOT use files.smart_find or files.search for them.",
                "  2. Do NOT ask the user where the file is — it is already provided below.",
                "  3. Do NOT ask which reader/tool to use — use the built-in tool for the file type.",
                "     - PDF files  → files.read_pdf(path=...)",
                "     - Excel files → excel.open_workbook(path=...)",
                "     - Word files  → word.open_document(path=...)",
                "     - Text/CSV   → files.read_text(path=...)",
                "",
                "Attached file paths (use directly in tool arguments):",
            ]
            for i, fp in enumerate(files):
                ext = fp.rsplit(".", 1)[-1].lower() if "." in fp else "unknown"
                attach_lines.append(f"  [{i}] {fp}  (type: {ext.upper()}, template: {{{{attached_file_{i}}}}})")
            attach_lines.append(
                f"\nShorthand: the FIRST attached file is always available as {{{{attached_file}}}}"
            )
            prompt += "\n" + "\n".join(attach_lines)

        # Inject persistent user memory — LLM sees these as pre-known facts
        if self._memory:
            mem_lines = ["## Persistent User Memory",
                         "These facts were remembered from previous sessions.",
                         "Use them directly — do NOT ask the user to provide them again.\n"]
            # Group by category prefix for readability
            cats: Dict[str, list] = {}
            for k, v in self._memory.items():
                cat = "facts"
                if any(k.startswith(p) for p in ("user_",)):
                    cat = "User"
                elif any(k.startswith(p) for p in ("contact_",)):
                    cat = "Contacts"
                elif any(k.startswith(p) for p in ("preferred_", "output_")):
                    cat = "Preferences"
                else:
                    cat = "Facts"
                cats.setdefault(cat, []).append(f"  - {k}: {v}")
            for cat, lines in cats.items():
                mem_lines.append(f"### {cat}")
                mem_lines.extend(lines)
            prompt += "\n\n" + "\n".join(mem_lines)

        return prompt

    def _build_user_message(self, request: UserRequest) -> str:
        """Format the user message with context hints."""
        msg = request.text
        if request.attachments:
            msg += "\n\n[ATTACHED FILES — already on disk, use paths directly]"
            for i, fp in enumerate(request.attachments):
                msg += f"\n  File {i}: {fp}"
            msg += "\nDo NOT ask where the file is. Do NOT ask which tool to use."
        if self._context:
            relevant = {k: v for k, v in self._context.items()
                       if k not in ("attached_files",)}
            if relevant:
                msg += f"\n\nAdditional context: {json.dumps(relevant)}"
        return msg

    def _parse_plan(
        self,
        raw: Dict[str, Any],
        request: Optional[UserRequest],
        session_id: str = None,
    ) -> ExecutionPlan:
        """Convert raw LLM JSON response into typed ExecutionPlan."""
        try:
            steps_raw = raw.get("steps", [])
            steps = []

            for i, s in enumerate(steps_raw):
                tool_calls = []
                for tc_raw in s.get("tool_calls", []):
                    tc = ToolCall(
                        tool_name=tc_raw.get("tool_name", ""),
                        agent=_parse_agent(s.get("agent", "file")),
                        arguments=tc_raw.get("arguments", {}),
                        risk_level=_parse_risk(s.get("risk_level", "low")),
                        requires_approval=s.get("requires_approval", False),
                    )
                    tool_calls.append(tc)

                # LLM sometimes returns dependencies as ints [1, 2] instead of
                # strings ["1", "2"] — coerce all values to str to satisfy schema.
                raw_deps = s.get("dependencies", [])
                deps = [str(d) for d in raw_deps] if raw_deps else []

                step = PlanStep(
                    order=s.get("order", i + 1),
                    title=s.get("title", f"Step {i + 1}"),
                    description=s.get("description", ""),
                    agent=_parse_agent(s.get("agent", "file")),
                    risk_level=_parse_risk(s.get("risk_level", "low")),
                    requires_approval=s.get("requires_approval", False),
                    approval_message=s.get("approval_message"),
                    tool_calls=tool_calls,
                    dependencies=deps,
                    fallback_strategy=s.get("fallback_strategy"),
                )
                steps.append(step)

            required_agents = list({s.agent for s in steps})

            plan = ExecutionPlan(
                request_id=request.id if request else short_id(),
                session_id=session_id or (request.session_id if request else short_id()),
                intent_summary=raw.get("intent_summary", "Automation task"),
                steps=steps,
                required_agents=required_agents,
                missing_info=raw.get("missing_info", []),
                clarification_needed=raw.get("clarification_needed", False),
                raw_llm_response=json.dumps(raw),
            )
            logger.info(
                f"Plan created: {len(steps)} steps, "
                f"agents: {[a.value for a in required_agents]}"
            )
            return plan

        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            return self._fallback_plan(request, session_id)

    def _fallback_plan(
        self,
        request: Optional[UserRequest],
        session_id: str = None,
    ) -> ExecutionPlan:
        """Return a minimal plan when LLM fails or is unavailable."""
        return ExecutionPlan(
            request_id=request.id if request else short_id(),
            session_id=session_id or (request.session_id if request else short_id()),
            intent_summary="Could not generate plan — LLM unavailable or returned invalid response.",
            steps=[],
            required_agents=[],
            clarification_needed=True,
            missing_info=["Could not parse request. Please check your API key and try again."],
        )
