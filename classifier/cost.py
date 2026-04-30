"""Cost calculation for Claude API calls.

Skill: Cost Calculation — convert (model, input_tokens, output_tokens)
into a USD cost using the published per-MTok pricing, and aggregate spend
across many classifications so an operator can see the unit economics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config import MODEL_PRICING


@dataclass
class CallCost:
    model: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float

    @property
    def total_usd(self) -> float:
        return self.input_cost_usd + self.output_cost_usd


def cost_of_call(model: str, input_tokens: int, output_tokens: int) -> CallCost:
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        raise ValueError(f"Unknown model for pricing: {model}")

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return CallCost(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
    )


@dataclass
class CostTracker:
    calls: list[CallCost] = field(default_factory=list)

    def record(self, call: CallCost) -> None:
        self.calls.append(call)

    @property
    def total_usd(self) -> float:
        return sum(c.total_usd for c in self.calls)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    def average_per_call_usd(self) -> float:
        return self.total_usd / len(self.calls) if self.calls else 0.0

    def summary(self) -> str:
        if not self.calls:
            return "No calls recorded."
        return (
            f"Calls: {len(self.calls)} | "
            f"Input tokens: {self.total_input_tokens:,} | "
            f"Output tokens: {self.total_output_tokens:,} | "
            f"Total: ${self.total_usd:.6f} | "
            f"Avg/call: ${self.average_per_call_usd():.6f}"
        )
