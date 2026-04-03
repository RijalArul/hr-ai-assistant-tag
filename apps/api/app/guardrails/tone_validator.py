"""Tone validator — prohibited content and NVC compliance check (P0 keyword-based).

P0: deterministic keyword/pattern check
P2 (future): MiniMax judge for full NVC compliance
"""

from __future__ import annotations

import re

_PROHIBITED_LEGAL_ADVICE = re.compile(
    r"\b(?:anda\s+berhak\s+menuntut|konsultasikan\s+dengan\s+pengacara|"
    r"dasar\s+hukumnya\s+adalah|melanggar\s+hukum|gugatan\s+hukum|"
    r"you\s+should\s+sue|legal\s+action|consult\s+a\s+lawyer)\b",
    re.IGNORECASE,
)

_PROHIBITED_FINANCIAL_ADVICE = re.compile(
    r"\b(?:investasikan\s+di|beli\s+saham|portofolio\s+investasi|"
    r"you\s+should\s+invest|financial\s+advice|buy\s+stocks)\b",
    re.IGNORECASE,
)

_PROHIBITED_MEDICAL_ADVICE = re.compile(
    r"\b(?:minum\s+obat|dosis\s+yang\s+tepat|konsultasikan\s+ke\s+dokter\s+untuk|"
    r"gejala\s+penyakit|medical\s+diagnosis|take\s+this\s+medication)\b",
    re.IGNORECASE,
)

_PROFANITY_PATTERNS = re.compile(
    r"\b(?:bangsat|anjing|brengsek|fuck|shit|ass\s*hole)\b",
    re.IGNORECASE,
)

_DISCLAIMER_TEMPLATE = (
    "\n\nCatatan: Respons ini hanya bersifat informasi HR dan bukan merupakan "
    "saran hukum, keuangan, atau medis."
)


def validate_tone(response: str, nvc_strict: bool = False) -> tuple[str, bool]:
    """Check for prohibited content and optionally add a disclaimer.

    Returns (final_response, tone_warning_triggered).
    """
    warning = False
    final = response

    # Remove obvious profanity (replace with placeholder)
    if _PROFANITY_PATTERNS.search(response):
        final = _PROFANITY_PATTERNS.sub("[dihapus]", final)
        warning = True

    # Add disclaimer if response contains advisory language
    has_legal = bool(_PROHIBITED_LEGAL_ADVICE.search(final))
    has_financial = bool(_PROHIBITED_FINANCIAL_ADVICE.search(final))
    has_medical = bool(_PROHIBITED_MEDICAL_ADVICE.search(final))

    if has_legal or has_financial or has_medical:
        final = final.rstrip() + _DISCLAIMER_TEMPLATE
        warning = True

    return final, warning
