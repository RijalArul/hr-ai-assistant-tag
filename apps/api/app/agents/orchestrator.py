from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.company_agent import run_company_agent
from app.agents.file_agent import run_file_agent
from app.agents.hr_data_agent import run_hr_data_agent
from app.core.security import SessionContext
from app.guardrails.sensitive_cases import (
    SensitiveCaseAssessment,
    assess_sensitive_case,
)
from app.models import (
    AgentRoute,
    AgentTraceStep,
    ConversationIntent,
    ConversationRequestCategory,
    IntentAssessment,
    OrchestratorRequest,
    OrchestratorResponse,
    ResponseMode,
    SensitivityAssessment,
)
from app.services.cache import get_cache
from app.services.db import AsyncSessionLocal
from app.services.execution_intent import assess_action_execution_intent
from app.services.minimax import ProviderClassificationResult, classify_with_minimax
from app.services.semantic_router import (
    AgentCapabilityResult,
    SemanticIntentResult,
    retrieve_agent_capabilities,
    retrieve_intent_candidates,
)
from shared import SensitivityLevel

INTENT_KEYWORDS: OrderedDict[ConversationIntent, list[str]] = OrderedDict(
    [
        (
            ConversationIntent.PAYROLL_DOCUMENT_REQUEST,
            ["slip gaji", "salary slip", "payslip", "pay slip"],
        ),
        (
            ConversationIntent.PAYROLL_INFO,
            ["gaji", "salary", "payroll", "bpjs", "pph21", "kompensasi", "potongan"],
        ),
        (
            ConversationIntent.ATTENDANCE_REVIEW,
            [
                "attendance",
                "kehadiran",
                "absen",
                "presensi",
                "telat",
                "terlambat",
                "check in",
                "check-in",
                "wfh",
                "jam masuk",
                "masuk kantor",
                "jam masuk kantor",
                "rata rata masuk",
                "rata-rata masuk",
            ],
        ),
        (
            ConversationIntent.ATTENDANCE_CORRECTION,
            [
                "lupa absen",
                "lupa check-in",
                "lupa check in",
                "salah absen",
                "koreksi absen",
                "update absen",
                "lupa lapor",
                "salah status",
                "harusnya wfh",
                "harusnya wfo",
                "correction",
            ],
        ),
        (
            ConversationIntent.TIME_OFF_BALANCE,
            ["sisa cuti", "jatah cuti", "saldo cuti", "leave balance"],
        ),
        (
            ConversationIntent.TIME_OFF_REQUEST_STATUS,
            [
                "status cuti",
                "pengajuan cuti",
                "leave request",
                "cuti saya",
                "izin sakit",
                "cuti sakit",
                "sick leave",
                "lapor sakit",
                "approve cuti",
                "approval cuti",
                "persetujuan cuti",
            ],
        ),
        (
            ConversationIntent.TIME_OFF_SIMULATION,
            [
                "kalau saya cuti",
                "simulasi cuti",
                "hitung cuti",
                "potong cuti",
                "ambil cuti 3 hari",
                "ambil cuti 2 hari",
                "rencana cuti",
                "sisa berapa kalau",
            ],
        ),
        (
            ConversationIntent.PERSONAL_PROFILE,
            [
                "profil saya",
                "profil aku",
                "data saya",
                "data aku",
                "posisi saya",
                "posisi aku",
                "jabatan saya",
                "jabatan aku",
                "role saya",
                "role aku",
                "join date",
                "tanggal join",
                "atasan saya",
                "atasan aku",
                "manager saya",
                "manager aku",
                "manajer saya",
                "manajer aku",
                "mentor saya",
                "mentor aku",
                "guide saya",
                "guide aku",
            ],
        ),
        (
            ConversationIntent.COMPANY_POLICY,
            [
                "kebijakan",
                "aturan",
                "policy",
                "peraturan",
                "kode etik",
                "jam kerja",
                "carry over",
                "reimburse",
                "reimbursement",
                "klaim",
                "claim",
                "benefit",
                "benefits",
                "ditanggung",
                "eligible",
                "berhak",
                "syarat",
                "tunjangan",
                "allowance",
                "probation",
                "sesuai policy",
            ],
        ),
        (
            ConversationIntent.COMPANY_STRUCTURE,
            [
                "struktur",
                "organisasi",
                "departemen",
                "department",
                "tim hr",
                "kepala departemen",
                "head of",
                "human resources",
                "personalia",
                "kontak hr",
                "pic hr",
                "onboarding",
                "karyawan baru",
                "pegawai baru",
                "siapa pic",
                "recruiter",
                "rekrutmen",
                "referral",
                "hiring",
                "talent acquisition",
                "hrbp",
                "it support",
            ],
        ),
        (
            ConversationIntent.EMPLOYEE_WELLBEING_CONCERN,
            ["pelecehan", "diskriminasi", "dibully", "burnout", "depresi", "stress berat", "suicid", "bunuh diri"],
        ),
    ]
)

DEFAULT_SENSITIVITY_KEYWORDS = {
    SensitivityLevel.HIGH: [
        "bunuh diri",
        "suicide",
        "self harm",
        "pelecehan seksual",
        "sexual harassment",
        "kekerasan",
    ],
    SensitivityLevel.MEDIUM: [
        "pelecehan",
        "diskriminasi",
        "dibully",
        "burnout",
        "depresi",
        "stress berat",
        "toxic",
        "intimidasi",
    ],
}
SENSITIVITY_RANK = {
    SensitivityLevel.LOW: 0,
    SensitivityLevel.MEDIUM: 1,
    SensitivityLevel.HIGH: 2,
}

HR_DATA_INTENTS = {
    ConversationIntent.PAYROLL_INFO,
    ConversationIntent.PAYROLL_DOCUMENT_REQUEST,
    ConversationIntent.ATTENDANCE_REVIEW,
    ConversationIntent.ATTENDANCE_CORRECTION,
    ConversationIntent.TIME_OFF_BALANCE,
    ConversationIntent.TIME_OFF_REQUEST_STATUS,
    ConversationIntent.TIME_OFF_SIMULATION,
    ConversationIntent.PERSONAL_PROFILE,
}
COMPANY_INTENTS = {
    ConversationIntent.COMPANY_POLICY,
    ConversationIntent.COMPANY_STRUCTURE,
}

LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD = 0.78
SEMANTIC_PROVIDER_HINT_THRESHOLD = {
    "vector": 0.52,
    "lexical": 0.34,
}
SEMANTIC_DIRECT_FALLBACK_THRESHOLD = {
    "vector": 0.72,
    "lexical": 0.55,
}
AGENT_CAPABILITY_ROUTE_THRESHOLD = {
    "vector": 0.58,
    "lexical": 0.42,
}
KNOWN_AGENT_KEYS = {"hr-data-agent", "company-agent", "file-agent"}
GUIDANCE_REQUEST_MARKERS = [
    "tanya siapa",
    "hubungi siapa",
    "kontak siapa",
    "ke siapa",
    "ke mana",
    "harus ke siapa",
    "harus izin ke mana",
    "izin ke mana",
    "harus tanya ke siapa",
    "siapa yang bisa bantu",
    "siapa yang harus saya hubungi",
    "siapa pic",
    "pic siapa",
    "siapa recruiter",
    "siapa hrbp",
    "ke tim mana",
    "jalur mana",
    "approve siapa",
    "di-approve siapa",
    "approval siapa",
    "persetujuan siapa",
    "siapa yang approve",
    "minta arahan",
    "next step",
    "langkah berikutnya",
]
PERSONAL_PROFILE_SELF_MARKERS = [
    "saya",
    "aku",
    "gue",
    "gua",
    "my",
    "me",
]
PERSONAL_PROFILE_FIELD_MARKERS = [
    "profil",
    "profile",
    "data saya",
    "data aku",
    "posisi",
    "jabatan",
    "role",
    "atasan",
    "manager",
    "manajer",
    "supervisor",
    "lead",
]
PERSONAL_PROFILE_GUIDANCE_MARKERS = [
    "guide",
    "mentor",
    "onboarding",
    "dibimbing",
    "membimbing",
    "diguide",
    "di guide",
]
POLICY_REASONING_MARKERS = [
    "bisa reimburse",
    "eligible",
    "reimburse",
    "klaim",
    "claim",
    "limit",
    "maksimal",
    "max",
    "syarat",
    "dokumen",
    "apakah bisa",
    "bisa ambil",
    "boleh nggak",
    "boleh gak",
    "berhak",
    "jatah",
    "apakah dapat",
    "sesuai policy",
    "masih sesuai",
]
DECISION_SUPPORT_MARKERS = [
    "resign",
    "mengundurkan diri",
    "pengunduran diri",
    "burnout",
    "capek",
    "bingung",
    "konflik",
    "atasan saya",
    "manager saya",
    "internal move",
    "mutasi",
]
SENSITIVE_REPORT_MARKERS = [
    "lapor",
    "melaporkan",
    "report",
    "pelecehan",
    "diskriminasi",
    "unsafe",
    "kekerasan",
    "dibully",
]
COMPANY_GUIDANCE_SCOPE_MARKERS = [
    "departemen",
    "department",
    "tim hr",
    "human resources",
    "personalia",
    "administrasi",
    "onboarding",
    "karyawan baru",
    "pegawai baru",
    "kontak hr",
    "pic hr",
    "payroll",
    "gaji",
    "benefit",
    "benefits",
    "reimbursement",
    "reimburse",
    "klaim",
    "claim",
    "referral",
    "refer",
    "recruiter",
    "recruitment",
    "rekrutmen",
    "hiring",
    "talent acquisition",
    "ta",
    "hrbp",
    "people partner",
    "people ops",
    "career",
    "karier",
    "internal move",
    "mutasi",
    "it support",
    "issue teknis",
    "teknis internal",
    "akses sistem",
    "akun kerja",
    "password",
    "device",
    "laptop",
]


def _normalize_message(message: str) -> str:
    return " ".join(message.lower().strip().split())


def _contains_any_phrase(message: str, phrases: list[str]) -> bool:
    return any(phrase in message for phrase in phrases)


def _looks_like_guidance_request(message: str) -> bool:
    return _contains_any_phrase(_normalize_message(message), GUIDANCE_REQUEST_MARKERS)


def _looks_like_policy_reasoning_request(message: str) -> bool:
    if _contains_any_phrase(message, POLICY_REASONING_MARKERS):
        return True
    return bool(re.search(r"\b\d{2,}\s?(k|rb|ribu|jt|juta|m|million)\b", message))


def _looks_like_payroll_issue_request(message: str) -> bool:
    lowered = _normalize_message(message)
    issue_markers = [
        "potongan",
        "bpjs",
        "pph21",
        "pph 21",
        "deduction",
        "deductions",
        "rincian",
        "detail gaji",
        "detail payroll",
        "komponen gaji",
        "kapan gaji",
        "kapan cair",
        "gajian kapan",
        "tanggal gajian",
        "tanggal pembayaran",
        "status pembayaran",
        "payment date",
        "payment status",
        "belum cair",
        "belum keluar",
        "belum terbit",
        "belum muncul",
        "slip saya belum",
        "payslip belum",
    ]
    if any(marker in lowered for marker in issue_markers):
        return True

    asks_why = any(marker in lowered for marker in ["kenapa", "mengapa", "why"])
    mentions_payroll = any(
        token in lowered
        for token in [
            "gaji",
            "salary",
            "payroll",
            "slip",
            "payslip",
            "bpjs",
            "pph21",
            "pph 21",
        ]
    )
    return asks_why and mentions_payroll


def _looks_like_time_off_simulation_request(message: str) -> bool:
    lowered = _normalize_message(message)
    has_leave_subject = any(token in lowered for token in ["cuti", "leave"])
    has_day_count = bool(re.search(r"\b\d+\s*(hari|day)\b", lowered))
    has_projection_signal = any(
        token in lowered
        for token in [
            "sisa",
            "tinggal",
            "tersisa",
            "remaining",
            "berapa kalau",
        ]
    )
    return has_leave_subject and has_day_count and has_projection_signal


def _looks_like_time_off_operational_request(message: str) -> bool:
    lowered = _normalize_message(message)
    if any(token in lowered for token in ["izin sakit", "cuti sakit", "sick leave"]):
        return True

    mentions_leave = any(token in lowered for token in ["cuti", "leave"])
    mentions_sick_leave = "sakit" in lowered and "izin" in lowered
    has_operational_signal = any(
        token in lowered
        for token in [
            "ajukan",
            "pengajuan",
            "request",
            "approve",
            "approval",
            "persetujuan",
            "izin",
            "lapor",
            "status",
            "ke siapa",
            "ke mana",
        ]
    )
    return (mentions_leave or mentions_sick_leave) and has_operational_signal


def _looks_like_time_off_policy_mechanism_request(message: str) -> bool:
    lowered = _normalize_message(message)
    mentions_balance = any(
        token in lowered
        for token in ["saldo cuti", "jatah cuti", "leave balance", "sisa cuti"]
    )
    asks_refresh = any(token in lowered for token in ["kapan", "when"]) and any(
        token in lowered
        for token in ["nambah", "bertambah", "increase", "refresh", "reset"]
    )
    return mentions_balance and asks_refresh


def _should_promote_hr_route_to_mixed_for_guidance(
    message: str,
    intent: IntentAssessment,
) -> bool:
    if intent.primary_intent in {
        ConversationIntent.PAYROLL_INFO,
        ConversationIntent.PAYROLL_DOCUMENT_REQUEST,
    }:
        return _looks_like_guidance_request(message)

    if intent.primary_intent in {
        ConversationIntent.TIME_OFF_BALANCE,
        ConversationIntent.TIME_OFF_REQUEST_STATUS,
        ConversationIntent.TIME_OFF_SIMULATION,
    }:
        return _looks_like_guidance_request(message) or _looks_like_time_off_policy_mechanism_request(
            message
        )

    return False


def _looks_like_workflow_request(
    message: str,
    intent: ConversationIntent,
) -> bool:
    gate = assess_action_execution_intent(
        message,
        intent_key=intent.value,
    )
    return bool(gate.get("should_trigger"))


def _looks_like_decision_support(message: str) -> bool:
    return _contains_any_phrase(message, DECISION_SUPPORT_MARKERS)


def _looks_like_sensitive_report(message: str) -> bool:
    return _contains_any_phrase(message, SENSITIVE_REPORT_MARKERS)


def _has_personal_profile_self_signal(message: str) -> bool:
    lowered = _normalize_message(message)
    return any(
        re.search(rf"\b{re.escape(marker)}\b", lowered)
        for marker in PERSONAL_PROFILE_SELF_MARKERS
    )


def _looks_like_personal_profile_request(message: str) -> bool:
    lowered = _normalize_message(message)
    if _looks_like_time_off_operational_request(lowered) and any(
        token in lowered for token in ["cuti", "leave", "izin"]
    ):
        return False

    has_self_signal = _has_personal_profile_self_signal(lowered)
    asks_identity = any(
        token in lowered
        for token in [
            "siapa",
            "apa",
            "posisi apa",
            "posisi apakah",
            "jabatan apa",
            "role apa",
            "tolong cek",
            "cek",
        ]
    ) or "?" in message
    asks_profile_field = any(
        token in lowered
        for token in [
            *PERSONAL_PROFILE_FIELD_MARKERS,
            *PERSONAL_PROFILE_GUIDANCE_MARKERS,
        ]
    )
    if has_self_signal and asks_profile_field:
        return True
    if asks_identity and any(
        token in lowered
        for token in [
            "siapa atasan",
            "atasan siapa",
            "siapa manager",
            "manager siapa",
            "siapa manajer",
            "manajer siapa",
            "posisi apa",
            "posisi apakah",
            "jabatan apa",
            "role apa",
        ]
    ):
        return True
    return False


def _pack_agent_message(
    base_message: str,
    *,
    attachment_text: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    max_history_items: int = 4,
    max_attachment_chars: int = 1200,
) -> str:
    """Build a structured, labelled context block for downstream agents (I.7).

    Rather than concatenating attachment text and history as raw strings,
    this helper wraps each piece in a clearly labelled section so agents
    can parse context boundaries reliably without grepping for sentinel text.

    Layout produced:
        [USER REQUEST]
        <base_message>

        [CONVERSATION HISTORY]
        user: ...
        assistant: ...

        [ATTACHMENT CONTENT]
        <extracted text>
    """
    parts: list[str] = [f"[USER REQUEST]\n{base_message.strip()}"]

    if conversation_history:
        history_items = conversation_history[-max_history_items:]
        history_lines: list[str] = []
        for item in history_items:
            role = str(item.get("role", "unknown")).strip().lower()
            content = str(item.get("content", "")).strip()
            if content:
                history_lines.append(f"{role}: {content[:400]}")
        if history_lines:
            parts.append("[CONVERSATION HISTORY]\n" + "\n".join(history_lines))

    if attachment_text:
        truncated = attachment_text[:max_attachment_chars]
        if len(attachment_text) > max_attachment_chars:
            truncated += " [truncated]"
        parts.append(f"[ATTACHMENT CONTENT]\n{truncated}")

    return "\n\n".join(parts)


def _build_classification_message(
    message: str,
    attachment_names: list[str] | None = None,
    attachment_preview: str | None = None,
) -> str:
    parts = [message.strip()]

    if attachment_names:
        parts.append(f"Attachments: {', '.join(attachment_names)}")

    if attachment_preview:
        parts.append(f"Attachment preview: {attachment_preview[:800]}")

    return "\n".join(part for part in parts if part)


_TOPIC_DOMAIN_MAP: dict[str, str] = {
    # payroll / salary
    "gaji": "payroll", "salary": "payroll", "payroll": "payroll",
    "payslip": "payroll", "slip gaji": "payroll",
    # attendance
    "attendance": "attendance", "kehadiran": "attendance",
    "presensi": "attendance", "jam masuk": "attendance",
    "check in": "attendance", "check-in": "attendance",
    # time-off
    "cuti": "time_off", "leave": "time_off", "izin": "time_off",
    "saldo cuti": "time_off", "jatah cuti": "time_off",
    # sensitive / reporting
    "lapor": "sensitive", "melaporkan": "sensitive", "report": "sensitive",
    "pelecehan": "sensitive", "diskriminasi": "sensitive",
    "kekerasan": "sensitive", "dibully": "sensitive", "bully": "sensitive",
    "harassment": "sensitive", "sensitivity": "sensitive",
    "sensitive": "sensitive", "whistleblow": "sensitive",
    "pelanggaran": "sensitive", "keluhan": "sensitive",
    "complaint": "sensitive", "unsafe": "sensitive",
    # decision support
    "resign": "decision", "mengundurkan diri": "decision",
    "burnout": "decision", "konflik": "decision", "mutasi": "decision",
    # policy / company
    "aturan": "policy", "policy": "policy", "kebijakan": "policy",
    "reimburse": "policy", "reimbursement": "policy",
    "klaim": "policy", "claim": "policy",
    # profile
    "profil": "profile", "profile": "profile",
    "posisi": "profile", "jabatan": "profile", "role": "profile",
}


def _detect_topic_domain_from_message(lowered_message: str) -> str | None:
    """Return the dominant topic domain for a single message, or None."""
    for phrase, domain in _TOPIC_DOMAIN_MAP.items():
        if phrase in lowered_message:
            return domain
    return None


def _detect_topic_domain(
    conversation_history: list[dict[str, str]],
) -> str | None:
    """Return the dominant topic domain of the most recent user message in history."""
    for item in reversed(conversation_history):
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip().lower()
        if role == "user" and content:
            return _detect_topic_domain_from_message(content)
    return None


def _should_use_conversation_grounding(
    message: str,
    conversation_history: list[dict[str, str]] | None,
) -> bool:
    if not conversation_history:
        return False

    lowered = _normalize_message(message)
    referential_markers = [
        "yang tadi",
        "tadi",
        "itu",
        "tersebut",
        "yang barusan",
        "barusan",
        "sebelumnya",
        "yang itu",
    ]
    informative_tokens = re.findall(r"[a-zA-Z0-9_]{3,}", lowered)
    is_short_follow_up = len(informative_tokens) <= 6
    has_referential_marker = any(marker in lowered for marker in referential_markers)
    if has_referential_marker:
        return True
    if not is_short_follow_up:
        return False

    standalone_signals = [
        "cuti",
        "leave",
        "payroll",
        "payslip",
        "slip gaji",
        "gaji",
        "salary",
        "attendance",
        "kehadiran",
        "presensi",
        "jam masuk",
        "check in",
        "check-in",
        "aturan",
        "policy",
        "kebijakan",
        "struktur",
        "department",
        "departemen",
        "posisi",
        "jabatan",
        "role",
        "atasan",
        "manager",
        "manajer",
        "supervisor",
        "lead",
        "mentor",
        "guide",
        "onboarding",
        "profil",
        "profile",
        "saldo",
        "status",
        # Sensitive / reporting signals – prevent topic bleeding from
        # prior conversations when the user starts a report or raises
        # a wellbeing / sensitivity concern.
        "lapor",
        "melaporkan",
        "report",
        "pelecehan",
        "diskriminasi",
        "unsafe",
        "kekerasan",
        "dibully",
        "bully",
        "harassment",
        "sensitivity",
        "sensitive",
        "whistleblow",
        "pelanggaran",
        "keluhan",
        "complaint",
        # Decision-support signals
        "resign",
        "mengundurkan diri",
        "burnout",
        "konflik",
        "mutasi",
        # Reimbursement / claim signals
        "reimburse",
        "reimbursement",
        "klaim",
        "claim",
    ]
    has_standalone_signal = bool(
        re.search(r"\b(20\d{2}|jan|feb|mar|apr|mei|may|jun|jul|agu|aug|sep|okt|oct|nov|des|dec)\b", lowered)
    ) or any(signal in lowered for signal in standalone_signals)
    if has_standalone_signal:
        return False

    # Topic-divergence guard: even for short messages without explicit
    # standalone signals, check whether the previous conversation was
    # about a clearly *different* domain.  If so, do NOT ground – the
    # user likely started a new topic.
    if conversation_history and not has_referential_marker:
        prev_domain = _detect_topic_domain(conversation_history)
        curr_domain = _detect_topic_domain_from_message(lowered)
        if prev_domain and curr_domain and prev_domain != curr_domain:
            return False

    return True


def _build_grounded_message_from_history(
    message: str,
    conversation_history: list[dict[str, str]],
) -> tuple[str, dict[str, Any]]:
    recent_history = conversation_history[-4:]
    history_lines: list[str] = []
    for item in recent_history:
        role = str(item.get("role", "unknown")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        history_lines.append(f"{role}: {content[:400]}")

    if not history_lines:
        return message, {
            "used": False,
            "reason": "Conversation history was present but empty after normalization.",
            "history_items": 0,
        }

    grounded_message = (
        "Recent conversation context:\n"
        + "\n".join(history_lines)
        + f"\n\nCurrent user follow-up:\n{message.strip()}"
    )
    return grounded_message, {
        "used": True,
        "reason": "Recent conversation history was added because the current message looked referential or too short on its own.",
        "history_items": len(history_lines),
    }


def _build_weighted_keywords(
    default_keywords: list[str],
    override_items: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    weighted_keywords = {keyword.lower(): 1 for keyword in default_keywords}

    for item in override_items or []:
        keyword = str(item.get("keyword", "")).strip().lower()
        if not keyword:
            continue

        try:
            weight = max(int(item.get("weight", 1)), 1)
        except (TypeError, ValueError):
            weight = 1

        weighted_keywords[keyword] = max(weighted_keywords.get(keyword, 0), weight)

    return weighted_keywords


def _apply_local_intent_bonus(
    intent: ConversationIntent,
    lowered_message: str,
) -> tuple[int, list[str]]:
    bonus_score = 0
    bonus_matches: list[str] = []

    if intent == ConversationIntent.TIME_OFF_BALANCE:
        if "cuti" in lowered_message and any(
            token in lowered_message for token in ["sisa", "saldo", "jatah"]
        ):
            bonus_score += 3
            bonus_matches.append("time_off_balance_signal")
        if _looks_like_time_off_policy_mechanism_request(lowered_message):
            bonus_score += 2
            bonus_matches.append("time_off_balance_refresh_signal")

    if intent == ConversationIntent.TIME_OFF_REQUEST_STATUS:
        if _looks_like_time_off_operational_request(lowered_message):
            bonus_score += 4
            bonus_matches.append("time_off_request_signal")

    if intent == ConversationIntent.TIME_OFF_SIMULATION:
        if _looks_like_time_off_simulation_request(lowered_message):
            bonus_score += 4
            bonus_matches.append("time_off_simulation_signal")

    if intent == ConversationIntent.PAYROLL_DOCUMENT_REQUEST:
        if (
            any(token in lowered_message for token in ["slip", "payslip", "pay slip"])
            and not _looks_like_payroll_issue_request(lowered_message)
        ):
            bonus_score += 3
            bonus_matches.append("payroll_document_signal")

    if intent == ConversationIntent.PAYROLL_INFO:
        if any(token in lowered_message for token in ["gaji", "salary", "payroll"]):
            bonus_score += 2
            bonus_matches.append("payroll_info_signal")
        if _looks_like_payroll_issue_request(lowered_message):
            bonus_score += 3
            bonus_matches.append("payroll_issue_signal")

    if intent == ConversationIntent.ATTENDANCE_REVIEW:
        if any(
            token in lowered_message
            for token in [
                "jam masuk",
                "masuk kantor",
                "check in",
                "check-in",
                "kehadiran",
                "attendance",
            ]
        ):
            bonus_score += 3
            bonus_matches.append("attendance_review_signal")

    if intent == ConversationIntent.PERSONAL_PROFILE:
        if _looks_like_personal_profile_request(lowered_message):
            bonus_score += 4
            bonus_matches.append("personal_profile_signal")
        if any(
            token in lowered_message
            for token in [
                "posisi",
                "jabatan",
                "role",
                "atasan",
                "manager",
                "manajer",
                "supervisor",
                "lead",
            ]
        ):
            bonus_score += 2
            bonus_matches.append("personal_profile_field_signal")
        if (
            _has_personal_profile_self_signal(lowered_message)
            and any(
                token in lowered_message
                for token in PERSONAL_PROFILE_GUIDANCE_MARKERS
            )
        ):
            bonus_score += 3
            bonus_matches.append("personal_profile_guidance_signal")

    if intent == ConversationIntent.COMPANY_POLICY:
        if any(token in lowered_message for token in ["aturan", "kebijakan", "policy"]):
            bonus_score += 2
            bonus_matches.append("company_policy_signal")
        if _looks_like_policy_reasoning_request(lowered_message):
            bonus_score += 3
            bonus_matches.append("company_policy_reasoning_signal")

    if intent == ConversationIntent.COMPANY_STRUCTURE:
        mentions_contact_route = any(
            token in lowered_message
            for token in [
                "tanya siapa",
                "hubungi siapa",
                "kontak siapa",
                "ke siapa",
                "harus ke siapa",
                "siapa yang bisa bantu",
                "siapa pic",
                "pic siapa",
                "siapa recruiter",
                "siapa hrbp",
                "ke tim mana",
                "jalur mana",
            ]
        )
        mentions_structure_scope = any(
            token in lowered_message for token in COMPANY_GUIDANCE_SCOPE_MARKERS
        ) or bool(re.search(r"\bhr\b", lowered_message))
        if mentions_contact_route and mentions_structure_scope:
            bonus_score += 4
            bonus_matches.append("company_structure_contact_signal")

        if any(
            token in lowered_message
            for token in [
                "struktur",
                "organisasi",
                "departemen",
                "department",
                "tim hr",
                "kepala departemen",
                "head of",
            ]
        ):
            bonus_score += 2
            bonus_matches.append("company_structure_signal")

    return bonus_score, bonus_matches


async def _load_classifier_overrides(
    db: AsyncSession,
    company_id: str,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    cache = get_cache("classifier_config")
    cache_key = f"classifier:{company_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    try:
        result = await db.execute(
            text(
                """
                SELECT
                    classifier_type,
                    target_key,
                    keyword,
                    weight
                FROM classifier_keyword_overrides
                WHERE company_id = CAST(:company_id AS uuid)
                  AND is_active = true
                ORDER BY classifier_type ASC, target_key ASC, weight DESC, keyword ASC
                """
            ),
            {"company_id": company_id},
        )
    except Exception:
        empty_overrides = {"intent": {}, "sensitivity": {}}
        cache.set(cache_key, empty_overrides, ttl_seconds=60)
        return empty_overrides

    overrides: dict[str, dict[str, list[dict[str, Any]]]] = {
        "intent": {},
        "sensitivity": {},
    }
    for row in result.mappings().all():
        data = dict(row)
        classifier_type = str(data.get("classifier_type", "")).strip().lower()
        target_key = str(data.get("target_key", "")).strip()
        if classifier_type not in {"intent", "sensitivity"} or not target_key:
            continue

        overrides[classifier_type].setdefault(target_key, []).append(
            {
                "keyword": data.get("keyword"),
                "weight": data.get("weight", 1),
            }
        )

    cache.set(cache_key, overrides)
    return overrides


def _count_classifier_overrides(
    overrides: dict[str, dict[str, list[dict[str, Any]]]],
) -> int:
    return sum(
        len(items)
        for classifier_map in overrides.values()
        for items in classifier_map.values()
    )


def classify_intent(
    message: str,
    classifier_overrides: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> IntentAssessment:
    lowered = _normalize_message(message)
    scored: list[tuple[int, ConversationIntent, list[str]]] = []
    intent_override_map = (
        classifier_overrides.get("intent", {}) if classifier_overrides else {}
    )

    for intent, keywords in INTENT_KEYWORDS.items():
        keyword_weights = _build_weighted_keywords(
            keywords,
            intent_override_map.get(intent.value, []),
        )
        matched: list[str] = []
        score = 0

        for keyword, weight in keyword_weights.items():
            if keyword in lowered:
                matched.append(keyword)
                score += weight

        bonus_score, bonus_matches = _apply_local_intent_bonus(intent, lowered)
        score += bonus_score
        matched.extend(bonus_matches)

        if score > 0:
            scored.append((score, intent, matched))

    scored.sort(key=lambda item: item[0], reverse=True)

    if not scored:
        generic_hr_keywords = ["hr", "payroll", "cuti", "attendance", "policy", "kebijakan"]
        if any(keyword in lowered for keyword in generic_hr_keywords):
            return IntentAssessment(
                primary_intent=ConversationIntent.GENERAL_HR_SUPPORT,
                secondary_intents=[],
                confidence=0.35,
                matched_keywords=[keyword for keyword in generic_hr_keywords if keyword in lowered],
            )
        return IntentAssessment(
            primary_intent=ConversationIntent.OUT_OF_SCOPE,
            secondary_intents=[],
            confidence=0.2,
            matched_keywords=[],
        )

    primary_score, primary_intent, matched_keywords = scored[0]
    secondary_intents = [
        intent
        for score, intent, _ in scored[1:3]
        if (
            score > 0
            and intent != primary_intent
            and score >= max(2, primary_score - 1)
        )
    ]
    confidence = min(0.45 + (primary_score * 0.1), 0.97)
    has_signal_match = any(keyword.endswith("_signal") for keyword in matched_keywords)
    if len(set(matched_keywords)) >= 2:
        confidence = min(confidence + 0.08, 0.97)
    if not secondary_intents and primary_score >= 4:
        confidence = max(confidence, 0.82)
    if not secondary_intents and has_signal_match:
        confidence = max(confidence, 0.82)

    return IntentAssessment(
        primary_intent=primary_intent,
        secondary_intents=secondary_intents,
        confidence=confidence,
        matched_keywords=sorted(set(matched_keywords)),
    )


def assess_sensitivity(
    message: str,
    classifier_overrides: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> SensitivityAssessment:
    lowered = _normalize_message(message)
    sensitivity_override_map = (
        classifier_overrides.get("sensitivity", {}) if classifier_overrides else {}
    )

    high_keywords = _build_weighted_keywords(
        DEFAULT_SENSITIVITY_KEYWORDS[SensitivityLevel.HIGH],
        sensitivity_override_map.get(SensitivityLevel.HIGH.value, []),
    )
    medium_keywords = _build_weighted_keywords(
        DEFAULT_SENSITIVITY_KEYWORDS[SensitivityLevel.MEDIUM],
        sensitivity_override_map.get(SensitivityLevel.MEDIUM.value, []),
    )

    high_matches = [keyword for keyword in high_keywords if keyword in lowered]
    if high_matches:
        return SensitivityAssessment(
            level=SensitivityLevel.HIGH,
            matched_keywords=sorted(set(high_matches)),
            rationale=(
                "Pesan mengandung sinyal risiko tinggi yang perlu diarahkan ke "
                "penanganan HR/manual review."
            ),
        )

    medium_matches = [keyword for keyword in medium_keywords if keyword in lowered]
    if medium_matches:
        return SensitivityAssessment(
            level=SensitivityLevel.MEDIUM,
            matched_keywords=sorted(set(medium_matches)),
            rationale=(
                "Pesan mengandung topik sensitif yang sebaiknya tidak ditangani "
                "sepenuhnya oleh jalur otomatis."
            ),
        )

    return SensitivityAssessment(
        level=SensitivityLevel.LOW,
        matched_keywords=[],
        rationale="Pesan tidak menunjukkan indikator sensitif yang kuat.",
    )


def _merge_sensitive_case_sensitivity(
    sensitivity: SensitivityAssessment,
    sensitive_case: SensitiveCaseAssessment | None,
) -> SensitivityAssessment:
    if sensitive_case is None:
        return sensitivity

    matched_keywords = sorted(
        set(sensitivity.matched_keywords + list(sensitive_case.matched_markers))
    )
    if sensitive_case.case_key not in matched_keywords:
        matched_keywords.append(sensitive_case.case_key)

    if (
        SENSITIVITY_RANK[sensitive_case.minimum_sensitivity]
        <= SENSITIVITY_RANK[sensitivity.level]
    ):
        return sensitivity.model_copy(
            update={
                "matched_keywords": matched_keywords,
                "rationale": (
                    f"{sensitivity.rationale} Kategori {sensitive_case.case_key} "
                    "tetap diperlakukan hati-hati."
                ),
            }
        )

    return SensitivityAssessment(
        level=sensitive_case.minimum_sensitivity,
        matched_keywords=matched_keywords,
        rationale=(
            f"Pesan cocok dengan kategori sensitif {sensitive_case.case_key} "
            "yang perlu diarahkan ke penanganan manusia."
        ),
    )


def _resolve_route(intent: IntentAssessment) -> AgentRoute:
    intents = {intent.primary_intent, *intent.secondary_intents}
    needs_hr_data = any(item in HR_DATA_INTENTS for item in intents)
    needs_company = any(item in COMPANY_INTENTS for item in intents)

    if intent.primary_intent == ConversationIntent.OUT_OF_SCOPE:
        return AgentRoute.OUT_OF_SCOPE
    if intent.primary_intent == ConversationIntent.GENERAL_HR_SUPPORT:
        return AgentRoute.OUT_OF_SCOPE
    if needs_hr_data and needs_company:
        return AgentRoute.MIXED
    if needs_hr_data:
        return AgentRoute.HR_DATA
    if needs_company:
        return AgentRoute.COMPANY
    return AgentRoute.OUT_OF_SCOPE


def _build_query_policy(
    message: str,
    intent: IntentAssessment,
) -> dict[str, Any]:
    lowered = _normalize_message(message)
    has_temporal_signal = bool(
        re.search(r"\b(20\d{2}|jan|feb|mar|apr|mei|may|jun|jul|agu|aug|sep|okt|oct|nov|des|dec)\b", lowered)
    ) or any(
        phrase in lowered
        for phrase in [
            "bulan ini",
            "this month",
            "bulan lalu",
            "last month",
            "bulan kemarin",
            "tahun ini",
            "this year",
            "tahun lalu",
            "last year",
            "periode terkini",
            "period terbaru",
            "periode terbaru",
            "latest period",
            "last complete month",
            "awal bulan ini",
            "akhir bulan ini",
            "yang relevan terakhir",
        ]
    )
    has_comparison_signal = any(
        token in lowered
        for token in [
            "dibanding",
            "compare",
            "comparison",
            "versus",
            "vs",
            "lebih rendah",
            "lebih tinggi",
            "lower",
            "higher",
            "naik",
            "turun",
        ]
    )
    has_trend_signal = any(
        token in lowered
        for token in [
            "trend",
            "tren",
            "rata rata",
            "rata-rata",
            "average",
            "avg",
            "rolling",
            "30 hari terakhir",
            "sebulan terakhir",
        ]
    )
    informative_tokens = re.findall(r"[a-zA-Z0-9_]{3,}", lowered)
    is_ambiguous = (
        intent.primary_intent in {
            ConversationIntent.GENERAL_HR_SUPPORT,
            ConversationIntent.OUT_OF_SCOPE,
        }
        or len(informative_tokens) <= 3
    )

    if intent.primary_intent in HR_DATA_INTENTS:
        if has_comparison_signal or has_trend_signal:
            query_class = "comparison_lookup"
        elif has_temporal_signal:
            query_class = "temporal_lookup"
        else:
            query_class = "factual_exact_lookup"
        boundary_mode = "must_be_deterministic"
    elif intent.primary_intent == ConversationIntent.COMPANY_STRUCTURE:
        query_class = "factual_exact_lookup"
        boundary_mode = "deterministic_preferred"
    elif intent.primary_intent == ConversationIntent.COMPANY_POLICY:
        query_class = "semantic_lookup"
        boundary_mode = "semantic_assisted"
    elif is_ambiguous:
        query_class = "ambiguous_lookup"
        boundary_mode = "needs_clarification_or_provider"
    else:
        query_class = "semantic_lookup"
        boundary_mode = "semantic_assisted"

    return {
        "query_class": query_class,
        "boundary_mode": boundary_mode,
        "has_temporal_signal": has_temporal_signal,
        "has_comparison_signal": has_comparison_signal,
        "has_trend_signal": has_trend_signal,
        "requires_structured_scope": boundary_mode in {
            "must_be_deterministic",
            "deterministic_preferred",
        },
        "is_ambiguous": is_ambiguous,
    }


def _build_query_policy_trace_detail(query_policy: dict[str, Any]) -> str:
    return (
        f"query_class={query_policy['query_class']}, "
        f"boundary_mode={query_policy['boundary_mode']}, "
        f"temporal={query_policy['has_temporal_signal']}, "
        f"comparison={query_policy['has_comparison_signal']}, "
        f"trend={query_policy['has_trend_signal']}, "
        f"ambiguous={query_policy['is_ambiguous']}"
    )


def _derive_request_category(
    *,
    message: str,
    intent: IntentAssessment,
    sensitivity: SensitivityAssessment,
    route: AgentRoute,
    company_records: dict[str, Any] | None = None,
) -> ConversationRequestCategory:
    lowered = _normalize_message(message)
    company_records = company_records or {}

    if sensitivity.level != SensitivityLevel.LOW:
        if _looks_like_decision_support(lowered):
            return ConversationRequestCategory.DECISION_SUPPORT
        if _looks_like_sensitive_report(lowered):
            return ConversationRequestCategory.SENSITIVE_REPORT
        return ConversationRequestCategory.SENSITIVE_REPORT

    if _looks_like_workflow_request(lowered, intent.primary_intent):
        return ConversationRequestCategory.WORKFLOW_REQUEST

    if (
        company_records.get("contact_guidance_requested")
        or (
            route in {AgentRoute.COMPANY, AgentRoute.MIXED}
            and _looks_like_guidance_request(lowered)
        )
    ):
        return ConversationRequestCategory.GUIDANCE_REQUEST

    if (
        intent.primary_intent == ConversationIntent.COMPANY_POLICY
        and _looks_like_policy_reasoning_request(lowered)
    ):
        return ConversationRequestCategory.POLICY_REASONING_REQUEST

    if intent.primary_intent == ConversationIntent.TIME_OFF_SIMULATION:
        return ConversationRequestCategory.SIMULATION_REQUEST

    return ConversationRequestCategory.INFORMATIONAL_QUESTION


def _resolve_response_mode(
    request_category: ConversationRequestCategory,
    *,
    sensitivity: SensitivityAssessment,
) -> ResponseMode:
    if sensitivity.level != SensitivityLevel.LOW:
        return ResponseMode.SENSITIVE_GUARDED
    if request_category == ConversationRequestCategory.GUIDANCE_REQUEST:
        return ResponseMode.GUIDANCE
    if request_category in {
        ConversationRequestCategory.POLICY_REASONING_REQUEST,
        ConversationRequestCategory.SIMULATION_REQUEST,
    }:
        return ResponseMode.POLICY_REASONING
    if request_category == ConversationRequestCategory.WORKFLOW_REQUEST:
        return ResponseMode.WORKFLOW_INTAKE
    return ResponseMode.INFORMATIONAL


def _build_recommended_next_steps(
    *,
    message: str = "",
    intent: IntentAssessment,
    route: AgentRoute,
    request_category: ConversationRequestCategory,
    response_mode: ResponseMode,
    company_records: dict[str, Any] | None = None,
    sensitive_case: SensitiveCaseAssessment | None = None,
) -> list[str]:
    company_records = company_records or {}
    lowered = _normalize_message(message)
    steps: list[str] = []

    if response_mode == ResponseMode.GUIDANCE:
        recommended_channel = str(company_records.get("recommended_channel") or "").strip()
        if recommended_channel:
            steps.append(f"Mulai lewat channel yang disarankan: {recommended_channel}.")

        preparation_checklist = company_records.get("preparation_checklist")
        if isinstance(preparation_checklist, list):
            for item in preparation_checklist[:2]:
                item_text = str(item).strip()
                if item_text:
                    steps.append(item_text)

        if not steps:
            steps.extend(
                [
                    "Hubungi PIC atau fungsi yang paling relevan untuk topik ini.",
                    "Siapkan ringkasan masalah dan konteks singkat sebelum menghubungi mereka.",
                ]
            )
    elif response_mode == ResponseMode.POLICY_REASONING:
        policy_reasoning = (
            company_records.get("policy_reasoning")
            if isinstance(company_records, dict)
            else None
        )
        if isinstance(policy_reasoning, dict):
            eligibility = str(policy_reasoning.get("eligibility") or "").strip().lower()
            if eligibility != "not_eligible":
                required_documents = policy_reasoning.get("required_documents")
                if isinstance(required_documents, list) and required_documents:
                    steps.append(
                        "Siapkan dokumen pendukung ini: "
                        + ", ".join(str(item) for item in required_documents[:3])
                        + "."
                    )
            next_action = str(policy_reasoning.get("next_action") or "").strip()
            if next_action:
                steps.append(next_action)
            if not steps:
                if eligibility == "not_eligible":
                    steps.append(
                        "Jangan ajukan klaim dulu sebelum ada konfirmasi manual kalau kasusmu memang berbeda dari pengecualian policy."
                    )
                else:
                    steps.extend(
                        [
                            "Siapkan nominal, tanggal, dan dokumen pendukung bila ingin verifikasi policy lebih presisi.",
                            "Tambahkan detail benefit, level, atau kategori klaim jika kasusmu masih ambigu.",
                        ]
                    )
        else:
            steps.extend(
                [
                    "Siapkan nominal, tanggal, dan dokumen pendukung bila ingin verifikasi policy lebih presisi.",
                    "Tambahkan detail benefit, level, atau kategori klaim jika kasusmu masih ambigu.",
                ]
            )
    elif response_mode == ResponseMode.WORKFLOW_INTAKE:
        steps.extend(
            [
                "Sebutkan periode atau detail dokumen secara eksplisit jika kamu ingin sistem membuat action formal.",
                "Cek action percakapan ini setelah request dikonfirmasi untuk melihat follow-up yang dibuat.",
            ]
        )
    elif request_category == ConversationRequestCategory.SIMULATION_REQUEST:
        steps.extend(
            [
                "Sebutkan jumlah hari atau rentang tanggal spesifik untuk simulasi yang lebih akurat.",
                "Tanyakan tentang sisa saldo setelah simulasi jika kamu ingin merencanakan cuti panjang.",
            ]
        )
    elif intent.primary_intent == ConversationIntent.ATTENDANCE_CORRECTION:
        steps.extend(
            [
                "Sebutkan tanggal absensi yang ingin dikoreksi agar PIC bisa mengecek lebih cepat.",
                "Lampirkan bukti (misal: screenshot/foto) jika diminta oleh atasan atau tim HR.",
            ]
        )
    elif "reimburse" in lowered or "klaim" in lowered or "claim" in lowered:
        steps.extend(
            [
                "Sebutkan kategori reimbursement (misal: kacamata, transportasi, atau medical).",
                "Pastikan nominal dan tanggal pengeluaran sudah disebutkan untuk proses intake otomatis.",
                "Siapkan dokumen wajib seperti invoice, receipt, atau bukti bayar digital.",
            ]
        )
    elif intent.primary_intent == ConversationIntent.PERSONAL_PROFILE and any(v in lowered for v in ["update", "ubah", "ganti", "edit"]):
        steps.extend(
            [
                "Sebutkan data spesifik yang ingin diubah (misal: alamat, nomor HP, atau rekening bank).",
                "Pastikan kamu memiliki dokumen pendukung jika perubahan data memerlukan verifikasi HR.",
            ]
        )
    elif response_mode == ResponseMode.SENSITIVE_GUARDED:
        if sensitive_case is not None and sensitive_case.recommended_next_steps:
            steps.extend(list(sensitive_case.recommended_next_steps))
        elif request_category == ConversationRequestCategory.DECISION_SUPPORT:
            steps.extend(
                [
                    "Pertimbangkan diskusi dulu dengan atasan atau HR yang relevan sebelum mengambil langkah formal.",
                    "Kalau kamu nyaman, jelaskan konteks utamanya supaya arahan berikutnya bisa lebih tepat.",
                ]
            )
        else:
            steps.extend(
                [
                    "Gunakan jalur HR atau kanal pelaporan resmi agar kasus sensitif ini ditangani manusia yang berwenang.",
                    "Jangan mengandalkan jalur otomatis saja untuk kasus dengan dampak tinggi seperti ini.",
                ]
            )
    elif response_mode == ResponseMode.INFORMATIONAL:
        if intent.primary_intent in HR_DATA_INTENTS | {ConversationIntent.PAYROLL_DOCUMENT_REQUEST}:
            steps.append("Tambahkan periode spesifik bila kamu ingin jawaban yang lebih presisi.")
        elif route in {AgentRoute.COMPANY, AgentRoute.MIXED}:
            steps.append("Kalau kamu butuh arahan praktis, lanjutkan dengan topik spesifik atau tanya harus ke siapa.")

    deduped_steps: list[str] = []
    for step in steps:
        if step not in deduped_steps:
            deduped_steps.append(step)
    return deduped_steps[:3]


def _build_response_contract_trace_detail(
    request_category: ConversationRequestCategory,
    response_mode: ResponseMode,
    recommended_next_steps: list[str],
) -> str:
    return (
        f"request_category={request_category.value}, "
        f"response_mode={response_mode.value}, "
        f"recommended_next_steps={len(recommended_next_steps)}"
    )


def _build_sensitive_response(
    sensitivity: SensitivityAssessment,
    sensitive_case: SensitiveCaseAssessment | None = None,
) -> str:
    if sensitive_case is not None:
        return sensitive_case.response_template

    return (
        "Terima kasih sudah menyampaikan hal yang sensitif ini. Aku tidak akan "
        "menyimpulkan atau mengotomasi penanganannya. Jalur yang paling aman "
        "adalah meminta bantuan HR atau pihak perusahaan yang berwenang untuk "
        "menangani kasus ini secara manusiawi."
    )


def _build_sensitive_case_trace_detail(
    sensitive_case: SensitiveCaseAssessment,
) -> str:
    return (
        f"sensitive_case={sensitive_case.case_key}, "
        f"action_policy={sensitive_case.action_policy}, "
        f"review_policy={sensitive_case.review_policy}"
    )


def _build_out_of_scope_response(intent: IntentAssessment) -> str:
    if intent.primary_intent == ConversationIntent.GENERAL_HR_SUPPORT:
        return (
            "Aku bisa bantu kalau pertanyaannya dibuat lebih spesifik, misalnya "
            "tentang payroll, attendance, cuti, policy perusahaan, atau struktur perusahaan."
        )
    return (
        "Pesan ini belum cukup jelas atau belum masuk domain HR.ai. Coba arahkan "
        "ke payroll, attendance, time off, policy perusahaan, atau struktur perusahaan."
    )


def _synthesize_answer(
    route: AgentRoute,
    hr_summary: str | None,
    company_summary: str | None,
    file_summary: str | None,
) -> str:
    parts: list[str] = []

    if route == AgentRoute.HR_DATA and hr_summary:
        parts.append(hr_summary)
    elif route == AgentRoute.COMPANY and company_summary:
        parts.append(company_summary)
    elif route == AgentRoute.MIXED:
        if hr_summary:
            parts.append(f"Data personal: {hr_summary}")
        if company_summary:
            parts.append(f"Referensi perusahaan: {company_summary}")

    if file_summary:
        parts.append(f"Lampiran: {file_summary}")

    return " ".join(part for part in parts if part).strip()


def _build_hr_trace_detail(summary: str) -> str:
    return summary.strip()


def _build_company_trace_detail(company_result) -> str:
    matched_rules = company_result.records.get("matched_rules", [])
    if matched_rules:
        parts: list[str] = []
        for rule in matched_rules:
            title = rule.get("title") or "Untitled rule"
            category = rule.get("category") or "-"
            effective_date = rule.get("effective_date") or "-"
            content = (
                rule.get("content")
                or rule.get("matched_chunk")
                or company_result.summary
            )
            parts.append(
                f"{title} ({category}, efektif {effective_date}): "
                f"{content}"
            )
        return " ".join(parts).strip()
    return company_result.summary.strip()


def _build_semantic_trace_detail(semantic_result: SemanticIntentResult) -> str:
    if not semantic_result.candidates:
        return (
            semantic_result.fallback_reason
            or "No semantic intent candidates matched the current message."
        )

    candidate_text = ", ".join(
        (
            f"{candidate.intent.value}"
            f"({candidate.similarity:.2f}, {candidate.source})"
        )
        for candidate in semantic_result.candidates[:4]
    )
    if semantic_result.fallback_reason:
        return (
            f"Top semantic candidates: {candidate_text}. "
            f"{semantic_result.fallback_reason}"
        )
    return f"Top semantic candidates: {candidate_text}."


def _build_semantic_intent_assessment(
    semantic_result: SemanticIntentResult,
) -> IntentAssessment | None:
    top_candidate = semantic_result.top_candidate
    if top_candidate is None:
        return None

    direct_threshold = SEMANTIC_DIRECT_FALLBACK_THRESHOLD.get(
        semantic_result.retrieval_mode,
        0.72,
    )
    if top_candidate.similarity < direct_threshold:
        return None

    primary_intent = top_candidate.intent
    secondary_intents: list[ConversationIntent] = []
    for candidate in semantic_result.candidates[1:4]:
        if candidate.intent == primary_intent:
            continue
        if candidate.similarity >= max(direct_threshold - 0.1, top_candidate.similarity - 0.12):
            secondary_intents.append(candidate.intent)

    confidence = min(
        max(
            top_candidate.similarity
            + (0.08 if semantic_result.retrieval_mode == "vector" else 0.04),
            0.68,
        ),
        0.94,
    )

    return IntentAssessment(
        primary_intent=primary_intent,
        secondary_intents=secondary_intents[:2],
        confidence=confidence,
        matched_keywords=[
            f"semantic:{candidate.intent.value}"
            for candidate in semantic_result.candidates[:3]
        ],
    )


def _build_agent_capability_trace_detail(
    agent_result: AgentCapabilityResult,
) -> str:
    if not agent_result.candidates:
        return (
            agent_result.fallback_reason
            or "No agent capability candidate matched the current message."
        )

    candidate_text = ", ".join(
        (
            f"{candidate.agent_key}"
            f"({candidate.similarity:.2f}, {candidate.source})"
        )
        for candidate in agent_result.candidates[:4]
    )
    if agent_result.fallback_reason:
        return (
            f"Top agent capability candidates: {candidate_text}. "
            f"{agent_result.fallback_reason}"
        )
    return f"Top agent capability candidates: {candidate_text}."


def _sanitize_agent_keys(
    agent_keys: list[str] | None,
    *,
    has_attachments: bool,
) -> list[str]:
    sanitized: list[str] = []
    for agent_key in agent_keys or []:
        if agent_key not in KNOWN_AGENT_KEYS:
            continue
        if agent_key == "file-agent" and not has_attachments:
            continue
        if agent_key not in sanitized:
            sanitized.append(agent_key)
    return sanitized


def _route_to_agent_keys(route: AgentRoute) -> list[str]:
    if route == AgentRoute.HR_DATA:
        return ["hr-data-agent"]
    if route == AgentRoute.COMPANY:
        return ["company-agent"]
    if route == AgentRoute.MIXED:
        return ["hr-data-agent", "company-agent"]
    return []


def _resolve_route_from_agent_keys(agent_keys: list[str]) -> AgentRoute:
    normalized = set(agent_keys)
    needs_hr = "hr-data-agent" in normalized
    needs_company = "company-agent" in normalized
    if needs_hr and needs_company:
        return AgentRoute.MIXED
    if needs_hr:
        return AgentRoute.HR_DATA
    if needs_company:
        return AgentRoute.COMPANY
    return AgentRoute.OUT_OF_SCOPE


def _intent_matches_route(intent: ConversationIntent, route: AgentRoute) -> bool:
    if route == AgentRoute.HR_DATA:
        return intent in HR_DATA_INTENTS
    if route == AgentRoute.COMPANY:
        return intent in COMPANY_INTENTS
    if route == AgentRoute.MIXED:
        return intent in HR_DATA_INTENTS or intent in COMPANY_INTENTS
    if route == AgentRoute.OUT_OF_SCOPE:
        return intent in {
            ConversationIntent.OUT_OF_SCOPE,
            ConversationIntent.GENERAL_HR_SUPPORT,
        }
    return False


def _infer_agents_from_capabilities(
    agent_result: AgentCapabilityResult,
    *,
    has_attachments: bool,
) -> list[str]:
    threshold = AGENT_CAPABILITY_ROUTE_THRESHOLD.get(agent_result.retrieval_mode, 0.58)
    inferred = [
        candidate.agent_key
        for candidate in agent_result.candidates
        if candidate.similarity >= threshold
    ]
    return _sanitize_agent_keys(inferred, has_attachments=has_attachments)


def _build_agent_execution_plan(
    *,
    message: str,
    route: AgentRoute,
    intent: IntentAssessment,
    query_policy: dict[str, Any],
    has_attachments: bool,
    agent_result: AgentCapabilityResult,
    provider_chosen_agents: list[str] | None = None,
) -> tuple[AgentRoute, list[str], str]:
    provider_agents = _sanitize_agent_keys(
        provider_chosen_agents,
        has_attachments=has_attachments,
    )
    capability_agents = _infer_agents_from_capabilities(
        agent_result,
        has_attachments=has_attachments,
    )
    route_agents = _route_to_agent_keys(route)

    if (
        route == AgentRoute.HR_DATA
        and _should_promote_hr_route_to_mixed_for_guidance(message, intent)
    ):
        return AgentRoute.MIXED, ["hr-data-agent", "company-agent"], (
            "HR data guidance request needs both employee data and company contact guidance."
        )

    if provider_agents:
        provider_route = _resolve_route_from_agent_keys(
            [agent for agent in provider_agents if agent != "file-agent"]
        )
        deterministic_boundary = query_policy.get("boundary_mode") == "must_be_deterministic"
        cross_domain_secondary = (
            route == AgentRoute.HR_DATA
            and any(item in COMPANY_INTENTS for item in intent.secondary_intents)
        ) or (
            route == AgentRoute.COMPANY
            and any(item in HR_DATA_INTENTS for item in intent.secondary_intents)
        )
        if (
            route in {AgentRoute.OUT_OF_SCOPE, AgentRoute.COMPANY, AgentRoute.HR_DATA}
            and provider_route == AgentRoute.MIXED
        ):
            if deterministic_boundary and not cross_domain_secondary:
                return route, route_agents, (
                    "Provider mixed-agent suggestion was ignored because this query "
                    "is inside a deterministic boundary."
                )
            return AgentRoute.MIXED, ["hr-data-agent", "company-agent"], (
                "Provider selected both hr-data-agent and company-agent."
            )
        if route == AgentRoute.OUT_OF_SCOPE and provider_route != AgentRoute.OUT_OF_SCOPE:
            return provider_route, _route_to_agent_keys(provider_route), (
                "Provider-selected agents promoted the route from out_of_scope."
            )

    capability_route = _resolve_route_from_agent_keys(
        [agent for agent in capability_agents if agent != "file-agent"]
    )
    if route == AgentRoute.OUT_OF_SCOPE and capability_route != AgentRoute.OUT_OF_SCOPE:
        return capability_route, _route_to_agent_keys(capability_route), (
            "Semantic agent capabilities promoted the route from out_of_scope."
        )

    if (
        route == AgentRoute.HR_DATA
        and any(item in COMPANY_INTENTS for item in intent.secondary_intents)
        and "company-agent" in capability_agents
    ):
        return AgentRoute.MIXED, ["hr-data-agent", "company-agent"], (
            "Secondary company intent plus semantic capability suggested a mixed route."
        )

    if (
        route == AgentRoute.COMPANY
        and any(item in HR_DATA_INTENTS for item in intent.secondary_intents)
        and "hr-data-agent" in capability_agents
    ):
        return AgentRoute.MIXED, ["hr-data-agent", "company-agent"], (
            "Secondary HR intent plus semantic capability suggested a mixed route."
        )

    return route, route_agents, "Route stayed on intent-based mapping."


def _align_intent_with_route(
    intent: IntentAssessment,
    route: AgentRoute,
    semantic_result: SemanticIntentResult,
) -> tuple[IntentAssessment, AgentRoute, str | None]:
    if route in {AgentRoute.OUT_OF_SCOPE, AgentRoute.SENSITIVE_REDIRECT}:
        return intent, route, None

    if _intent_matches_route(intent.primary_intent, route):
        return intent, route, None

    aligned_candidates = [
        candidate
        for candidate in semantic_result.candidates
        if _intent_matches_route(candidate.intent, route)
    ]
    if aligned_candidates:
        primary_candidate = aligned_candidates[0]
        secondary_intents = [
            candidate.intent
            for candidate in aligned_candidates[1:4]
            if candidate.intent != primary_candidate.intent
        ]
        promoted_intent = IntentAssessment(
            primary_intent=primary_candidate.intent,
            secondary_intents=secondary_intents[:2],
            confidence=min(
                max(
                    intent.confidence,
                    primary_candidate.similarity
                    + (0.08 if semantic_result.retrieval_mode == "vector" else 0.04),
                ),
                0.94,
            ),
            matched_keywords=sorted(
                set(
                    intent.matched_keywords
                    + [
                        f"semantic:{candidate.intent.value}"
                        for candidate in aligned_candidates[:3]
                    ]
                )
            ),
        )
        return (
            promoted_intent,
            route,
            (
                "Intent was aligned with the planned route using semantic intent "
                f"candidate {primary_candidate.intent.value}."
            ),
        )

    if route == AgentRoute.COMPANY:
        promoted_intent = IntentAssessment(
            primary_intent=ConversationIntent.COMPANY_POLICY,
            secondary_intents=[],
            confidence=max(intent.confidence, 0.62),
            matched_keywords=sorted(
                set(intent.matched_keywords + ["agent_capability:company-agent"])
            ),
        )
        return (
            promoted_intent,
            route,
            (
                "Intent defaulted to company_policy because agent capability "
                "routing promoted the request into the company domain."
            ),
        )

    return (
        intent,
        AgentRoute.OUT_OF_SCOPE,
        (
            "Capability-based route promotion was discarded because no aligned "
            "semantic intent candidate was available."
        ),
    )


def _should_refine_with_attachment_preview(
    intent: IntentAssessment,
    extracted_attachment_text: str | None,
) -> bool:
    return (
        bool(extracted_attachment_text)
        and (
            intent.primary_intent
            in {ConversationIntent.GENERAL_HR_SUPPORT, ConversationIntent.OUT_OF_SCOPE}
            or intent.confidence < LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD
        )
    )


def _should_use_provider_classifier(
    intent: IntentAssessment,
    sensitivity: SensitivityAssessment,
    *,
    used_attachment_preview: bool,
    semantic_result: SemanticIntentResult,
) -> tuple[bool, str]:
    if sensitivity.level != SensitivityLevel.LOW and sensitivity.matched_keywords:
        return (
            False,
            "Skipped because local sensitivity keywords were already explicit.",
        )

    semantic_top = semantic_result.top_candidate
    semantic_threshold = SEMANTIC_PROVIDER_HINT_THRESHOLD.get(
        semantic_result.retrieval_mode,
        0.52,
    )
    if (
        semantic_top is not None
        and semantic_top.similarity >= semantic_threshold
        and (
            intent.primary_intent
            in {ConversationIntent.GENERAL_HR_SUPPORT, ConversationIntent.OUT_OF_SCOPE}
            or intent.confidence < LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD
            or (
                semantic_top.intent != intent.primary_intent
                and intent.confidence < 0.92
            )
        )
    ):
        return (
            True,
            (
                "Semantic routing found a strong candidate intent "
                f"({semantic_top.intent.value}, similarity={semantic_top.similarity:.2f})."
            ),
        )

    if (
        intent.primary_intent
        not in {ConversationIntent.GENERAL_HR_SUPPORT, ConversationIntent.OUT_OF_SCOPE}
        and intent.confidence >= LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD
        and len(intent.secondary_intents) <= 1
    ):
        return (
            False,
            (
                "Skipped because local classifier was already confident "
                f"(confidence={intent.confidence:.2f})."
            ),
        )

    if intent.primary_intent in {
        ConversationIntent.GENERAL_HR_SUPPORT,
        ConversationIntent.OUT_OF_SCOPE,
    }:
        return (
            True,
            "Local classifier still sees the request as generic or ambiguous.",
        )

    if len(intent.secondary_intents) >= 2:
        return True, "Multiple competing intents were detected locally."

    if intent.confidence < LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD:
        return (
            True,
            (
                "Local classifier confidence is below the escalation threshold "
                f"({intent.confidence:.2f})."
            ),
        )

    if used_attachment_preview:
        return True, "Attachment context changed the local interpretation, so provider confirmation is helpful."

    return False, "Skipped because local classifier result was sufficient."


def _record_duration(timings_ms: dict[str, int], key: str, started_at: float) -> None:
    timings_ms[key] = round((perf_counter() - started_at) * 1000)


def _apply_orchestration_metrics(
    context: dict[str, Any],
    *,
    classifier_source: str,
    provider_status: str,
    provider_reason: str,
    query_class: str,
    boundary_mode: str,
    used_attachment_preview: bool,
    classifier_override_count: int,
    semantic_retrieval_mode: str,
    semantic_candidate_count: int,
    semantic_fallback_used: bool,
    agent_capability_retrieval_mode: str,
    agent_capability_candidate_count: int,
    capability_route_promotion_used: bool,
    timings_ms: dict[str, int],
) -> None:
    context["metrics"] = {
        "classifier_source": classifier_source,
        "provider_status": provider_status,
        "provider_reason": provider_reason,
        "query_class": query_class,
        "boundary_mode": boundary_mode,
        "used_attachment_preview": used_attachment_preview,
        "classifier_override_count": classifier_override_count,
        "semantic_retrieval_mode": semantic_retrieval_mode,
        "semantic_candidate_count": semantic_candidate_count,
        "semantic_fallback_used": semantic_fallback_used,
        "agent_capability_retrieval_mode": agent_capability_retrieval_mode,
        "agent_capability_candidate_count": agent_capability_candidate_count,
        "capability_route_promotion_used": capability_route_promotion_used,
        "latency_ms": timings_ms,
    }


def _build_fallback_ladder(
    *,
    query_policy: dict[str, Any],
    conversation_grounding: dict[str, Any],
    classifier_source: str,
    provider_status: str,
    provider_reason: str,
    semantic_result: SemanticIntentResult,
    agent_capability_result: AgentCapabilityResult,
    retrieval_assessment: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ladder: list[dict[str, Any]] = [
        {
            "stage": "query_policy",
            "status": query_policy["boundary_mode"],
            "detail": (
                f"query_class={query_policy['query_class']}, "
                f"boundary_mode={query_policy['boundary_mode']}"
            ),
        },
        {
            "stage": "conversation_grounding",
            "status": "used" if conversation_grounding.get("used") else "skipped",
            "detail": str(conversation_grounding.get("reason") or "No grounding detail."),
        },
        {
            "stage": "classifier",
            "status": classifier_source,
            "detail": provider_reason,
        },
        {
            "stage": "provider_judge",
            "status": provider_status,
            "detail": provider_reason,
        },
        {
            "stage": "semantic_intent",
            "status": semantic_result.retrieval_mode,
            "detail": semantic_result.fallback_reason
            or f"{len(semantic_result.candidates)} candidate(s) available.",
        },
        {
            "stage": "agent_capabilities",
            "status": agent_capability_result.retrieval_mode,
            "detail": agent_capability_result.fallback_reason
            or f"{len(agent_capability_result.candidates)} candidate(s) available.",
        },
    ]

    partial_or_weak = False
    for domain, assessment in (retrieval_assessment or {}).items():
        if not isinstance(assessment, dict):
            continue
        for section, details in assessment.items():
            if not isinstance(details, dict):
                continue
            status = str(details.get("status") or "unknown")
            if status in {"partial", "weak"}:
                partial_or_weak = True
            ladder.append(
                {
                    "stage": f"{domain}_{section}",
                    "status": status,
                    "detail": str(details.get("reason") or "No detail available."),
                }
            )

    ladder.append(
        {
            "stage": "answer_completeness",
            "status": "partial_answer" if partial_or_weak else "direct_answer",
            "detail": (
                "One or more retrieval stages were partial/weak, so the answer discloses limits."
                if partial_or_weak
                else "The answer was produced from sufficiently strong retrieval."
            ),
        }
    )
    return ladder


async def _run_hr_data_agent_isolated(
    session: SessionContext,
    message: str,
    primary_intent: ConversationIntent,
    secondary_intents: list[ConversationIntent],
    conversation_history: list[dict[str, str]] | None = None,
):
    async with AsyncSessionLocal() as isolated_db:
        return await run_hr_data_agent(
            isolated_db,
            session,
            message,
            primary_intent,
            secondary_intents,
            conversation_history=conversation_history,
        )


async def _run_company_agent_isolated(
    session: SessionContext,
    message: str,
):
    async with AsyncSessionLocal() as isolated_db:
        return await run_company_agent(isolated_db, session, message)


async def orchestrate_message(
    db: AsyncSession,
    session: SessionContext,
    payload: OrchestratorRequest,
) -> OrchestratorResponse:
    trace: list[AgentTraceStep] = []
    used_agents: list[str] = []
    evidence = []
    context: dict[str, Any] = {}
    timings_ms: dict[str, int] = {}
    agent_message = payload.message.strip()
    routing_message = agent_message
    conversation_grounding = {
        "used": False,
        "reason": "Conversation grounding was not needed for this message.",
        "history_items": 0,
    }
    attachment_names = [attachment.resolved_name for attachment in payload.attachments]
    extracted_attachment_text: str | None = None
    file_summary: str | None = None
    used_attachment_preview = False

    if payload.attachments:
        file_started_at = perf_counter()
        file_result = await run_file_agent(payload.attachments)
        _record_duration(timings_ms, "file_agent", file_started_at)
        used_agents.append("file-agent")
        trace.append(
            AgentTraceStep(
                agent="file-agent",
                status="used",
                detail=file_result.summary,
            )
        )
        context["file"] = file_result.attachments
        evidence.extend(file_result.evidence)
        file_summary = file_result.summary
        extracted_attachment_text = file_result.extracted_text
        if extracted_attachment_text:
            # I.7: structured context packing – label attachment content clearly
            # so downstream agents can parse boundaries without heuristics.
            agent_message = _pack_agent_message(
                agent_message,
                attachment_text=extracted_attachment_text,
            )
            routing_message = agent_message
    else:
        trace.append(
            AgentTraceStep(
                agent="file-agent",
                status="skipped",
                detail="No attachment was supplied in this request.",
            )
        )

    classifier_overrides_started_at = perf_counter()
    classifier_overrides = await _load_classifier_overrides(db, session.company_id)
    _record_duration(timings_ms, "classifier_config", classifier_overrides_started_at)
    classifier_override_count = _count_classifier_overrides(classifier_overrides)

    if _should_use_conversation_grounding(payload.message, payload.conversation_history):
        grounded_started_at = perf_counter()
        routing_message, conversation_grounding = _build_grounded_message_from_history(
            agent_message,
            payload.conversation_history,
        )
        _record_duration(timings_ms, "conversation_grounding", grounded_started_at)
        trace.append(
            AgentTraceStep(
                agent="orchestrator",
                status="used",
                detail=(
                    "Recent conversation history was used to ground a short or referential follow-up."
                ),
            )
        )
    context["conversation_grounding"] = conversation_grounding

    semantic_started_at = perf_counter()
    semantic_result = await retrieve_intent_candidates(
        db,
        session.company_id,
        routing_message,
    )
    _record_duration(timings_ms, "semantic_intent_retrieval", semantic_started_at)
    semantic_fallback_intent = _build_semantic_intent_assessment(semantic_result)
    semantic_fallback_used = False
    context["semantic_routing"] = semantic_result.as_dict()
    trace.append(
        AgentTraceStep(
            agent="semantic-intent-retriever",
            status="used" if semantic_result.candidates else "skipped",
            detail=_build_semantic_trace_detail(semantic_result),
        )
    )
    agent_capability_started_at = perf_counter()
    agent_capability_result = await retrieve_agent_capabilities(
        db,
        session.company_id,
        routing_message,
    )
    _record_duration(timings_ms, "agent_capability_retrieval", agent_capability_started_at)
    capability_route_promotion_used = False
    context["agent_capabilities"] = agent_capability_result.as_dict()
    trace.append(
        AgentTraceStep(
            agent="semantic-agent-retriever",
            status="used" if agent_capability_result.candidates else "skipped",
            detail=_build_agent_capability_trace_detail(agent_capability_result),
        )
    )

    classification_message = _build_classification_message(
        routing_message,
        attachment_names=attachment_names,
    )
    intent = classify_intent(classification_message, classifier_overrides)
    sensitivity = assess_sensitivity(classification_message, classifier_overrides)
    sensitive_case = assess_sensitive_case(
        classification_message,
        sensitivity_level=sensitivity.level,
    )
    sensitivity = _merge_sensitive_case_sensitivity(sensitivity, sensitive_case)
    provider_input_message = classification_message

    if _should_refine_with_attachment_preview(intent, extracted_attachment_text):
        used_attachment_preview = True
        provider_input_message = _build_classification_message(
            routing_message,
            attachment_names=attachment_names,
            attachment_preview=extracted_attachment_text,
        )
        intent = classify_intent(provider_input_message, classifier_overrides)
        sensitivity = assess_sensitivity(provider_input_message, classifier_overrides)
        sensitive_case = assess_sensitive_case(
            provider_input_message,
            sensitivity_level=sensitivity.level,
        )
        sensitivity = _merge_sensitive_case_sensitivity(sensitivity, sensitive_case)
        trace.append(
            AgentTraceStep(
                agent="orchestrator",
                status="used",
                detail=(
                    "Attachment preview was folded into local classification "
                    "because the initial message was too generic or low-confidence."
                ),
            )
        )

    classifier_source = "local"
    provider_status = "skipped"
    provider_reason = "Local classifier result was used directly."
    provider_chosen_agents: list[str] = []
    should_use_provider, provider_decision_reason = _should_use_provider_classifier(
        intent,
        sensitivity,
        used_attachment_preview=used_attachment_preview,
        semantic_result=semantic_result,
    )

    if should_use_provider:
        classifier_started_at = perf_counter()
        provider_assessment = await classify_with_minimax(
            provider_input_message,
            candidate_intents=[
                candidate.as_dict() for candidate in semantic_result.candidates
            ],
            candidate_agents=[
                candidate.as_dict() for candidate in agent_capability_result.candidates
            ],
            local_assessment=intent,
        )
        _record_duration(timings_ms, "minimax_classifier", classifier_started_at)

        if (
            isinstance(provider_assessment, ProviderClassificationResult)
            and provider_assessment.is_success
        ):
            provider_intent = provider_assessment.intent
            provider_sensitivity = provider_assessment.sensitivity
            if provider_intent is not None and provider_sensitivity is not None:
                intent = provider_intent
                sensitivity = provider_sensitivity
                classifier_source = "minimax"
                provider_status = "used"
                provider_reason = "MiniMax classification replaced the local result."
                provider_chosen_agents = _sanitize_agent_keys(
                    provider_assessment.chosen_agents,
                    has_attachments=bool(payload.attachments),
                )
                used_agents.append("minimax-classifier")
                trace.append(
                    AgentTraceStep(
                        agent="minimax-classifier",
                        status="used",
                        detail=(
                            f"Provider intent={intent.primary_intent.value}, "
                            f"sensitivity={sensitivity.level.value}, "
                            f"confidence={intent.confidence:.2f}, "
                            f"chosen_agents={provider_chosen_agents or ['none']}"
                        ),
                    )
                )
        else:
            provider_status = "fallback"
            fallback_reason = (
                provider_assessment.fallback_reason
                if (
                    isinstance(provider_assessment, ProviderClassificationResult)
                    and provider_assessment.fallback_reason
                )
                else "MiniMax provider returned no usable classification result."
            )
            provider_reason = fallback_reason
            trace.append(
                AgentTraceStep(
                    agent="minimax-classifier",
                    status="fallback",
                    detail=fallback_reason,
                )
            )
            if semantic_fallback_intent is not None:
                intent = semantic_fallback_intent
                classifier_source = "semantic_retrieval"
                semantic_fallback_used = True
                if (
                    intent.primary_intent
                    == ConversationIntent.EMPLOYEE_WELLBEING_CONCERN
                    and sensitivity.level == SensitivityLevel.LOW
                ):
                    sensitivity = SensitivityAssessment(
                        level=SensitivityLevel.MEDIUM,
                        matched_keywords=["semantic:employee_wellbeing_concern"],
                        rationale=(
                            "Semantic routing indicates a wellbeing-related topic "
                            "that should be handled cautiously."
                        ),
                    )
                provider_reason = (
                    f"{fallback_reason} Semantic routing fallback promoted "
                    f"{intent.primary_intent.value}."
                )
                trace.append(
                    AgentTraceStep(
                        agent="orchestrator",
                        status="used",
                        detail=(
                            "Semantic routing fallback was applied after MiniMax "
                            f"was unavailable. intent={intent.primary_intent.value}, "
                            f"confidence={intent.confidence:.2f}"
                        ),
                )
            )
    else:
        provider_reason = provider_decision_reason
        trace.append(
            AgentTraceStep(
                agent="minimax-classifier",
                status="skipped",
                detail=provider_decision_reason,
            )
        )

    sensitive_case = assess_sensitive_case(
        provider_input_message,
        sensitivity_level=sensitivity.level,
    )
    sensitivity = _merge_sensitive_case_sensitivity(sensitivity, sensitive_case)
    if sensitive_case is not None:
        context["sensitive_handling"] = sensitive_case.as_context()
        trace.append(
            AgentTraceStep(
                agent="sensitive-policy",
                status="used",
                detail=_build_sensitive_case_trace_detail(sensitive_case),
            )
        )

    trace.append(
        AgentTraceStep(
            agent="orchestrator",
            status="used",
            detail=(
                f"Intent={intent.primary_intent.value}, "
                f"sensitivity={sensitivity.level.value}, "
                f"confidence={intent.confidence:.2f}, "
                f"classifier_source={classifier_source}"
            ),
        )
    )

    query_policy = _build_query_policy(payload.message, intent)
    context["query_policy"] = query_policy
    trace.append(
        AgentTraceStep(
            agent="orchestrator",
            status="used",
            detail=_build_query_policy_trace_detail(query_policy),
        )
    )

    _apply_orchestration_metrics(
        context,
        classifier_source=classifier_source,
        provider_status=provider_status,
        provider_reason=provider_reason,
        query_class=query_policy["query_class"],
        boundary_mode=query_policy["boundary_mode"],
        used_attachment_preview=used_attachment_preview,
        classifier_override_count=classifier_override_count,
        semantic_retrieval_mode=semantic_result.retrieval_mode,
        semantic_candidate_count=len(semantic_result.candidates),
        semantic_fallback_used=semantic_fallback_used,
        agent_capability_retrieval_mode=agent_capability_result.retrieval_mode,
        agent_capability_candidate_count=len(agent_capability_result.candidates),
        capability_route_promotion_used=capability_route_promotion_used,
        timings_ms=timings_ms,
    )
    context["fallback_ladder"] = _build_fallback_ladder(
        query_policy=query_policy,
        conversation_grounding=conversation_grounding,
        classifier_source=classifier_source,
        provider_status=provider_status,
        provider_reason=provider_reason,
        semantic_result=semantic_result,
        agent_capability_result=agent_capability_result,
    )

    if sensitivity.level != SensitivityLevel.LOW:
        request_category = _derive_request_category(
            message=payload.message,
            intent=intent,
            sensitivity=sensitivity,
            route=AgentRoute.SENSITIVE_REDIRECT,
        )
        response_mode = _resolve_response_mode(
            request_category,
            sensitivity=sensitivity,
        )
        recommended_next_steps = _build_recommended_next_steps(
            message=payload.message,
            intent=intent,
            route=AgentRoute.SENSITIVE_REDIRECT,
            request_category=request_category,
            response_mode=response_mode,
            company_records=None,
            sensitive_case=sensitive_case,
        )
        context["response_contract"] = {
            "request_category": request_category.value,
            "response_mode": response_mode.value,
            "recommended_next_steps": recommended_next_steps,
        }
        trace.append(
            AgentTraceStep(
                agent="orchestrator",
                status="used",
                detail=_build_response_contract_trace_detail(
                    request_category,
                    response_mode,
                    recommended_next_steps,
                ),
            )
        )
        return OrchestratorResponse(
            route=AgentRoute.SENSITIVE_REDIRECT,
            intent=intent,
            sensitivity=sensitivity,
            request_category=request_category,
            response_mode=response_mode,
            answer=_build_sensitive_response(sensitivity, sensitive_case),
            recommended_next_steps=recommended_next_steps,
            used_agents=used_agents,
            evidence=evidence,
            trace=trace,
            extracted_attachment_text=extracted_attachment_text,
            context=context,
        )

    initial_route = _resolve_route(intent)
    route = initial_route
    route, planned_agent_keys, agent_plan_reason = _build_agent_execution_plan(
        message=payload.message,
        route=route,
        intent=intent,
        query_policy=query_policy,
        has_attachments=bool(payload.attachments),
        agent_result=agent_capability_result,
        provider_chosen_agents=provider_chosen_agents,
    )
    intent, route, intent_alignment_reason = _align_intent_with_route(
        intent,
        route,
        semantic_result,
    )
    if route == AgentRoute.OUT_OF_SCOPE:
        planned_agent_keys = []
    else:
        planned_agent_keys = _route_to_agent_keys(route)
    capability_route_promotion_used = (
        initial_route != route
        and route != AgentRoute.OUT_OF_SCOPE
    )
    context["agent_routing"] = {
        "planned_agents": planned_agent_keys,
        "provider_chosen_agents": provider_chosen_agents,
        "semantic_candidate_agents": [
            candidate.agent_key for candidate in agent_capability_result.candidates
        ],
        "planning_reason": agent_plan_reason,
    }
    if intent_alignment_reason:
        context["agent_routing"]["intent_alignment_reason"] = intent_alignment_reason
        trace.append(
            AgentTraceStep(
                agent="orchestrator",
                status="used",
                detail=intent_alignment_reason,
            )
        )
    trace.append(
        AgentTraceStep(
            agent="orchestrator",
            status="used",
            detail=(
                f"Planned agents={planned_agent_keys or ['none']}, "
                f"route={route.value}, "
                f"reason={agent_plan_reason}"
            ),
        )
    )

    _apply_orchestration_metrics(
        context,
        classifier_source=classifier_source,
        provider_status=provider_status,
        provider_reason=provider_reason,
        query_class=query_policy["query_class"],
        boundary_mode=query_policy["boundary_mode"],
        used_attachment_preview=used_attachment_preview,
        classifier_override_count=classifier_override_count,
        semantic_retrieval_mode=semantic_result.retrieval_mode,
        semantic_candidate_count=len(semantic_result.candidates),
        semantic_fallback_used=semantic_fallback_used,
        agent_capability_retrieval_mode=agent_capability_result.retrieval_mode,
        agent_capability_candidate_count=len(agent_capability_result.candidates),
        capability_route_promotion_used=capability_route_promotion_used,
        timings_ms=timings_ms,
    )
    context["fallback_ladder"] = _build_fallback_ladder(
        query_policy=query_policy,
        conversation_grounding=conversation_grounding,
        classifier_source=classifier_source,
        provider_status=provider_status,
        provider_reason=provider_reason,
        semantic_result=semantic_result,
        agent_capability_result=agent_capability_result,
    )

    if route == AgentRoute.OUT_OF_SCOPE:
        request_category = _derive_request_category(
            message=payload.message,
            intent=intent,
            sensitivity=sensitivity,
            route=route,
        )
        response_mode = _resolve_response_mode(
            request_category,
            sensitivity=sensitivity,
        )
        recommended_next_steps = _build_recommended_next_steps(
            message=payload.message,
            intent=intent,
            route=route,
            request_category=request_category,
            response_mode=response_mode,
            company_records=None,
        )
        context["response_contract"] = {
            "request_category": request_category.value,
            "response_mode": response_mode.value,
            "recommended_next_steps": recommended_next_steps,
        }
        trace.append(
            AgentTraceStep(
                agent="orchestrator",
                status="used",
                detail=_build_response_contract_trace_detail(
                    request_category,
                    response_mode,
                    recommended_next_steps,
                ),
            )
        )
        return OrchestratorResponse(
            route=route,
            intent=intent,
            sensitivity=sensitivity,
            request_category=request_category,
            response_mode=response_mode,
            answer=_build_out_of_scope_response(intent),
            recommended_next_steps=recommended_next_steps,
            used_agents=used_agents,
            evidence=evidence,
            trace=trace,
            extracted_attachment_text=extracted_attachment_text,
            context=context,
        )

    hr_result = None
    company_result = None
    company_agent_message = (
        routing_message if conversation_grounding.get("used") else agent_message
    )

    if route == AgentRoute.MIXED and isinstance(db, AsyncSession):
        mixed_started_at = perf_counter()
        hr_result, company_result = await asyncio.gather(
            _run_hr_data_agent_isolated(
                session,
                agent_message,
                intent.primary_intent,
                intent.secondary_intents,
                payload.conversation_history,
            ),
            _run_company_agent_isolated(session, company_agent_message),
        )
        _record_duration(timings_ms, "mixed_agents_parallel", mixed_started_at)
        used_agents.extend(["hr-data-agent", "company-agent"])
        trace.append(
            AgentTraceStep(
                agent="hr-data-agent",
                status="used",
                detail=_build_hr_trace_detail(hr_result.summary),
            )
        )
        trace.append(
            AgentTraceStep(
                agent="company-agent",
                status="used",
                detail=_build_company_trace_detail(company_result),
            )
        )
        context["hr_data"] = hr_result.records
        if hr_result.records.get("retrieval_assessment"):
            context.setdefault("retrieval_assessment", {})["hr_data"] = hr_result.records[
                "retrieval_assessment"
            ]
        context["company"] = company_result.records
        if company_result.records.get("retrieval_assessment"):
            context.setdefault("retrieval_assessment", {})["company"] = company_result.records[
                "retrieval_assessment"
            ]
        evidence.extend(hr_result.evidence)
        evidence.extend(company_result.evidence)
    else:
        if route in {AgentRoute.HR_DATA, AgentRoute.MIXED}:
            hr_started_at = perf_counter()
            hr_result = await run_hr_data_agent(
                db,
                session,
                agent_message,
                intent.primary_intent,
                intent.secondary_intents,
                conversation_history=payload.conversation_history,
            )
            _record_duration(timings_ms, "hr_data_agent", hr_started_at)
            used_agents.append("hr-data-agent")
            trace.append(
                AgentTraceStep(
                    agent="hr-data-agent",
                    status="used",
                    detail=_build_hr_trace_detail(hr_result.summary),
                )
            )
            context["hr_data"] = hr_result.records
            if hr_result.records.get("retrieval_assessment"):
                context.setdefault("retrieval_assessment", {})["hr_data"] = hr_result.records[
                    "retrieval_assessment"
                ]
            evidence.extend(hr_result.evidence)

        if route in {AgentRoute.COMPANY, AgentRoute.MIXED}:
            company_started_at = perf_counter()
            company_result = await run_company_agent(db, session, company_agent_message)
            _record_duration(timings_ms, "company_agent", company_started_at)
            used_agents.append("company-agent")
            trace.append(
                AgentTraceStep(
                    agent="company-agent",
                    status="used",
                    detail=_build_company_trace_detail(company_result),
                )
            )
            context["company"] = company_result.records
            if company_result.records.get("retrieval_assessment"):
                context.setdefault("retrieval_assessment", {})["company"] = company_result.records[
                    "retrieval_assessment"
                ]
            evidence.extend(company_result.evidence)

    _apply_orchestration_metrics(
        context,
        classifier_source=classifier_source,
        provider_status=provider_status,
        provider_reason=provider_reason,
        query_class=query_policy["query_class"],
        boundary_mode=query_policy["boundary_mode"],
        used_attachment_preview=used_attachment_preview,
        classifier_override_count=classifier_override_count,
        semantic_retrieval_mode=semantic_result.retrieval_mode,
        semantic_candidate_count=len(semantic_result.candidates),
        semantic_fallback_used=semantic_fallback_used,
        agent_capability_retrieval_mode=agent_capability_result.retrieval_mode,
        agent_capability_candidate_count=len(agent_capability_result.candidates),
        capability_route_promotion_used=capability_route_promotion_used,
        timings_ms=timings_ms,
    )
    context["fallback_ladder"] = _build_fallback_ladder(
        query_policy=query_policy,
        conversation_grounding=conversation_grounding,
        classifier_source=classifier_source,
        provider_status=provider_status,
        provider_reason=provider_reason,
        semantic_result=semantic_result,
        agent_capability_result=agent_capability_result,
        retrieval_assessment=context.get("retrieval_assessment"),
    )

    answer = _synthesize_answer(
        route,
        hr_result.summary if hr_result else None,
        company_result.summary if company_result else None,
        file_summary,
    )
    request_category = _derive_request_category(
        message=payload.message,
        intent=intent,
        sensitivity=sensitivity,
        route=route,
        company_records=company_result.records if company_result else None,
    )
    response_mode = _resolve_response_mode(
        request_category,
        sensitivity=sensitivity,
    )
    recommended_next_steps = _build_recommended_next_steps(
        message=payload.message,
        intent=intent,
        route=route,
        request_category=request_category,
        response_mode=response_mode,
        company_records=company_result.records if company_result else None,
        sensitive_case=sensitive_case,
    )
    context["response_contract"] = {
        "request_category": request_category.value,
        "response_mode": response_mode.value,
        "recommended_next_steps": recommended_next_steps,
    }
    trace.append(
        AgentTraceStep(
            agent="orchestrator",
            status="used",
            detail=_build_response_contract_trace_detail(
                request_category,
                response_mode,
                recommended_next_steps,
            ),
        )
    )

    return OrchestratorResponse(
        route=route,
        intent=intent,
        sensitivity=sensitivity,
        request_category=request_category,
        response_mode=response_mode,
        answer=answer,
        recommended_next_steps=recommended_next_steps,
        used_agents=used_agents,
        evidence=evidence,
        trace=trace,
        extracted_attachment_text=extracted_attachment_text,
        context=context,
    )
