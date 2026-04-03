from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from sqlalchemy import text  # noqa: E402

from app.services.db import AsyncSessionLocal  # noqa: E402
from app.services.embeddings import generate_embedding, to_pgvector_literal  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync Gemini embeddings for intent_examples and agent_capabilities."
        )
    )
    parser.add_argument(
        "--company-id",
        required=False,
        help="Optional company id filter.",
    )
    return parser.parse_args()


def _ensure_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        value = parsed
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _build_capability_text(row: dict[str, object]) -> str:
    sample_queries = _ensure_string_list(row.get("sample_queries"))
    supported_intents = _ensure_string_list(row.get("supported_intents"))
    data_sources = _ensure_string_list(row.get("data_sources"))
    return " ".join(
        part
        for part in [
            str(row.get("title") or "").strip(),
            str(row.get("description") or "").strip(),
            " ".join(sample_queries),
            " ".join(supported_intents),
            " ".join(data_sources),
        ]
        if part
    ).strip()


async def _sync_intent_examples(company_id: str | None = None) -> int:
    filters = []
    params: dict[str, str] = {}
    if company_id:
        filters.append("(company_id IS NULL OR company_id = CAST(:company_id AS uuid))")
        params["company_id"] = company_id

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                f"""
                SELECT
                    id::text AS id,
                    example_text
                FROM intent_examples
                {where_clause}
                ORDER BY created_at ASC
                """
            ),
            params,
        )
        rows = result.mappings().all()
        updated = 0

        for row in rows:
            embedding = generate_embedding(
                str(row["example_text"]),
                task_type="RETRIEVAL_DOCUMENT",
            )
            if embedding is None:
                continue

            await db.execute(
                text(
                    """
                    UPDATE intent_examples
                    SET embedding = CAST(:embedding AS vector)
                    WHERE id = CAST(:id AS uuid)
                    """
                ),
                {
                    "id": row["id"],
                    "embedding": to_pgvector_literal(embedding),
                },
            )
            updated += 1

        await db.commit()
        return updated


async def _sync_agent_capabilities(company_id: str | None = None) -> int:
    filters = []
    params: dict[str, str] = {}
    if company_id:
        filters.append("(company_id IS NULL OR company_id = CAST(:company_id AS uuid))")
        params["company_id"] = company_id

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                f"""
                SELECT
                    id::text AS id,
                    title,
                    description,
                    supported_intents,
                    data_sources,
                    sample_queries
                FROM agent_capabilities
                {where_clause}
                ORDER BY created_at ASC
                """
            ),
            params,
        )
        rows = result.mappings().all()
        updated = 0

        for row in rows:
            combined_text = _build_capability_text(dict(row))
            if not combined_text:
                continue

            embedding = generate_embedding(
                combined_text,
                task_type="RETRIEVAL_DOCUMENT",
                title=str(row.get("title") or "").strip() or None,
            )
            if embedding is None:
                continue

            await db.execute(
                text(
                    """
                    UPDATE agent_capabilities
                    SET embedding = CAST(:embedding AS vector)
                    WHERE id = CAST(:id AS uuid)
                    """
                ),
                {
                    "id": row["id"],
                    "embedding": to_pgvector_literal(embedding),
                },
            )
            updated += 1

        await db.commit()
        return updated


async def main() -> None:
    args = parse_args()
    intent_examples_updated = await _sync_intent_examples(args.company_id)
    agent_capabilities_updated = await _sync_agent_capabilities(args.company_id)
    print(
        "Synced semantic routing embeddings: "
        f"intent_examples={intent_examples_updated}, "
        f"agent_capabilities={agent_capabilities_updated}."
    )


if __name__ == "__main__":
    asyncio.run(main())
