from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext
from app.models import CompanyAgentResult, EvidenceItem
from app.services.embeddings import generate_embedding, to_pgvector_literal
from app.services.cache import get_cache

RULE_CATEGORY_KEYWORDS = {
    "leave": ["cuti", "leave", "izin", "carry over", "cuti sakit", "cuti tahunan"],
    "attendance": ["attendance", "kehadiran", "presensi", "telat", "terlambat", "jam kerja"],
    "work_arrangement": ["wfh", "work from home", "remote", "hybrid"],
    "payroll": ["gaji", "salary", "payroll", "kompensasi", "bpjs", "pph21", "slip gaji"],
    "conduct": ["kode etik", "integritas", "diskriminasi", "pelecehan", "conduct"],
}

DEPARTMENT_KEYWORDS = {
    "human resources": ["hr", "human resources", "personalia"],
    "it": ["it", "teknologi", "engineering", "developer"],
}

MONTH_NAMES_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


def _format_date(value: date | None) -> str:
    if value is None:
        return "-"
    return f"{value.day} {MONTH_NAMES_ID[value.month]} {value.year}"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _normalize_rule_version_key(rule: dict[str, Any]) -> str:
    title = _normalize_text(str(rule.get("title") or ""))
    category = _normalize_text(str(rule.get("category") or ""))
    return f"{category}::{title}"


def _parse_effective_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _contains_term(text: str, term: str) -> bool:
    pattern = rf"(?<!\w){re.escape(term.lower())}(?!\w)"
    return re.search(pattern, text) is not None


def _serialize_rule(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    effective_date = data.get("effective_date")
    if isinstance(effective_date, date):
        data["effective_date"] = effective_date.isoformat()
    return data


def _snippet(text: str, *, max_length: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


async def _load_company_rules(
    db: AsyncSession,
    company_id: str,
) -> list[dict[str, Any]]:
    cache = get_cache("company_rules")
    cache_key = f"rules:{company_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    result = await db.execute(
        text(
            """
            SELECT
                id::text AS id,
                title,
                category,
                content,
                effective_date,
                is_active
            FROM company_rules
            WHERE company_id = CAST(:company_id AS uuid)
              AND is_active = true
            ORDER BY effective_date DESC NULLS LAST, created_at DESC
            """
        ),
        {"company_id": company_id},
    )
    rules = [_serialize_rule(dict(row)) for row in result.mappings().all()]
    cache.set(cache_key, rules)
    return rules


async def _load_company_structure(
    db: AsyncSession,
    company_id: str,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT
                d.id::text AS department_id,
                d.name AS department_name,
                parent.name AS parent_department_name,
                head.name AS head_employee_name
            FROM departments d
            LEFT JOIN departments parent
              ON parent.id = d.parent_id
            LEFT JOIN employees head
              ON head.id = d.head_employee_id
            WHERE d.company_id = CAST(:company_id AS uuid)
            ORDER BY d.name ASC
            """
        ),
        {"company_id": company_id},
    )
    return [dict(row) for row in result.mappings().all()]


async def _search_rule_chunks_by_vector(
    db: AsyncSession,
    company_id: str,
    message: str,
) -> list[dict[str, Any]]:
    query_embedding = generate_embedding(message)
    if query_embedding is None:
        return []

    try:
        result = await db.execute(
            text(
                """
                SELECT
                    r.id::text AS id,
                    r.title,
                    r.category,
                    r.content,
                    r.effective_date,
                    r.is_active,
                    c.content_chunk,
                    1 - (c.embedding <=> CAST(:query_embedding AS vector)) AS similarity
                FROM company_rule_chunks c
                INNER JOIN company_rules r
                  ON r.id = c.company_rule_id
                WHERE c.company_id = CAST(:company_id AS uuid)
                  AND r.is_active = true
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> CAST(:query_embedding AS vector)
                LIMIT 5
                """
            ),
            {
                "company_id": company_id,
                "query_embedding": to_pgvector_literal(query_embedding),
            },
        )
    except Exception:
        return []
    rows = result.mappings().all()
    if not rows:
        return []

    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = _serialize_rule(dict(row))
        rule_id = data["id"]
        similarity = float(data["similarity"])
        if similarity < 0.55:
            continue

        existing = merged.get(rule_id)
        if existing is None or similarity > existing["similarity"]:
            merged[rule_id] = {
                "id": data["id"],
                "title": data["title"],
                "category": data["category"],
                "content": data["content"],
                "effective_date": data["effective_date"],
                "is_active": data["is_active"],
                "matched_terms": ["vector_search"],
                "matched_chunk": data["content_chunk"],
                "similarity": similarity,
                "ranking_score": similarity,
            }

    ranked = sorted(
        merged.values(),
        key=lambda item: item["similarity"],
        reverse=True,
    )
    return ranked[:3]


def _score_rule(message: str, rule: dict[str, Any]) -> tuple[int, list[str]]:
    lowered = _normalize_text(message)
    matched_terms: list[str] = []
    score = 0

    category = rule["category"]
    for keyword in RULE_CATEGORY_KEYWORDS.get(category, []):
        if _contains_term(lowered, keyword):
            score += 3
            matched_terms.append(keyword)

    searchable_fields = f"{rule['title']} {rule['content']}".lower()
    tokens = [
        token
        for token in re.findall(r"[a-zA-Z0-9_]{3,}", lowered)
        if token not in {
            "dan",
            "yang",
            "untuk",
            "saya",
            "apa",
            "bagaimana",
            "aturan",
            "tahun",
            "berapa",
            "this",
        }
    ]
    for token in tokens[:8]:
        if _contains_term(searchable_fields, token):
            score += 1
            matched_terms.append(token)

    if _contains_term(lowered, rule["title"]):
        score += 4
        matched_terms.append(rule["title"])

    return score, matched_terms


def _rank_rules(message: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for rule in rules:
        score, matched_terms = _score_rule(message, rule)
        if score > 0:
            enriched_rule = dict(rule)
            enriched_rule["matched_terms"] = sorted(set(matched_terms))
            enriched_rule["ranking_score"] = score
            ranked.append((score, enriched_rule))

    ranked.sort(
        key=lambda item: (
            item[0],
            item[1]["effective_date"] or "",
        ),
        reverse=True,
    )
    return [item[1] for item in ranked[:3]]


def _apply_policy_freshness(
    matched_rules: list[dict[str, Any]],
    all_rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_by_key: dict[str, dict[str, Any]] = {}
    for rule in all_rules:
        key = _normalize_rule_version_key(rule)
        effective_date = _parse_effective_date(rule.get("effective_date"))
        existing = latest_by_key.get(key)
        if effective_date is None:
            continue
        existing_effective_date = (
            _parse_effective_date(existing.get("effective_date")) if existing else None
        )
        if existing is None or (
            existing_effective_date is not None and effective_date > existing_effective_date
        ):
            latest_by_key[key] = dict(rule)

    adjusted_by_key: dict[str, dict[str, Any]] = {}
    for rule in matched_rules:
        key = _normalize_rule_version_key(rule)
        effective_date = _parse_effective_date(rule.get("effective_date"))
        latest_rule = latest_by_key.get(key)
        latest_effective_date = (
            _parse_effective_date(latest_rule.get("effective_date"))
            if latest_rule is not None
            else None
        )
        enriched = dict(rule)
        if (
            latest_rule is not None
            and latest_rule.get("id") != rule.get("id")
            and latest_effective_date is not None
            and (effective_date is None or latest_effective_date > effective_date)
        ):
            enriched = {
                **dict(latest_rule),
                "matched_terms": list(rule.get("matched_terms", [])),
                "matched_chunk": rule.get("matched_chunk"),
                "similarity": rule.get("similarity"),
                "ranking_score": rule.get("ranking_score", 0.0),
                "promoted_from_rule_id": rule.get("id"),
                "version_source": "latest_active_version",
            }
            effective_date = latest_effective_date
        else:
            enriched["version_source"] = "matched_version"

        freshness_status = "unknown"
        if effective_date is not None and latest_effective_date is not None:
            freshness_status = (
                "current" if effective_date >= latest_effective_date else "outdated"
            )
        freshness_boost = 0.0
        if freshness_status == "current":
            freshness_boost = 0.04
        elif freshness_status == "outdated":
            freshness_boost = -0.04

        ranking_score = float(rule.get("ranking_score", 0.0) or 0.0) + freshness_boost
        enriched["freshness_status"] = freshness_status
        enriched["latest_effective_date"] = (
            latest_effective_date.isoformat() if latest_effective_date else None
        )
        enriched["ranking_score"] = round(ranking_score, 4)
        existing = adjusted_by_key.get(key)
        if existing is None:
            adjusted_by_key[key] = enriched
            continue

        existing_score = float(existing.get("ranking_score", 0.0) or 0.0)
        if ranking_score > existing_score:
            adjusted_by_key[key] = enriched
            continue

        if ranking_score == existing_score and (
            (enriched.get("effective_date") or "") > (existing.get("effective_date") or "")
        ):
            adjusted_by_key[key] = enriched

    adjusted_rules = list(adjusted_by_key.values())
    adjusted_rules.sort(
        key=lambda item: (
            float(item.get("ranking_score", 0.0) or 0.0),
            item.get("effective_date") or "",
        ),
        reverse=True,
    )
    return adjusted_rules[:3]


def _build_retrieval_assessment(
    status: str,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        **extra,
    }


def _assess_policy_retrieval(
    matched_rules: list[dict[str, Any]],
    *,
    retrieval_strategy: str,
) -> dict[str, Any]:
    if not matched_rules:
        return _build_retrieval_assessment(
            "weak",
            "Referensi policy yang ditemukan belum cukup kuat untuk dijadikan jawaban utama.",
            retrieval_strategy=retrieval_strategy,
            match_count=0,
        )

    version_promotion_used = any(
        rule.get("version_source") == "latest_active_version" for rule in matched_rules
    )
    if version_promotion_used:
        return _build_retrieval_assessment(
            "partial",
            "Semantic match sempat mengarah ke versi policy yang lebih lama, jadi sistem mempromosikan versi aktif terbaru dengan policy key yang sama sebagai referensi utama.",
            retrieval_strategy=retrieval_strategy,
            match_count=len(matched_rules),
            version_promotion_used=True,
        )

    if retrieval_strategy == "vector":
        best_similarity = max(float(rule.get("similarity", 0.0) or 0.0) for rule in matched_rules)
        top_rule = matched_rules[0]
        if top_rule.get("freshness_status") == "outdated":
            return _build_retrieval_assessment(
                "partial",
                "Rule yang paling mirip masih versi lama, jadi jawaban ini perlu dibaca dengan hati-hati sambil mengutamakan versi terbaru yang berlaku.",
                retrieval_strategy=retrieval_strategy,
                best_similarity=round(best_similarity, 4),
                match_count=len(matched_rules),
                freshness_status="outdated",
            )
        if best_similarity >= 0.78:
            return _build_retrieval_assessment(
                "enough",
                "Kecocokan semantic policy cukup kuat untuk dipakai sebagai referensi utama.",
                retrieval_strategy=retrieval_strategy,
                best_similarity=round(best_similarity, 4),
                match_count=len(matched_rules),
            )
        return _build_retrieval_assessment(
            "partial",
            "Kecocokan semantic policy masih menengah, jadi jawaban ini sebaiknya dianggap referensi awal.",
            retrieval_strategy=retrieval_strategy,
            best_similarity=round(best_similarity, 4),
            match_count=len(matched_rules),
        )

    strongest_keyword_count = max(len(rule.get("matched_terms", [])) for rule in matched_rules)
    if matched_rules[0].get("freshness_status") == "outdated":
        return _build_retrieval_assessment(
            "partial",
            "Policy yang paling cocok masih versi lama, jadi jawaban ini harus dibaca sebagai referensi awal sambil mengutamakan policy terbaru yang berlaku.",
            retrieval_strategy=retrieval_strategy,
            strongest_keyword_count=strongest_keyword_count,
            match_count=len(matched_rules),
            freshness_status="outdated",
        )
    if len(matched_rules) >= 2 or strongest_keyword_count >= 3:
        return _build_retrieval_assessment(
            "enough",
            "Keyword dan konteks policy yang ditemukan cukup kuat untuk dipakai sebagai referensi utama.",
            retrieval_strategy=retrieval_strategy,
            strongest_keyword_count=strongest_keyword_count,
            match_count=len(matched_rules),
        )

    return _build_retrieval_assessment(
        "partial",
        "Policy yang ditemukan masih berdasarkan kecocokan keyword yang terbatas, jadi jawabannya masih bersifat awal.",
        retrieval_strategy=retrieval_strategy,
        strongest_keyword_count=strongest_keyword_count,
        match_count=len(matched_rules),
    )


def _select_departments(
    message: str,
    departments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    lowered = _normalize_text(message)
    selected: list[dict[str, Any]] = []

    for department in departments:
        department_name = department["department_name"].lower()
        if department_name in lowered and department not in selected:
            selected.append(department)

    for department_name, keywords in DEPARTMENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            for department in departments:
                if department["department_name"].lower() == department_name:
                    if department not in selected:
                        selected.append(department)

    if selected:
        return selected
    return departments[:3]


def _summarize_rules(rules: list[dict[str, Any]]) -> str:
    if not rules:
        return (
            "Aku tidak menemukan kebijakan perusahaan yang cukup relevan dari "
            "kata kunci yang diberikan."
        )

    parts = []
    for rule in rules:
        effective_date = (
            _format_date(date.fromisoformat(rule["effective_date"]))
            if rule.get("effective_date")
            else "-"
        )
        parts.append(
            f"{rule['title']} ({rule['category']}, efektif {effective_date}): "
            f"{re.sub(r'\s+', ' ', rule['content']).strip()}"
        )
    return " ".join(parts)


def _summarize_structure(departments: list[dict[str, Any]]) -> str:
    if not departments:
        return "Aku tidak menemukan struktur departemen perusahaan untuk company ini."

    parts = []
    for department in departments:
        parts.append(
            f"Departemen {department['department_name']} dipimpin oleh "
            f"{department['head_employee_name'] or 'belum ditetapkan'}."
        )
    return " ".join(parts)


def _wants_structure(message: str) -> bool:
    lowered = _normalize_text(message)
    return any(
        keyword in lowered
        for keyword in [
            "struktur",
            "departemen",
            "department",
            "tim hr",
            "kepala departemen",
            "head of",
        ]
    )


async def run_company_agent(
    db: AsyncSession,
    session: SessionContext,
    message: str,
) -> CompanyAgentResult:
    wants_structure = _wants_structure(message)
    rules = await _load_company_rules(db, session.company_id)
    vector_matches = await _search_rule_chunks_by_vector(db, session.company_id, message)
    if vector_matches:
        matched_rules = _apply_policy_freshness(vector_matches, rules)
    else:
        matched_rules = _apply_policy_freshness(_rank_rules(message, rules), rules)

    records: dict[str, Any] = {}
    evidence: list[EvidenceItem] = []
    summary_parts: list[str] = []
    retrieval_assessment: dict[str, Any] = {}

    retrieval_mode = "policy_lookup"

    if matched_rules:
        records["matched_rules"] = matched_rules
        records["retrieval_strategy"] = "vector" if vector_matches else "keyword"
        policy_assessment = _assess_policy_retrieval(
            matched_rules,
            retrieval_strategy=records["retrieval_strategy"],
        )
        retrieval_assessment["policy"] = policy_assessment
        policy_summary = _summarize_rules(matched_rules)
        if policy_assessment["status"] == "partial":
            policy_summary = f"{policy_assessment['reason']} {policy_summary}"
        summary_parts.append(policy_summary)
        for rule in matched_rules:
            evidence.append(
                EvidenceItem(
                    source_type="company_rule",
                    title=rule["title"],
                    snippet=_snippet(rule.get("matched_chunk") or rule["content"]),
                    metadata={
                        "rule_id": rule["id"],
                        "category": rule["category"],
                        "matched_terms": rule.get("matched_terms", []),
                        "similarity": rule.get("similarity"),
                        "retrieval_status": policy_assessment["status"],
                        "freshness_status": rule.get("freshness_status"),
                        "latest_effective_date": rule.get("latest_effective_date"),
                        "version_source": rule.get("version_source"),
                        "promoted_from_rule_id": rule.get("promoted_from_rule_id"),
                    },
                )
            )
    else:
        retrieval_assessment["policy"] = _assess_policy_retrieval(
            matched_rules,
            retrieval_strategy="vector" if vector_matches else "keyword",
        )

    if wants_structure:
        departments = await _load_company_structure(db, session.company_id)
        selected_departments = _select_departments(message, departments)
        records["departments"] = selected_departments
        summary_parts.append(_summarize_structure(selected_departments))
        retrieval_mode = "mixed_lookup" if matched_rules else "structure_lookup"
        retrieval_assessment["structure"] = _build_retrieval_assessment(
            "enough" if selected_departments else "weak",
            (
                "Struktur organisasi yang relevan berhasil ditemukan."
                if selected_departments
                else "Struktur organisasi yang relevan belum ditemukan."
            ),
            department_count=len(selected_departments),
        )

        for department in selected_departments:
            evidence.append(
                EvidenceItem(
                    source_type="company_structure",
                    title=department["department_name"],
                    snippet=(
                        f"Head: {department['head_employee_name'] or 'belum ditetapkan'}"
                    ),
                    metadata={
                        "department_id": department["department_id"],
                        "parent_department_name": department["parent_department_name"],
                        "retrieval_status": retrieval_assessment["structure"]["status"],
                    },
                )
            )

    if not summary_parts:
        summary_parts.append(
            "Aku belum menemukan referensi policy atau struktur perusahaan yang cukup kuat."
        )
    if retrieval_assessment:
        records["retrieval_assessment"] = retrieval_assessment

    return CompanyAgentResult(
        retrieval_mode=retrieval_mode,
        summary=" ".join(summary_parts),
        records=records,
        evidence=evidence,
    )
