"""Best-effort secret/PII redaction before anything is retained. Not a
security boundary by itself — retained text still lands in an
operator-controlled Hindsight instance — but keeps obvious secrets out of
a long-lived memory store by default."""

from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?i)(password|token|secret)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
]


def scrub(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
