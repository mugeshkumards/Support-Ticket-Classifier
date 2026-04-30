"""PII detection and redaction.

Skill: PII Detection / Redaction — strip emails, phone numbers, credit-card
numbers, SSNs, and IP addresses from ticket bodies BEFORE the text is sent
to the LLM. The redacted body is what goes to Claude; the raw body never
leaves the application boundary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


@dataclass
class RedactionResult:
    redacted_text: str
    counts: dict[str, int]

    @property
    def total_redactions(self) -> int:
        return sum(self.counts.values())


_PATTERNS: dict[str, Pattern[str]] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "PHONE": re.compile(
        r"(?:(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})"
    ),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "IP_ADDRESS": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
    ),
}


def _luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def redact(text: str) -> RedactionResult:
    counts: dict[str, int] = {}
    redacted = text

    for label, pattern in _PATTERNS.items():
        if label == "CREDIT_CARD":
            def _cc_sub(match: re.Match[str]) -> str:
                if _luhn_valid(match.group(0)):
                    counts[label] = counts.get(label, 0) + 1
                    return f"[REDACTED_{label}]"
                return match.group(0)

            redacted = pattern.sub(_cc_sub, redacted)
        else:
            new_text, n = pattern.subn(f"[REDACTED_{label}]", redacted)
            if n:
                counts[label] = n
            redacted = new_text

    return RedactionResult(redacted_text=redacted, counts=counts)
