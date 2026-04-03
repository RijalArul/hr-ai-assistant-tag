"""Evidence-based hallucination checker.

Validates that numeric claims in the AI response can be traced back
to data returned by the agents. No LLM re-check — purely deterministic.
"""

from __future__ import annotations

import re
from typing import Any

from app.guardrails.models import HallucinationFlag

_LOW_CONFIDENCE_DISCLAIMER = (
    "Informasi ini mungkin tidak lengkap. Silakan konfirmasi dengan tim HR."
)
_NUMERIC_MISMATCH_DISCLAIMER = (
    "Catatan: Silakan konfirmasi detail angka ini langsung ke tim HR "
    "untuk memastikan keakuratannya."
)
_POLICY_CLAIM_DISCLAIMER = (
    "Catatan: Informasi ini berdasarkan dokumen kebijakan yang tersedia. "
    "Silakan verifikasi dengan HR untuk aturan terbaru."
)

# Match Rp amounts or plain integers >= 4 digits
_NUMBER_RE = re.compile(
    r"Rp\s*([\d.,]+)|"           # Rp 12.000.000
    r"\b(\d{1,3}(?:[.,]\d{3})+)\b|"  # 12.000.000
    r"\b(\d+)\s+hari\b|"         # 11 hari
    r"\b(\d+)\s+jam\b"           # 8 jam
)


def _extract_numbers_from_text(text: str) -> list[float]:
    """Extract numeric values from response text."""
    numbers: list[float] = []
    for match in _NUMBER_RE.finditer(text):
        raw = next(g for g in match.groups() if g is not None)
        cleaned = raw.replace(".", "").replace(",", ".")
        try:
            numbers.append(float(cleaned))
        except ValueError:
            pass
    return numbers


def _flatten_evidence_numbers(evidence: list[Any]) -> list[float]:
    """Recursively extract all numeric values from agent evidence."""
    numbers: list[float] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, (int, float)):
            numbers.append(float(obj))
        elif isinstance(obj, str):
            try:
                numbers.append(float(obj.replace(",", ".")))
            except ValueError:
                pass
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)

    for item in evidence:
        _walk(item)

    return numbers


def _approximately_matches(
    num: float,
    evidence_numbers: list[float],
    tolerance_pct: float = 0.01,
) -> bool:
    """Check if num matches any evidence number within tolerance."""
    if not evidence_numbers:
        return True  # No evidence available — don't flag
    for ev_num in evidence_numbers:
        if ev_num == 0 and num == 0:
            return True
        if ev_num != 0:
            if abs(num - ev_num) / abs(ev_num) <= tolerance_pct:
                return True
        if abs(num - ev_num) < 1:  # near-zero absolute difference
            return True
    return False


def check_hallucination(
    response: str,
    evidence: list[Any],
    route_confidence: float,
    tolerance_pct: float = 0.01,
) -> tuple[str, list[HallucinationFlag], bool]:
    """Check response for potential hallucinations.

    Returns (final_response, flags, disclaimer_added).
    """
    flags: list[HallucinationFlag] = []
    disclaimers: list[str] = []

    # Low confidence → add disclaimer regardless
    if route_confidence < 0.6:
        disclaimers.append(_LOW_CONFIDENCE_DISCLAIMER)

    # Extract and verify numbers
    response_numbers = _extract_numbers_from_text(response)
    evidence_numbers = _flatten_evidence_numbers(evidence)

    if response_numbers and evidence_numbers:
        for num in response_numbers:
            if not _approximately_matches(num, evidence_numbers, tolerance_pct):
                flags.append(
                    HallucinationFlag(
                        number=str(num),
                        reason="Number in response does not match any evidence value.",
                    )
                )

        if flags and _NUMERIC_MISMATCH_DISCLAIMER not in disclaimers:
            disclaimers.append(_NUMERIC_MISMATCH_DISCLAIMER)

    final_response = response
    if disclaimers:
        final_response = response.rstrip() + "\n\n" + " ".join(disclaimers)

    return final_response, flags, bool(disclaimers)
