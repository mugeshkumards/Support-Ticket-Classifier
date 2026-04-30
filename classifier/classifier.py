"""Core ticket classifier (OpenRouter / OpenAI-compatible).

Skills covered here:
  - Structured Output from LLM: uses OpenAI tool/function calling to force
    the model to emit a payload that matches our JSON schema. More robust
    than asking for "JSON in the response text".
  - Validate LLM Response: every tool-call payload is parsed through
    Pydantic, and additional business rules (category->team consistency,
    confidence threshold) are enforced afterwards.
  - Control LLM's Non-Determinism: temperature=0, deterministic system
    prompt, enum-constrained schema, forced tool choice.
  - Fallback / Retry: transient API errors trigger exponential backoff;
    LOW-confidence or invalid responses on the primary model trigger a
    one-shot escalation to a stronger fallback model.
  - PII Detection / Redaction: ticket bodies are redacted before being
    sent to the API.
  - Cost Calculation: every call's usage is recorded on a CostTracker.
  - Prompt Versioning: the active prompt's version is stamped on every
    classification result.
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Optional

import openai
from pydantic import ValidationError

from config import (
    FALLBACK_MODEL,
    INITIAL_BACKOFF_SECONDS,
    MAX_RETRIES,
    MIN_CONFIDENCE_THRESHOLD,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_BASE_URL,
    OPENROUTER_SITE_URL,
    PRIMARY_MODEL,
)

from .cost import CostTracker, cost_of_call
from .pii import redact
from .prompts import CURRENT_PROMPT
from .schema import (
    Category,
    SupportTicket,
    Team,
    TicketClassification,
)

logger = logging.getLogger(__name__)


# OpenAI-style "function" tool. Same schema we used before — the difference
# is just the wire format (`{"type": "function", "function": {...}}`).
_CLASSIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_classification",
        "description": (
            "Submit the structured classification for the support ticket. "
            "You must call this tool exactly once. Do not return free-text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                },
                "team": {
                    "type": "string",
                    "enum": [t.value for t in Team],
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "neutral", "negative", "frustrated"],
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Honest self-assessment: 0.9+ = clear, 0.5- = ambiguous.",
                },
                "summary": {
                    "type": "string",
                    "description": "<= 300 chars. One-sentence summary, no PII.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "<= 500 chars. Why you chose this classification.",
                },
            },
            "required": [
                "category", "team", "priority", "sentiment",
                "confidence", "summary", "reasoning",
            ],
            "additionalProperties": False,
        },
    },
}


# Category -> team mapping mirrors the rule in prompts.py. Enforced
# server-side as defense in depth: even if the model picks the right
# category but the wrong team, we correct the team rather than reject.
_CATEGORY_TO_TEAM: dict[Category, Team] = {
    Category.BILLING:          Team.BILLING_TEAM,
    Category.PAYMENT_FAILURE:  Team.BILLING_TEAM,
    Category.SHIPPING:         Team.LOGISTICS_TEAM,
    Category.ORDER_STATUS:     Team.LOGISTICS_TEAM,
    Category.PRODUCT_DEFECT:   Team.PRODUCT_QUALITY_TEAM,
    Category.RETURNS_REFUNDS:  Team.CUSTOMER_SUCCESS_TEAM,
    Category.GENERAL_INQUIRY:  Team.CUSTOMER_SUCCESS_TEAM,
    Category.TECHNICAL_BUG:    Team.ENGINEERING_TEAM,
    Category.ACCOUNT_LOGIN:    Team.ENGINEERING_TEAM,
    Category.OTHER:            Team.GENERAL_SUPPORT,
}


class ClassificationError(Exception):
    """Raised when the LLM cannot produce a valid classification."""


class TicketClassifier:
    def __init__(
        self,
        primary_model: str = PRIMARY_MODEL,
        fallback_model: str = FALLBACK_MODEL,
        cost_tracker: Optional[CostTracker] = None,
        api_key: Optional[str] = None,
        base_url: str = OPENROUTER_BASE_URL,
    ) -> None:
        key = api_key or OPENROUTER_API_KEY
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env "
                "and fill in your key from https://openrouter.ai/keys."
            )

        # OpenRouter is OpenAI-API-compatible — we just point the SDK at it.
        # The two extra headers are optional but show up nicely on the
        # OpenRouter dashboard / public leaderboards.
        self.client = openai.OpenAI(
            api_key=key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_NAME,
            },
        )
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.cost_tracker = cost_tracker or CostTracker()

    # ------------------------------------------------------------------ public

    def classify(self, ticket: SupportTicket) -> TicketClassification:
        """Classify a ticket. Escalates to the fallback model if the primary
        returns low confidence or fails validation."""

        redaction = redact(ticket.body)
        if redaction.total_redactions:
            logger.info(
                "Redacted %d PII items from ticket %s: %s",
                redaction.total_redactions, ticket.ticket_id, redaction.counts,
            )
        safe_body = redaction.redacted_text

        try:
            return self._classify_with_model(
                ticket, safe_body, self.primary_model,
            )
        except ClassificationError as primary_err:
            logger.warning(
                "Primary model failed on ticket %s: %s. Escalating to %s.",
                ticket.ticket_id, primary_err, self.fallback_model,
            )
            return self._classify_with_model(
                ticket, safe_body, self.fallback_model,
            )

    # ----------------------------------------------------------------- internal

    def _classify_with_model(
        self,
        ticket: SupportTicket,
        safe_body: str,
        model: str,
    ) -> TicketClassification:
        user_message = CURRENT_PROMPT.user_template.format(
            channel=ticket.channel.value,
            subject=ticket.subject,
            body=safe_body,
            ticket_id=ticket.ticket_id,
        )

        response = self._call_with_retry(
            model=model,
            system=CURRENT_PROMPT.system,
            user_message=user_message,
        )

        tool_args = self._extract_tool_args(response)
        classification = self._validate_and_build(
            tool_args=tool_args,
            ticket=ticket,
            model=model,
        )

        # If confidence is too low on the primary model, raise so the caller
        # escalates. On the fallback model we accept whatever we got.
        if (
            model == self.primary_model
            and classification.confidence < MIN_CONFIDENCE_THRESHOLD
        ):
            raise ClassificationError(
                f"Low confidence {classification.confidence:.2f} "
                f"< threshold {MIN_CONFIDENCE_THRESHOLD}"
            )

        return classification

    def _call_with_retry(self, model: str, system: str, user_message: str):
        """Call the API with exponential backoff on transient errors."""
        last_exc: Optional[Exception] = None

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_message},
                    ],
                    tools=[_CLASSIFY_TOOL],
                    tool_choice={
                        "type": "function",
                        "function": {"name": "submit_classification"},
                    },
                    max_tokens=1024,
                )
                if response.usage:
                    self.cost_tracker.record(cost_of_call(
                        model=model,
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                    ))
                return response

            except openai.RateLimitError as e:
                last_exc = e
                delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "Rate limited (attempt %d/%d). Retrying in %.1fs.",
                    attempt + 1, MAX_RETRIES, delay,
                )
                time.sleep(delay)
            except openai.APIStatusError as e:
                last_exc = e
                if e.status_code < 500:
                    # 4xx (other than 429) won't get better with retries.
                    raise
                delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "Server error %s (attempt %d/%d). Retrying in %.1fs.",
                    e.status_code, attempt + 1, MAX_RETRIES, delay,
                )
                time.sleep(delay)
            except openai.APIConnectionError as e:
                last_exc = e
                delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "Connection error (attempt %d/%d): %s. Retrying in %.1fs.",
                    attempt + 1, MAX_RETRIES, e, delay,
                )
                time.sleep(delay)

        raise ClassificationError(
            f"API failed after {MAX_RETRIES} retries: {last_exc}"
        )

    @staticmethod
    def _extract_tool_args(response) -> dict:
        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message.tool_calls:
            finish = getattr(choice, "finish_reason", None) if choice else None
            raise ClassificationError(
                f"Model did not call submit_classification "
                f"(finish_reason={finish})."
            )

        tool_call = choice.message.tool_calls[0]
        if tool_call.function.name != "submit_classification":
            raise ClassificationError(
                f"Model called unexpected tool: {tool_call.function.name}"
            )

        try:
            return json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            raise ClassificationError(
                f"Tool arguments were not valid JSON: {e}. "
                f"Raw: {tool_call.function.arguments[:500]}"
            ) from e

    @staticmethod
    def _validate_and_build(
        tool_args: dict,
        ticket: SupportTicket,
        model: str,
    ) -> TicketClassification:
        try:
            classification = TicketClassification(
                ticket_id=ticket.ticket_id,
                category=tool_args["category"],
                team=tool_args["team"],
                priority=tool_args["priority"],
                sentiment=tool_args["sentiment"],
                confidence=tool_args["confidence"],
                summary=tool_args["summary"],
                reasoning=tool_args["reasoning"],
                model_used=model,
                prompt_version=CURRENT_PROMPT.version,
            )
        except (ValidationError, KeyError) as e:
            raise ClassificationError(
                f"LLM output failed schema validation: {e}. "
                f"Raw input: {json.dumps(tool_args)[:500]}"
            ) from e

        # Business rule: enforce category -> team consistency.
        expected_team = _CATEGORY_TO_TEAM.get(classification.category)
        if expected_team and classification.team != expected_team:
            logger.info(
                "Correcting team for ticket %s: %s -> %s (category=%s).",
                ticket.ticket_id,
                classification.team.value, expected_team.value,
                classification.category.value,
            )
            classification = classification.model_copy(
                update={"team": expected_team},
            )

        return classification
