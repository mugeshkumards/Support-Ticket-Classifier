"""Pydantic schemas for support ticket classification.

Skill: Schema Design — strongly-typed, validated, enum-constrained outputs
that downstream services can consume with confidence.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Channel(str, Enum):
    WEB_FORM = "web_form"
    EMAIL = "email"


class Category(str, Enum):
    BILLING = "billing"
    SHIPPING = "shipping"
    PRODUCT_DEFECT = "product_defect"
    RETURNS_REFUNDS = "returns_refunds"
    ACCOUNT_LOGIN = "account_login"
    ORDER_STATUS = "order_status"
    PAYMENT_FAILURE = "payment_failure"
    TECHNICAL_BUG = "technical_bug"
    GENERAL_INQUIRY = "general_inquiry"
    OTHER = "other"


class Team(str, Enum):
    BILLING_TEAM = "billing_team"
    LOGISTICS_TEAM = "logistics_team"
    PRODUCT_QUALITY_TEAM = "product_quality_team"
    CUSTOMER_SUCCESS_TEAM = "customer_success_team"
    ENGINEERING_TEAM = "engineering_team"
    GENERAL_SUPPORT = "general_support"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    FRUSTRATED = "frustrated"


class SupportTicket(BaseModel):
    """Raw ticket input from web forms or emails."""

    ticket_id: str
    channel: Channel
    subject: str
    body: str
    customer_email: Optional[str] = None
    received_at: datetime = Field(default_factory=datetime.utcnow)


class TicketClassification(BaseModel):
    """Structured classification output produced by the LLM.

    This is the contract for downstream services (routing, SLA, analytics).
    """

    ticket_id: str
    category: Category
    team: Team
    priority: Priority
    sentiment: Sentiment
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=300)
    reasoning: str = Field(min_length=1, max_length=500)

    model_used: str
    prompt_version: str
    classified_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("summary", "reasoning")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()
