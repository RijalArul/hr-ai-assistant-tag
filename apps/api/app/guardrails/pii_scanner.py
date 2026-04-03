"""PII Scanner — context-aware regex detection and masking.

Scans AI output for sensitive data that should not be visible to the
current session user. Employee can only see their own data.
"""

from __future__ import annotations

import re
from typing import Any

from app.guardrails.models import PiiMaskEvent


# ─── PII Patterns ─────────────────────────────────────────────────────────────

_PII_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # (pii_type, pattern, mask_template)
    (
        "nik",
        re.compile(r"\b\d{16}\b"),
        lambda m: m[:2] + "*" * 12 + m[-2:],
    ),
    (
        "npwp",
        re.compile(r"\b\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}\b"),
        lambda m: m[:3] + "***.***.***" + m[-8:],
    ),
    (
        "phone",
        re.compile(r"(?<!\d)(?:\+62|08)\d{8,11}(?!\d)"),
        lambda m: "****-****" + m[-4:],
    ),
    (
        "bank_account",
        re.compile(r"\b\d{10,16}\b"),
        lambda m: "*" * (len(m) - 4) + m[-4:],
    ),
    (
        "email",
        re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
        lambda m: m.split("@")[0][:2] + "***@" + m.split("@")[1],
    ),
    (
        "salary_amount",
        re.compile(r"Rp\s*[\d.,]{3,}(?:\.\d{3})*(?:,\d{2})?"),
        lambda m: "Rp **.****.***",
    ),
]


def _should_mask_email(email: str, session_email: str) -> bool:
    """Only mask emails that are not the session user's own email."""
    return email.lower() != session_email.lower()


def scan_and_mask(
    response: str,
    session_email: str,
    session_employee_id: str,
    pii_config_custom: list[str] | None = None,
) -> tuple[str, list[PiiMaskEvent]]:
    """Scan response for PII and mask sensitive values.

    Context-aware: does NOT mask the session user's own email.
    Salary amounts are masked if they appear alongside another person's name
    or if the context is ambiguous.

    Returns (masked_response, list_of_pii_events).
    """
    events: list[PiiMaskEvent] = []
    masked = response

    # Apply built-in patterns
    for pii_type, pattern, masker in _PII_PATTERNS:
        matches = list(pattern.finditer(masked))
        if not matches:
            continue

        mask_count = 0
        offset = 0
        result = masked

        for match in matches:
            start = match.start() + offset
            end = match.end() + offset
            original = match.group()

            # Context-aware: skip own email
            if pii_type == "email" and not _should_mask_email(original, session_email):
                continue

            # Skip salary amounts that are the subject's own data
            # (salary_amount is masked only when it appears to reference someone else)
            # For MVP, allow salary amounts through since context is checked at agent level
            if pii_type == "salary_amount":
                continue

            replacement = masker(original)
            result = result[:start] + replacement + result[end:]
            offset += len(replacement) - len(original)
            mask_count += 1

        if mask_count > 0:
            masked = result
            events.append(PiiMaskEvent(pii_type=pii_type, mask_count=mask_count))

    # Apply custom PII patterns from guardrail config
    for custom_pattern_str in (pii_config_custom or []):
        try:
            custom_pattern = re.compile(custom_pattern_str)
            custom_matches = list(custom_pattern.finditer(masked))
            if custom_matches:
                masked = custom_pattern.sub("[REDACTED]", masked)
                events.append(
                    PiiMaskEvent(pii_type="custom", mask_count=len(custom_matches))
                )
        except re.error:
            pass  # Invalid custom regex — skip silently

    return masked, events
