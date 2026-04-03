from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from sqlalchemy import text  # noqa: E402

from app.services.db import AsyncSessionLocal  # noqa: E402
from app.services.embeddings import chunk_text, generate_embedding, to_pgvector_literal  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync company_rules into company_rule_chunks with embeddings."
    )
    parser.add_argument(
        "--company-id",
        required=False,
        help="Optional company id filter.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    async with AsyncSessionLocal() as db:
        filters = []
        params: dict[str, str] = {}
        if args.company_id:
            filters.append("company_id = CAST(:company_id AS uuid)")
            params["company_id"] = args.company_id

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        result = await db.execute(
            text(
                f"""
                SELECT
                    id::text AS id,
                    company_id::text AS company_id,
                    content
                FROM company_rules
                {where_clause}
                ORDER BY created_at ASC
                """
            ),
            params,
        )
        rules = result.mappings().all()

        synced_chunks = 0

        for rule in rules:
            chunks = chunk_text(rule["content"])
            rows_to_insert: list[dict[str, object]] = []

            for index, chunk in enumerate(chunks):
                embedding = generate_embedding(
                    chunk,
                    task_type="RETRIEVAL_DOCUMENT",
                )
                if embedding is None:
                    continue

                rows_to_insert.append(
                    {
                        "company_rule_id": rule["id"],
                        "company_id": rule["company_id"],
                        "chunk_index": index,
                        "content_chunk": chunk,
                        "embedding": to_pgvector_literal(embedding),
                        "metadata": '{"source":"sync_company_rule_chunks.py"}',
                    }
                )

            if not rows_to_insert:
                print(
                    f"Skipped rule {rule['id']} because no embeddings could be generated."
                )
                continue

            await db.execute(
                text(
                    """
                    DELETE FROM company_rule_chunks
                    WHERE company_rule_id = CAST(:company_rule_id AS uuid)
                    """
                ),
                {"company_rule_id": rule["id"]},
            )

            for row in rows_to_insert:
                await db.execute(
                    text(
                        """
                        INSERT INTO company_rule_chunks (
                            company_rule_id,
                            company_id,
                            chunk_index,
                            content_chunk,
                            embedding,
                            metadata
                        )
                        VALUES (
                            CAST(:company_rule_id AS uuid),
                            CAST(:company_id AS uuid),
                            :chunk_index,
                            :content_chunk,
                            CAST(:embedding AS vector),
                            CAST(:metadata AS jsonb)
                        )
                        """
                    ),
                    row,
                )
                synced_chunks += 1

        await db.commit()
        print(
            f"Synced {synced_chunks} company_rule_chunks across {len(rules)} company_rules."
        )


if __name__ == "__main__":
    asyncio.run(main())
