
from __future__ import annotations

import json
import logging
import random
import time
from typing import Optional

import openai
import httpx
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

# ── OpenAI function-calling tool definition ──────────────────────────
_CLASSIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_classification",
        "description": "Submit the structured classification for a support ticket.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                    "description": "The ticket category.",
                },
                "team": {
                    "type": "string",
                    "enum": [t.value for t in Team],
                    "description": "The team to route the ticket to.",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Ticket priority level.",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "neutral", "negative", "frustrated"],
                    "description": "Customer sentiment.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Classification confidence (0-1).",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the ticket (max 300 chars).",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Reasoning behind the classification (max 500 chars).",
                },
            },
            "required": [
                "category",
                "team",
                "priority",
                "sentiment",
                "confidence",
                "summary",
                "reasoning",
            ],
        },
    },
}


class ClassificationError(Exception):
    pass


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
            raise RuntimeError("OPENROUTER_API_KEY is not set.")

        # 🔥 FIX: Add timeout + stable HTTP client
        http_client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=20.0)
        )

        self.client = openai.OpenAI(
            api_key=key,
            base_url=base_url,
            http_client=http_client,
            default_headers={
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_NAME,
            },
        )

        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.cost_tracker = cost_tracker or CostTracker()

    # ========================= PUBLIC =========================

    def classify(self, ticket: SupportTicket) -> TicketClassification:

        redaction = redact(ticket.body)
        safe_body = redaction.redacted_text

        try:
            return self._classify_with_model(
                ticket, safe_body, self.primary_model
            )
        except ClassificationError as e:
            logger.warning(f"Primary failed → fallback: {e}")
            return self._classify_with_model(
                ticket, safe_body, self.fallback_model
            )

    # ========================= INTERNAL =========================

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
            tool_args, ticket, model
        )

        if (
            model == self.primary_model
            and classification.confidence < MIN_CONFIDENCE_THRESHOLD
        ):
            raise ClassificationError("Low confidence")

        return classification

    def _call_with_retry(self, model: str, system: str, user_message: str):

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
                    self.cost_tracker.record(
                        cost_of_call(
                            model=model,
                            input_tokens=response.usage.prompt_tokens,
                            output_tokens=response.usage.completion_tokens,
                        )
                    )

                return response

            except openai.RateLimitError as e:
                last_exc = e
                delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(f"Rate limit → retry in {delay}s")
                time.sleep(delay)

            except openai.APIConnectionError as e:
                last_exc = e
                delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt)

                # 🔥 KEY DEBUG LINE
                logger.error(f"Connection error FULL: {repr(e)}")

                logger.warning(
                    f"Connection error attempt {attempt+1}: retry in {delay}s"
                )
                time.sleep(delay)

            except openai.APIStatusError as e:
                last_exc = e
                if e.status_code < 500:
                    raise
                delay = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(f"Server error {e.status_code}, retry...")
                time.sleep(delay)

        raise ClassificationError(
            f"API failed after {MAX_RETRIES} retries: {last_exc}"
        )

    def _extract_tool_args(self, response) -> dict:

        choice = response.choices[0]
        tool_call = choice.message.tool_calls[0]

        return json.loads(tool_call.function.arguments)

    def _validate_and_build(
        self,
        tool_args: dict,
        ticket: SupportTicket,
        model: str,
    ) -> TicketClassification:

        try:
            return TicketClassification(
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
            raise ClassificationError(f"Validation failed: {e}")

