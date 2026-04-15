"""
LLM Service — Groq API Integration.

Wraps the Groq API (OpenAI-compatible, console.groq.com) with:
- Retry logic via tenacity
- Structured JSON output enforcement
- Token / latency logging
- Prompt template support
- Mock mode for testing without API key
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from models.schemas import LLMMessage, LLMRequest, LLMResponse
from utils.helpers import extract_json
from utils.logger import get_logger

logger = get_logger("services.llm", "llm")


# ─────────────────────────────────────────────
# Mock Responses (for Demo / Dry-Run mode)
# ─────────────────────────────────────────────

MOCK_PLAN_RESPONSE = {
    "intent_summary": "Demo plan: Open Excel, summarize data, create Word report, draft email",
    "clarification_needed": False,
    "missing_info": [],
    "steps": [
        {
            "order": 1, "title": "Find Excel File",
            "description": "Search Downloads for the latest .xlsx file",
            "agent": "file", "risk_level": "low",
            "requires_approval": False,
            "tool_calls": [{"tool_name": "files.search", "arguments": {"directory": "Downloads", "pattern": "*.xlsx", "latest": True}}],
            "dependencies": [], "fallback_strategy": "Ask user to provide path"
        },
        {
            "order": 2, "title": "Read Excel Data",
            "description": "Open workbook and read sheet data",
            "agent": "excel", "risk_level": "low",
            "requires_approval": False,
            "tool_calls": [{"tool_name": "excel.open_workbook", "arguments": {"path": "{{step_1.result.path}}"}},
                           {"tool_name": "excel.get_used_range", "arguments": {"sheet_name": "Sheet1"}}],
            "dependencies": ["step_1"], "fallback_strategy": "Use openpyxl"
        },
        {
            "order": 3, "title": "Create Word Report",
            "description": "Generate formatted Word document with summary",
            "agent": "word", "risk_level": "low",
            "requires_approval": False,
            "tool_calls": [{"tool_name": "word.create_document", "arguments": {}},
                           {"tool_name": "word.insert_heading", "arguments": {"text": "Q1 Sales Summary", "level": 1}},
                           {"tool_name": "word.insert_table", "arguments": {"data": "{{step_2.result.data}}"}}],
            "dependencies": ["step_2"], "fallback_strategy": "Use python-docx"
        },
        {
            "order": 4, "title": "Draft Email",
            "description": "Draft Outlook email with Word report attached",
            "agent": "email", "risk_level": "medium",
            "requires_approval": True,
            "approval_message": "Ready to draft an email. Approve to proceed?",
            "tool_calls": [{"tool_name": "email.create_draft", "arguments": {"to": "manager@example.com", "subject": "Q1 Report", "body": "{{llm_generated_body}}", "attachments": ["{{step_3.result.path}}"]}}],
            "dependencies": ["step_3"], "fallback_strategy": "Save draft only"
        }
    ]
}


# ─────────────────────────────────────────────
# LLM Service
# ─────────────────────────────────────────────

class LLMService:
    """
    Grok-powered LLM service for planning, summarization, and generation.
    Uses the OpenAI-compatible xAI API endpoint.
    """

    def __init__(self):
        self.api_key = os.getenv("GROK_API_KEY", "")
        self.base_url = os.getenv("GROK_BASE_URL", "https://api.groq.com/openai/v1")
        self.model = os.getenv("GROK_MODEL", "llama-3.3-70b-versatile")
        self.max_tokens = int(os.getenv("GROK_MAX_TOKENS", "4096"))
        self.temperature = float(os.getenv("GROK_TEMPERATURE", "0.2"))
        self.mock_mode = os.getenv("MOCK_LLM", "false").lower() == "true"

        self._client = None
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_calls = 0

        if not self.mock_mode and self.api_key:
            self._init_client()

    def _init_client(self):
        """Lazily initialize the OpenAI-compatible client pointed at Groq."""
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
            logger.info(f"LLM client initialized — base={self.base_url} model={self.model}")
        except ImportError:
            logger.error("openai package not installed. Run: pip install openai")
        except Exception as e:
            logger.error(f"Failed to init LLM client: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _call_api(self, request: LLMRequest) -> LLMResponse:
        """Raw API call with retry. Do not call directly — use complete() or plan()."""
        if self._client is None:
            raise RuntimeError("LLM client not initialized. Check GROK_API_KEY.")

        start = time.time()
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        kwargs: Dict[str, Any] = {
            "model": request.model or self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        # NOTE: Groq llama models do not support response_format=json_object.
        # JSON enforcement is handled via system prompt injection in complete().

        response = self._client.chat.completions.create(**kwargs)
        elapsed = (time.time() - start) * 1000

        content = response.choices[0].message.content or ""
        in_tok = response.usage.prompt_tokens if response.usage else 0
        out_tok = response.usage.completion_tokens if response.usage else 0

        self._total_input_tokens += in_tok
        self._total_output_tokens += out_tok
        self._total_calls += 1

        logger.info(
            f"LLM call #{self._total_calls} | "
            f"in={in_tok} out={out_tok} | {elapsed:.0f}ms"
        )

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            duration_ms=elapsed,
        )

    def complete(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send messages to Groq and return the response string.
        Set json_mode=True to enforce JSON output via system prompt injection.
        Groq llama models don't support response_format, so we instruct via prompt.
        """
        if self.mock_mode or not self.api_key:
            logger.warning("Mock mode: returning placeholder LLM response")
            if json_mode:
                return json.dumps(MOCK_PLAN_RESPONSE, indent=2)
            return "This is a mock LLM response. Set GROK_API_KEY in .env to use Groq."

        msgs = list(messages)

        if json_mode:
            # Inject JSON enforcement into system message (works across all Groq models)
            json_instruction = (
                "\n\nCRITICAL: Your response MUST be valid JSON only. "
                "No markdown fences, no explanation text, no commentary before or after. "
                "Start your response with { and end with }."
            )
            if msgs and msgs[0]["role"] == "system":
                msgs[0] = {**msgs[0], "content": msgs[0]["content"] + json_instruction}
            else:
                msgs.insert(0, {"role": "system", "content": json_instruction})

        llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in msgs]
        request = LLMRequest(
            messages=llm_messages,
            model=model,
            max_tokens=self.max_tokens,
            temperature=temperature or self.temperature,
            response_format=None,  # Never pass response_format to Groq
        )
        response = self._call_api(request)
        return response.content

    def plan(self, system_prompt: str, user_request: str) -> Optional[Dict[str, Any]]:
        """
        Generate an execution plan as structured JSON.
        Returns parsed dict or None on failure.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
        ]
        try:
            raw = self.complete(messages, json_mode=True)
            parsed = extract_json(raw)
            if parsed is None:
                logger.error(f"Failed to parse plan JSON:\n{raw[:500]}")
            return parsed
        except Exception as e:
            logger.error(f"LLM plan generation failed: {e}")
            return None

    def summarize(self, content: str, instruction: str = "Summarize concisely:") -> str:
        """Summarize arbitrary content."""
        messages = [
            {"role": "system", "content": "You are a professional business analyst. Be concise and precise."},
            {"role": "user", "content": f"{instruction}\n\n{content}"},
        ]
        return self.complete(messages)

    def generate_text(self, prompt: str, context: str = "") -> str:
        """Generate text content (for emails, report bodies, etc.)."""
        system = (
            "You are a professional business writer. "
            "Generate clear, formal, and concise content. "
            "Return only the generated text, no meta-commentary."
        )
        user = f"{context}\n\n{prompt}" if context else prompt
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.complete(messages, temperature=0.4)

    def extract_intent(self, user_input: str) -> Dict[str, Any]:
        """
        Quick intent extraction — returns structured dict with:
        action, targets, files, output_format, delivery_channel
        """
        prompt = (
            "Extract the intent from this automation request. "
            "Return JSON with keys: action, targets (list), files (list), "
            "output_format, delivery_channel, priority_order (list of app names).\n\n"
            f"Request: {user_input}"
        )
        messages = [
            {"role": "system", "content": "You extract structured intent from natural language automation requests. Output JSON only."},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = self.complete(messages, json_mode=True)
            return extract_json(raw) or {}
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            return {}

    def suggest_recovery(self, error: str, step_description: str) -> str:
        """Ask LLM to suggest a recovery strategy for a failed step."""
        messages = [
            {"role": "system", "content": "You are a Windows automation expert. Suggest brief, actionable recovery strategies."},
            {"role": "user", "content": f"Step: {step_description}\nError: {error}\n\nSuggest 2-3 recovery strategies:"},
        ]
        return self.complete(messages)

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_calls": self._total_calls,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "model": self.model,
            "mock_mode": self.mock_mode,
        }


# Module-level singleton
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create the module-level LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
