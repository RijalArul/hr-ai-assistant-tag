"""Multi-layer prompt injection detector.

Layer 1: Pattern matching (regex)
Layer 2: Input sanitization (control chars, unicode normalization)
Layer 3: Context boundary enforcement
"""

from __future__ import annotations

import re
import unicodedata

# ─── Layer 1: Known injection patterns ────────────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
        r"forget\s+(?:everything|what|all)",
        r"you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?(?:different|new|other|another)",
        r"pretend\s+(?:to\s+be|you\s+are|you're)",
        r"act\s+as\s+(?:if\s+you\s+have\s+no|an?\s+)?",
        r"system\s*prompt\s*:",
        r"<\s*/?system\s*>",
        r"\[INST\]",
        r"\[\/INST\]",
        r"base64\s+encoded\s+instructions",
        r"encoded\s+in\s+hex",
        r"disregard\s+(?:your\s+)?(?:previous|prior|all)\s+",
        r"new\s+instructions?\s*:",
        r"override\s+(?:your\s+)?(?:instructions?|rules?|constraints?)",
        r"jailbreak",
        r"DAN\s+mode",
        r"developer\s+mode",
        r"do\s+anything\s+now",
    ]
]

# ─── Layer 2: Sanitization ────────────────────────────────────────────────────

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u2060-\u2064]")


def sanitize_input(message: str) -> str:
    """Strip control characters, normalize unicode, remove zero-width chars."""
    # Unicode NFC normalization
    message = unicodedata.normalize("NFC", message)
    # Strip dangerous control characters (keep \n and \t)
    message = _CONTROL_CHAR_RE.sub("", message)
    # Remove zero-width / invisible characters
    message = _ZERO_WIDTH_RE.sub("", message)
    # Collapse excessive whitespace but preserve single newlines
    lines = [" ".join(line.split()) for line in message.splitlines()]
    return "\n".join(line for line in lines if line).strip()


# ─── Layer 3: Context boundary ────────────────────────────────────────────────

_SYSTEM_DELIMITER_START = "[SYSTEM_CONTEXT]"
_SYSTEM_DELIMITER_END = "[END_SYSTEM_CONTEXT]"
_USER_DELIMITER_START = "[USER_MESSAGE]"
_USER_DELIMITER_END = "[END_USER_MESSAGE]"

_SYSTEM_PROMPT_TEMPLATE = (
    "Kamu adalah HR AI assistant yang bekerja untuk {company_name}. "
    "Bantu karyawan dengan pertanyaan terkait HR: payroll, cuti, kehadiran, "
    "kebijakan perusahaan, dan struktur organisasi. "
    "Selalu netral, faktual, dan profesional. "
    "Jangan berikan saran hukum, keuangan, atau medis."
)


def wrap_with_context_boundary(
    message: str,
    company_name: str = "perusahaan",
) -> str:
    """Wrap message with context boundary delimiters to prevent injection."""
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(company_name=company_name)
    return (
        f"{_SYSTEM_DELIMITER_START}\n"
        f"{system_prompt}\n"
        f"{_SYSTEM_DELIMITER_END}\n\n"
        f"{_USER_DELIMITER_START}\n"
        f"{message}\n"
        f"{_USER_DELIMITER_END}"
    )


# ─── Main detection function ──────────────────────────────────────────────────

def detect_injection(message: str) -> tuple[bool, str | None]:
    """Run Layer 1 pattern matching.

    Returns (is_injection_detected, matched_pattern_description).
    """
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(message)
        if match:
            return True, f"Matched pattern: {pattern.pattern[:60]}"
    return False, None


def check_and_sanitize(message: str) -> tuple[bool, str, str | None]:
    """Full input processing pipeline.

    Returns (is_blocked, sanitized_message, block_reason).
    """
    sanitized = sanitize_input(message)

    is_injection, reason = detect_injection(sanitized)
    if is_injection:
        return True, sanitized, reason

    return False, sanitized, None
