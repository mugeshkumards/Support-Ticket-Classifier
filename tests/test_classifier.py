"""Offline unit tests (no API calls).

Tests cover the pieces that don't need a live LLM: PII redaction, schema
validation, cost calculation. Run with:  python -m pytest tests/
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from classifier.cost import CostTracker, cost_of_call
from classifier.pii import redact
from classifier.schema import (
    Category,
    Channel,
    Priority,
    Sentiment,
    SupportTicket,
    Team,
    TicketClassification,
)


# ----------------------------------------------------------------------- PII

def test_redact_email():
    result = redact("Contact me at alice@example.com please.")
    assert "alice@example.com" not in result.redacted_text
    assert "[REDACTED_EMAIL]" in result.redacted_text
    assert result.counts["EMAIL"] == 1


def test_redact_phone():
    result = redact("Call (415) 555-0142 or 415-555-0142.")
    assert "555-0142" not in result.redacted_text
    assert result.counts["PHONE"] == 2


def test_redact_ssn():
    result = redact("My SSN is 123-45-6789.")
    assert "123-45-6789" not in result.redacted_text
    assert result.counts["SSN"] == 1


def test_redact_credit_card_luhn_valid():
    # 4242 4242 4242 4242 is a known Luhn-valid test card
    result = redact("Card: 4242 4242 4242 4242")
    assert "[REDACTED_CREDIT_CARD]" in result.redacted_text


def test_redact_credit_card_luhn_invalid():
    # 1234 5678 9012 3456 is not Luhn-valid; should NOT be redacted
    result = redact("Order #1234567890123456")
    assert "[REDACTED_CREDIT_CARD]" not in result.redacted_text


def test_redact_no_pii():
    text = "Just a normal message with no PII."
    result = redact(text)
    assert result.redacted_text == text
    assert result.total_redactions == 0


# -------------------------------------------------------------------- schema

def test_classification_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        TicketClassification(
            ticket_id="x",
            category=Category.BILLING,
            team=Team.BILLING_TEAM,
            priority=Priority.HIGH,
            sentiment=Sentiment.NEGATIVE,
            confidence=1.5,                  # out of range
            summary="ok",
            reasoning="ok",
            model_used="claude-haiku-4-5",
            prompt_version="v1.0.0",
        )


def test_classification_rejects_oversized_summary():
    with pytest.raises(ValidationError):
        TicketClassification(
            ticket_id="x",
            category=Category.BILLING,
            team=Team.BILLING_TEAM,
            priority=Priority.HIGH,
            sentiment=Sentiment.NEGATIVE,
            confidence=0.9,
            summary="x" * 400,               # > 300
            reasoning="ok",
            model_used="claude-haiku-4-5",
            prompt_version="v1.0.0",
        )


def test_support_ticket_enum_validation():
    t = SupportTicket(
        ticket_id="x",
        channel="email",
        subject="hi",
        body="hello",
    )
    assert t.channel == Channel.EMAIL


# ---------------------------------------------------------------------- cost

def test_cost_haiku_known_value():
    # Haiku 4.5: $1/MTok input, $5/MTok output
    call = cost_of_call("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert call.input_cost_usd == pytest.approx(1.00)
    assert call.output_cost_usd == pytest.approx(5.00)
    assert call.total_usd == pytest.approx(6.00)


def test_cost_tracker_aggregates():
    tracker = CostTracker()
    tracker.record(cost_of_call("claude-haiku-4-5", 1000, 500))
    tracker.record(cost_of_call("claude-sonnet-4-6", 1000, 500))
    assert len(tracker.calls) == 2
    assert tracker.total_input_tokens == 2000
    assert tracker.total_output_tokens == 1000
    assert tracker.total_usd > 0


def test_cost_unknown_model_raises():
    with pytest.raises(ValueError):
        cost_of_call("claude-fake-99", 100, 100)
