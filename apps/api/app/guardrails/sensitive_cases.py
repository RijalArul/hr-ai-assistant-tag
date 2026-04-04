from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from shared import RuleTrigger, SensitivityLevel

SensitiveActionPolicy = Literal["guidance_only", "create_task"]
SensitiveReviewPolicy = Literal["redirect_only", "mandatory_manual_review"]


@dataclass(frozen=True)
class SensitiveCaseAssessment:
    case_key: str
    label: str
    minimum_sensitivity: SensitivityLevel
    action_policy: SensitiveActionPolicy
    review_policy: SensitiveReviewPolicy
    response_template: str
    recommended_next_steps: tuple[str, ...]
    matched_markers: tuple[str, ...] = ()
    automation_trigger: RuleTrigger | None = None
    automation_intent_key: str | None = None

    def as_context(self) -> dict[str, object]:
        return {
            "case_key": self.case_key,
            "label": self.label,
            "matched_markers": list(self.matched_markers),
            "action_policy": self.action_policy,
            "review_policy": self.review_policy,
            "recommended_next_steps": list(self.recommended_next_steps),
            "automation": {
                "should_create_action": self.action_policy == "create_task",
                "trigger": self.automation_trigger.value if self.automation_trigger else None,
                "intent_key": self.automation_intent_key,
            },
        }


def _normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message.lower()).strip()


def _find_markers(message: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(marker for marker in markers if marker in message)


def _build_harassment_case(message: str) -> SensitiveCaseAssessment | None:
    markers = _find_markers(
        message,
        (
            "pelecehan seksual",
            "sexual harassment",
            "pelecehan",
            "harassment",
            "diskriminasi",
            "dibully",
            "bullying",
        ),
    )
    if not markers:
        return None

    return SensitiveCaseAssessment(
        case_key="harassment_discrimination",
        label="harassment_discrimination",
        minimum_sensitivity=SensitivityLevel.MEDIUM,
        action_policy="create_task",
        review_policy="mandatory_manual_review",
        automation_trigger=RuleTrigger.SENSITIVITY_DETECTED,
        automation_intent_key="sensitive_harassment_case",
        response_template=(
            "Terima kasih sudah menyampaikan ini. Laporan pelecehan atau diskriminasi "
            "perlu ditangani langsung oleh tim yang berwenang, bukan diproses penuh "
            "oleh AI. Aku akan menjaga respons ini tetap hati-hati dan mengarahkan "
            "kasusnya ke jalur review manual."
        ),
        recommended_next_steps=(
            "Gunakan kanal pelaporan resmi atau HR yang berwenang agar kasus ini ditangani secara rahasia dan terdokumentasi.",
            "Catat kronologi, waktu, saksi, dan bukti yang masih bisa disimpan dengan aman.",
        ),
        matched_markers=markers,
    )


def _build_unsafe_workplace_case(message: str) -> SensitiveCaseAssessment | None:
    direct_markers = _find_markers(
        message,
        (
            "unsafe workplace",
            "tempat kerja tidak aman",
            "lingkungan kerja tidak aman",
            "merasa tidak aman di kantor",
            "ancaman",
            "kekerasan",
        ),
    )
    if direct_markers:
        markers = direct_markers
    elif "tidak aman" in message and any(
        token in message
        for token in ("kantor", "tempat kerja", "workplace", "lingkungan kerja")
    ):
        markers = ("tidak aman",)
    else:
        return None

    return SensitiveCaseAssessment(
        case_key="unsafe_workplace",
        label="unsafe_workplace",
        minimum_sensitivity=SensitivityLevel.HIGH,
        action_policy="create_task",
        review_policy="mandatory_manual_review",
        automation_trigger=RuleTrigger.SENSITIVITY_DETECTED,
        automation_intent_key="sensitive_unsafe_workplace_case",
        response_template=(
            "Terima kasih sudah memberi tahu soal rasa tidak aman di tempat kerja. "
            "Kasus seperti ini perlu masuk ke penanganan manusia yang berwenang "
            "secepatnya, jadi aku tidak akan mencoba menyimpulkan atau menormalkan "
            "situasinya lewat jalur otomatis."
        ),
        recommended_next_steps=(
            "Jika ada risiko keselamatan yang mendesak, gunakan jalur darurat atau PIC keamanan perusahaan secepatnya.",
            "Simpan detail lokasi, waktu, pihak yang terlibat, dan bukti yang masih aman untuk dicatat.",
        ),
        matched_markers=markers,
    )


def _build_manager_conflict_case(message: str) -> SensitiveCaseAssessment | None:
    has_manager_anchor = any(
        marker in message for marker in ("atasan", "manager", "manajer", "supervisor", "lead")
    )
    matched_markers = _find_markers(
        message,
        (
            "konflik",
            "berselisih",
            "bermasalah",
            "toxic",
            "mengintimidasi",
            "intimidasi",
        ),
    )
    if not (has_manager_anchor and matched_markers):
        return None

    markers = ("atasan/manager", *matched_markers)
    return SensitiveCaseAssessment(
        case_key="manager_conflict",
        label="manager_conflict",
        minimum_sensitivity=SensitivityLevel.MEDIUM,
        action_policy="guidance_only",
        review_policy="redirect_only",
        response_template=(
            "Terima kasih sudah cerita soal hubungan dengan atasan atau manager. "
            "Aku tidak akan mendorong keputusan formal terlalu cepat, tetapi situasi "
            "seperti ini biasanya lebih aman dibawa ke jalur HRBP atau HR yang netral "
            "kalau kamu belum nyaman bicara langsung."
        ),
        recommended_next_steps=(
            "Rangkum contoh situasi, waktu kejadian, dan dampaknya ke pekerjaan sebelum bicara dengan HRBP atau HR.",
            "Kalau belum aman bicara langsung dengan atasan, gunakan HRBP atau HR sebagai pihak netral untuk langkah awal.",
        ),
        matched_markers=tuple(markers),
    )


def _build_burnout_case(message: str) -> SensitiveCaseAssessment | None:
    markers = _find_markers(
        message,
        (
            "burnout",
            "stress berat",
            "stres berat",
            "depresi",
            "kewalahan",
            "kelelahan",
            "kelelahan mental",
        ),
    )
    if not markers:
        return None

    return SensitiveCaseAssessment(
        case_key="burnout_emotional_distress",
        label="burnout_emotional_distress",
        minimum_sensitivity=SensitivityLevel.MEDIUM,
        action_policy="guidance_only",
        review_policy="redirect_only",
        response_template=(
            "Terima kasih sudah jujur soal kondisi kamu. Kalau kamu sedang merasa "
            "burnout atau kewalahan, aku tidak akan mengubahnya menjadi proses formal "
            "secara otomatis. Langkah paling aman biasanya adalah mencari dukungan "
            "manusia dulu dari HRBP, HR, atau atasan yang kamu percaya."
        ),
        recommended_next_steps=(
            "Prioritaskan dukungan manusia dulu, seperti HRBP, HR, atau atasan yang kamu percaya kalau situasinya aman.",
            "Catat pemicu utama, dampaknya ke kerja, dan bantuan yang paling kamu butuhkan supaya follow-up lebih jelas.",
        ),
        matched_markers=markers,
    )


def _build_resignation_case(message: str) -> SensitiveCaseAssessment | None:
    markers = _find_markers(
        message,
        (
            "resign",
            "mengundurkan diri",
            "pengunduran diri",
            "notice period",
            "surat resign",
        ),
    )
    if not markers:
        return None

    return SensitiveCaseAssessment(
        case_key="resignation_intention",
        label="resignation_intention",
        minimum_sensitivity=SensitivityLevel.MEDIUM,
        action_policy="guidance_only",
        review_policy="redirect_only",
        response_template=(
            "Terima kasih sudah terbuka soal niat resign. Aku tidak akan mendorong "
            "langkah formal pengunduran diri lewat jalur otomatis. Kalau kamu masih "
            "menimbang pilihan, biasanya lebih aman merapikan alasan utamanya dulu "
            "lalu bicara dengan HRBP atau atasan yang relevan saat kamu siap."
        ),
        recommended_next_steps=(
            "Rangkum alasan utama, timeline, dan hal yang paling mendesak sebelum bicara dengan HRBP atau atasan yang relevan.",
            "Kalau kamu belum siap mengambil keputusan formal, fokus dulu pada opsi aman seperti diskusi, klarifikasi ekspektasi, atau internal move.",
        ),
        matched_markers=markers,
    )


def assess_sensitive_case(
    message: str,
    *,
    sensitivity_level: SensitivityLevel,
) -> SensitiveCaseAssessment | None:
    normalized = _normalize_message(message)

    for builder in (
        _build_harassment_case,
        _build_unsafe_workplace_case,
        _build_manager_conflict_case,
        _build_burnout_case,
        _build_resignation_case,
    ):
        case = builder(normalized)
        if case is not None:
            return case

    if sensitivity_level == SensitivityLevel.LOW:
        return None

    return SensitiveCaseAssessment(
        case_key="generic_sensitive",
        label="generic_sensitive",
        minimum_sensitivity=sensitivity_level,
        action_policy="guidance_only",
        review_policy="redirect_only",
        response_template=(
            "Terima kasih sudah menyampaikan hal yang sensitif ini. Aku tidak akan "
            "menyimpulkan atau mengotomasi penanganannya. Jalur yang paling aman "
            "adalah meminta bantuan HR atau pihak perusahaan yang berwenang untuk "
            "menangani kasus ini secara manusiawi."
        ),
        recommended_next_steps=(
            "Gunakan jalur HR atau kanal pelaporan resmi agar kasus sensitif ini ditangani manusia yang berwenang.",
            "Simpan konteks atau bukti yang masih aman bila kamu perlu menjelaskan kasusnya lebih lanjut.",
        ),
    )
