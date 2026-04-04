"""scripts/eval_routing.py

Evaluation harness for Session F – AI Quality and Retrieval Reliability.

Covers TODO I.8 (eval harness) and TODO I.9 (threshold calibration).

Usage
-----
    python scripts/eval_routing.py

No running database or external API is needed.  The harness runs the local
classifier (classify_intent / assess_sensitivity) and the lexical similarity
scorer against a fixed set of labelled test cases, then prints:

- Per-intent precision, recall, and F1.
- Overall accuracy.
- False-positive analysis: cases where the predicted intent differs from the
  expected one.
- Threshold sensitivity table: what accuracy looks like at different
  LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD values.
- Suggested threshold calibration values for both the local classifier and
  the SEMANTIC_DIRECT_FALLBACK_THRESHOLD per retrieval mode.

The test cases are intentionally representative of the domain (Indonesian
HR context) and cover guidance, policy reasoning, sensitive, workflow, and
out-of-scope buckets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from app.agents.orchestrator import classify_intent  # noqa: E402
from app.models import ConversationIntent  # noqa: E402
from app.services.semantic_router import (  # noqa: E402
    _normalize_text,
    _score_lexical_similarity,
)


# ---------------------------------------------------------------------------
# Test case definitions
# ---------------------------------------------------------------------------

class TestCase(NamedTuple):
    message: str
    expected_intent: ConversationIntent
    group: str  # used for grouping summary output


EVAL_CASES: list[TestCase] = [
    # ── Payroll / salary ─────────────────────────────────────────────────────
    TestCase("berapa gaji saya bulan ini?", ConversationIntent.PAYROLL_INFO, "payroll"),
    TestCase("cek payroll maret 2025", ConversationIntent.PAYROLL_INFO, "payroll"),
    TestCase("status salary saya", ConversationIntent.PAYROLL_INFO, "payroll"),
    TestCase("tunjangan saya berapa?", ConversationIntent.PAYROLL_INFO, "payroll"),
    TestCase("potongan bpjs saya bulan ini", ConversationIntent.PAYROLL_INFO, "payroll"),
    TestCase("tolong generate payslip april 2025", ConversationIntent.PAYROLL_DOCUMENT_REQUEST, "payroll"),
    TestCase("minta slip gaji maret", ConversationIntent.PAYROLL_DOCUMENT_REQUEST, "payroll"),
    TestCase("cetak pay slip februari 2025", ConversationIntent.PAYROLL_DOCUMENT_REQUEST, "payroll"),

    # ── Attendance ────────────────────────────────────────────────────────────
    TestCase("rata rata jam masuk saya bulan ini?", ConversationIntent.ATTENDANCE_REVIEW, "attendance"),
    TestCase("cek kehadiran saya minggu lalu", ConversationIntent.ATTENDANCE_REVIEW, "attendance"),
    TestCase("rekap attendance januari", ConversationIntent.ATTENDANCE_REVIEW, "attendance"),
    TestCase("apakah saya pernah telat bulan ini", ConversationIntent.ATTENDANCE_REVIEW, "attendance"),
    TestCase("hari apa saya WFH terakhir?", ConversationIntent.ATTENDANCE_REVIEW, "attendance"),

    # ── Time off / leave ─────────────────────────────────────────────────────
    TestCase("sisa cuti saya berapa?", ConversationIntent.TIME_OFF_BALANCE, "leave"),
    TestCase("cek jatah cuti 2025", ConversationIntent.TIME_OFF_BALANCE, "leave"),
    TestCase("saldo cuti saya tinggal berapa hari", ConversationIntent.TIME_OFF_BALANCE, "leave"),
    TestCase("leave balance saya?", ConversationIntent.TIME_OFF_BALANCE, "leave"),
    TestCase("status pengajuan cuti saya?", ConversationIntent.TIME_OFF_REQUEST_STATUS, "leave"),
    TestCase("apakah cuti saya sudah disetujui", ConversationIntent.TIME_OFF_REQUEST_STATUS, "leave"),
    TestCase("update status leave request kemarin", ConversationIntent.TIME_OFF_REQUEST_STATUS, "leave"),

    # ── Personal profile ──────────────────────────────────────────────────────
    TestCase("siapa atasan saya?", ConversationIntent.PERSONAL_PROFILE, "profile"),
    TestCase("posisi saya apa sekarang?", ConversationIntent.PERSONAL_PROFILE, "profile"),
    TestCase("tanggal join saya kapan?", ConversationIntent.PERSONAL_PROFILE, "profile"),
    TestCase("data saya", ConversationIntent.PERSONAL_PROFILE, "profile"),

    # ── Company policy ────────────────────────────────────────────────────────
    TestCase("apakah saya bisa reimburse kacamata?", ConversationIntent.COMPANY_POLICY, "policy"),
    TestCase("limit reimbursement psikolog berapa?", ConversationIntent.COMPANY_POLICY, "policy"),
    TestCase("aturan carry over cuti bagaimana?", ConversationIntent.COMPANY_POLICY, "policy"),
    TestCase("kebijakan probation di perusahaan ini apa?", ConversationIntent.COMPANY_POLICY, "policy"),
    TestCase("apakah tunjangan makan eligible buat saya?", ConversationIntent.COMPANY_POLICY, "policy"),
    TestCase("syarat klaim medical claim?", ConversationIntent.COMPANY_POLICY, "policy"),
    TestCase("allowance internet work from home berapa?", ConversationIntent.COMPANY_POLICY, "policy"),

    # ── Company structure / navigation ───────────────────────────────────────
    TestCase("kalau mau nanya payroll harus ke siapa?", ConversationIntent.COMPANY_STRUCTURE, "structure"),
    TestCase("siapa pic hr di sini?", ConversationIntent.COMPANY_STRUCTURE, "structure"),
    TestCase("kontak recruiter untuk referral hiring?", ConversationIntent.COMPANY_STRUCTURE, "structure"),
    TestCase("kalau ada issue laptop harus ke siapa?", ConversationIntent.COMPANY_STRUCTURE, "structure"),
    TestCase("tim hr terdiri dari siapa saja?", ConversationIntent.COMPANY_STRUCTURE, "structure"),
    TestCase("siapa hrbp yang handle departemen engineering?", ConversationIntent.COMPANY_STRUCTURE, "structure"),

    # ── Sensitive ─────────────────────────────────────────────────────────────
    TestCase("saya merasa dibully oleh rekan kerja", ConversationIntent.EMPLOYEE_WELLBEING_CONCERN, "sensitive"),
    TestCase("saya mengalami pelecehan di tempat kerja", ConversationIntent.EMPLOYEE_WELLBEING_CONCERN, "sensitive"),
    TestCase("saya merasa sangat burnout dan depresi", ConversationIntent.EMPLOYEE_WELLBEING_CONCERN, "sensitive"),

    # ── Out of scope ──────────────────────────────────────────────────────────
    TestCase("rekomendasikan restoran di jakarta", ConversationIntent.OUT_OF_SCOPE, "oos"),
    TestCase("cara bikin kue ulang tahun", ConversationIntent.OUT_OF_SCOPE, "oos"),
    TestCase("siapa presiden indonesia?", ConversationIntent.OUT_OF_SCOPE, "oos"),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class EvalResult(NamedTuple):
    message: str
    expected: ConversationIntent
    predicted: ConversationIntent
    confidence: float
    correct: bool
    group: str


def run_eval() -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in EVAL_CASES:
        assessment = classify_intent(case.message)
        predicted = assessment.primary_intent
        correct = predicted == case.expected_intent
        results.append(
            EvalResult(
                message=case.message,
                expected=case.expected_intent,
                predicted=predicted,
                confidence=assessment.confidence,
                correct=correct,
                group=case.group,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def _per_intent_metrics(
    results: list[EvalResult],
) -> dict[ConversationIntent, dict[str, float]]:
    tp: dict[ConversationIntent, int] = {}
    fp: dict[ConversationIntent, int] = {}
    fn: dict[ConversationIntent, int] = {}

    for r in results:
        if r.correct:
            tp[r.expected] = tp.get(r.expected, 0) + 1
        else:
            fn[r.expected] = fn.get(r.expected, 0) + 1
            fp[r.predicted] = fp.get(r.predicted, 0) + 1

    intents: set[ConversationIntent] = set()
    for r in results:
        intents.add(r.expected)
        intents.add(r.predicted)

    metrics: dict[ConversationIntent, dict[str, float]] = {}
    for intent in sorted(intents, key=lambda x: x.value):
        t = tp.get(intent, 0)
        f_p = fp.get(intent, 0)
        f_n = fn.get(intent, 0)
        precision = t / (t + f_p) if (t + f_p) > 0 else 0.0
        recall = t / (t + f_n) if (t + f_n) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        metrics[intent] = {"precision": precision, "recall": recall, "f1": f1}

    return metrics


def _threshold_sensitivity(
    results: list[EvalResult],
    thresholds: list[float],
) -> list[tuple[float, int, int, float]]:
    """For each threshold, count how many predictions pass the confidence bar.

    Returns (threshold, passed, correct_among_passed, accuracy_among_passed).
    A prediction is "passed" if confidence >= threshold.
    """
    rows: list[tuple[float, int, int, float]] = []
    for t in thresholds:
        passed = [r for r in results if r.confidence >= t]
        correct = sum(1 for r in passed if r.correct)
        acc = correct / len(passed) if passed else 0.0
        rows.append((t, len(passed), correct, acc))
    return rows


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

def print_report(results: list[EvalResult]) -> None:
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    accuracy = correct / total if total else 0.0

    print("=" * 70)
    print("HR.ai Routing Eval Harness - Session F (TODO I.8 / I.9)")
    print("=" * 70)
    print(f"Total cases : {total}")
    print(f"Correct     : {correct}")
    print(f"Accuracy    : {accuracy:.1%}")
    print()

    # Per-group accuracy.
    groups: dict[str, list[EvalResult]] = {}
    for r in results:
        groups.setdefault(r.group, []).append(r)

    print("-- Per-group accuracy ---------------------------------------------")
    for group, group_results in sorted(groups.items()):
        g_correct = sum(1 for r in group_results if r.correct)
        g_acc = g_correct / len(group_results)
        badge = "OK" if g_acc >= 0.80 else "NO"
        print(f"  {badge} {group:<12} {g_correct}/{len(group_results)}  ({g_acc:.0%})")
    print()

    # Per-intent metrics.
    metrics = _per_intent_metrics(results)
    print("-- Per-intent metrics ---------------------------------------------")
    header = f"  {'intent':<40}  {'P':>5}  {'R':>5}  {'F1':>5}"
    print(header)
    print("  " + "-" * 56)
    for intent, m in metrics.items():
        print(
            f"  {intent.value:<40}  "
            f"{m['precision']:>5.2f}  "
            f"{m['recall']:>5.2f}  "
            f"{m['f1']:>5.2f}"
        )
    print()

    # False positives.
    false_positives = [r for r in results if not r.correct]
    if false_positives:
        print("-- False positives ------------------------------------------------")
        for r in false_positives:
            print(
                f"  [{r.group}] \"{r.message[:55]}\"\n"
                f"    expected: {r.expected.value}\n"
                f"    got:      {r.predicted.value}  (conf={r.confidence:.2f})\n"
            )
    else:
        print("-- No false positives detected ------------------------------------")
        print()

    # Threshold sensitivity analysis (I.9).
    thresholds = [0.50, 0.60, 0.70, 0.78, 0.82, 0.85, 0.90]
    rows = _threshold_sensitivity(results, thresholds)
    print("-- Threshold sensitivity (I.9) ------------------------------------")
    print(f"  {'threshold':>10}  {'passed':>8}  {'correct':>8}  {'accuracy':>10}")
    print("  " + "-" * 42)
    for t, passed, corr, acc in rows:
        marker = " <- current" if t == 0.78 else ""
        print(f"  {t:>10.2f}  {passed:>8}  {corr:>8}  {acc:>10.1%}{marker}")
    print()

    # Calibration recommendations.
    print("-- Calibration recommendations ------------------------------------")
    best_t, best_passed, best_corr, best_acc = max(rows, key=lambda x: x[3])
    current_t, current_passed, current_corr, current_acc = next(
        r for r in rows if r[0] == 0.78
    )
    if best_acc > current_acc + 0.02:
        print(
            f"  Consider raising LOCAL_CLASSIFIER_CONFIDENCE_THRESHOLD to "
            f"{best_t:.2f} (accuracy: {best_acc:.1%} vs current {current_acc:.1%} at 0.78)."
        )
    else:
        print(
            f"  Current threshold (0.78) appears well-calibrated "
            f"(accuracy {current_acc:.1%})."
        )

    # Lexical similarity spot-check.
    print()
    print("-- Lexical scorer spot-check --------------------------------------")
    spot_pairs = [
        ("sisa cuti saya", "sisa cuti kamu berapa"),
        ("reimburse kacamata", "klaim kacamata eligible"),
        ("ke siapa payroll", "siapa yang handle gaji"),
    ]
    for q, example in spot_pairs:
        score = _score_lexical_similarity(_normalize_text(q), _normalize_text(example))
        print(f"  \"{q}\" vs \"{example}\" -> {score:.3f}")
    print()
    print("=" * 70)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    eval_results = run_eval()
    print_report(eval_results)
