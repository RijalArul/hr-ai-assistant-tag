from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from app.agents import orchestrate_message  # noqa: E402
from app.models import AttachmentInput, OrchestratorRequest  # noqa: E402
from app.services.auth import authenticate_employee_by_email  # noqa: E402
from app.services.db import AsyncSessionLocal  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview the internal Phase 3 orchestrator flow for one employee."
    )
    parser.add_argument(
        "--email",
        required=True,
        help="Employee email used to bootstrap trusted session context.",
    )
    parser.add_argument(
        "--message",
        required=True,
        help="HR message that will be routed by the orchestrator.",
    )
    parser.add_argument(
        "--attachment",
        action="append",
        default=[],
        help="Optional attachment path. Repeat the flag for multiple files.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    attachments = [AttachmentInput(file_path=value) for value in args.attachment]
    payload = OrchestratorRequest(
        message=args.message,
        attachments=attachments,
    )

    async with AsyncSessionLocal() as db:
        session = await authenticate_employee_by_email(db, args.email.strip().lower())
        response = await orchestrate_message(db, session, payload)

    print(
        json.dumps(
            response.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
