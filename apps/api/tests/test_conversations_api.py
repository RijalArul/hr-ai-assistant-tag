from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from app.agents.hr_data_agent import _resolve_relative_period
from app.agents.orchestrator import classify_intent
from app.core.security import SessionContext, get_current_session
from app.models import (
    CompanyAgentResult,
    ConversationIntent,
    EvidenceItem,
    HRDataAgentResult,
    IntentAssessment,
    SensitivityAssessment,
)
from app.agents.company_agent import run_company_agent
from app.services.db import get_db
from app.services.minimax import ProviderClassificationResult
from app.services.object_storage import StorageUploadResult
from app.services.semantic_router import (
    AgentCapabilityCandidate,
    AgentCapabilityResult,
    SemanticIntentCandidate,
    SemanticIntentResult,
)
from main import app
from shared import SensitivityLevel


class _FakeMappings:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def all(self) -> list[dict]:
        return self._rows

    def first(self) -> dict | None:
        return self._rows[0] if self._rows else None

    def one(self) -> dict:
        if not self._rows:
            raise AssertionError("Expected one row, but none were returned.")
        return self._rows[0]


class _FakeResult:
    def __init__(self, rows: list[dict] | None = None, scalar_value=None) -> None:
        self._rows = rows or []
        self._scalar_value = scalar_value

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._rows)

    def scalar_one(self):
        if self._scalar_value is None:
            raise AssertionError("Expected scalar value, but none was returned.")
        return self._scalar_value


class FakeAsyncSession:
    def __init__(self) -> None:
        self.conversations: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.actions: list[dict] = []
        self.action_logs: list[dict] = []
        self.action_deliveries: list[dict] = []
        self.commit_count = 0
        self.companies = {
            "00000000-0000-0000-0000-000000000001": {
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "PT Maju Bersama",
            }
        }
        self.employees = {
            "20000000-0000-0000-0000-000000000004": {
                "id": "20000000-0000-0000-0000-000000000004",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Fakhrul Muhammad Rijal",
                "email": "fakhrul.rijal@majubersama.id",
                "position": "Software Engineer",
                "department_name": "Engineering",
            }
        }
        self.payroll_records = [
            {
                "employee_id": "20000000-0000-0000-0000-000000000004",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "month": 3,
                "year": 2026,
                "basic_salary": 12000000,
                "allowances": 1500000,
                "gross_salary": 13500000,
                "deductions": 400000,
                "bpjs_kesehatan": 144000,
                "bpjs_ketenagakerjaan": 240000,
                "pph21": 700000,
                "net_pay": 12016000,
                "payment_status": "paid",
                "payment_date": "2026-03-27",
            }
        ]
        self.rules = [
            {
                "id": "60000000-0000-0000-0000-000000000001",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Payroll document follow-up",
                "description": "Generate and route payroll-related documents after a resolved conversation.",
                "trigger": "conversation_resolved",
                "intent_key": "payroll_document_request",
                "sensitivity_threshold": "medium",
                "is_enabled": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]
        self.rule_actions = {
            "60000000-0000-0000-0000-000000000001": [
                {
                    "rule_id": "60000000-0000-0000-0000-000000000001",
                    "action_type": "document_generation",
                    "title_template": "Generate salary slip",
                    "summary_template": "Prepare the requested salary slip and queue outbound delivery.",
                    "priority": "medium",
                    "delivery_channels": ["email", "in_app", "webhook"],
                    "payload_template": {
                        "document_type": "salary_slip",
                        "template_key": "payroll_salary_slip_v1",
                        "parameters": {
                            "month": 3,
                            "year": 2026,
                        },
                        "delivery_note": "Send the generated slip to the employee after verification.",
                    },
                }
            ]
        }

    async def execute(self, statement, params=None):
        query = " ".join(str(statement).lower().split())
        params = params or {}

        if "insert into conversations" in query:
            conversation_id = uuid4()
            now = datetime.now(UTC)
            row = {
                "id": str(conversation_id),
                "company_id": params["company_id"],
                "employee_id": params["employee_id"],
                "title": params.get("title"),
                "status": params["status"],
                "metadata": self._decode_json(params["metadata"]),
                "last_message_at": None,
                "created_at": now,
                "updated_at": now,
            }
            self.conversations[str(conversation_id)] = row
            return _FakeResult(scalar_value=conversation_id)

        if "from conversations c" in query:
            conversation = self.conversations.get(params["conversation_id"])
            if conversation is None:
                return _FakeResult()
            if conversation["company_id"] != params["company_id"]:
                return _FakeResult()
            if (
                "session_employee_id" in params
                and conversation["employee_id"] != params["session_employee_id"]
            ):
                return _FakeResult()
            return _FakeResult(rows=[conversation.copy()])

        if "insert into conversation_messages" in query:
            message_id = uuid4()
            now = datetime.now(UTC)
            row = {
                "id": str(message_id),
                "conversation_id": params["conversation_id"],
                "role": params["role"],
                "content": params["content"],
                "attachments": self._decode_json(params["attachments"]),
                "metadata": self._decode_json(params["metadata"]),
                "created_at": now,
            }
            self.messages.append(
                {
                    **row,
                    "company_id": params["company_id"],
                    "employee_id": params["employee_id"],
                }
            )
            return _FakeResult(rows=[row])

        if "from conversation_messages m" in query:
            rows = [
                {
                    "id": message["id"],
                    "conversation_id": message["conversation_id"],
                    "role": message["role"],
                    "content": message["content"],
                    "attachments": message["attachments"],
                    "metadata": message["metadata"],
                    "created_at": message["created_at"],
                }
                for message in self.messages
                if message["conversation_id"] == params["conversation_id"]
                and message["company_id"] == params["company_id"]
            ]
            rows.sort(key=lambda item: item["created_at"])
            return _FakeResult(rows=rows)

        if "update conversations" in query:
            conversation = self.conversations[params["conversation_id"]]
            if "title" in params:
                conversation["title"] = params["title"]
            if "conversation_status" in params:
                conversation["status"] = params["conversation_status"]
            if "metadata" in params:
                conversation["metadata"] = self._decode_json(params["metadata"])
            if "last_message_at" in params:
                conversation["last_message_at"] = params["last_message_at"]
            conversation["updated_at"] = datetime.now(UTC)
            return _FakeResult()

        if "from actions a" in query and "a.conversation_id = :conversation_id" in query:
            rows = [
                action.copy()
                for action in self.actions
                if action["conversation_id"] == params["conversation_id"]
                and action["company_id"] == params["company_id"]
                and (
                    "session_employee_id" not in params
                    or action["employee_id"] == params["session_employee_id"]
                )
            ]
            rows.sort(key=lambda item: item["created_at"], reverse=True)
            return _FakeResult(rows=rows)

        if "from actions a" in query and "a.id = :action_id" in query:
            for action in self.actions:
                if action["id"] != params["action_id"]:
                    continue
                if action["company_id"] != params["company_id"]:
                    continue
                if (
                    "session_employee_id" in params
                    and action["employee_id"] != params["session_employee_id"]
                ):
                    continue
                return _FakeResult(rows=[action.copy()])
            return _FakeResult()

        if (
            "select id from actions" in query
            and "rule_id = cast(:rule_id as uuid)" in query
        ):
            for action in reversed(self.actions):
                if action["company_id"] != params["company_id"]:
                    continue
                if action["employee_id"] != params["employee_id"]:
                    continue
                if action["conversation_id"] != params["conversation_id"]:
                    continue
                if action["rule_id"] != params["rule_id"]:
                    continue
                if action["type"] != params["action_type"]:
                    continue
                if action["status"] == params["cancelled_status"]:
                    continue
                return _FakeResult(rows=[{"id": action["id"]}])
            return _FakeResult()

        if "insert into actions" in query:
            action_id = uuid4()
            now = datetime.now(UTC)
            row = {
                "id": str(action_id),
                "company_id": params["company_id"],
                "employee_id": params["employee_id"],
                "conversation_id": params["conversation_id"],
                "rule_id": params["rule_id"],
                "type": params["action_type"],
                "title": params["title"],
                "summary": params["summary"],
                "status": params["action_status"],
                "priority": params["priority"],
                "sensitivity": params["sensitivity"],
                "delivery_channels": list(params["delivery_channels"]),
                "payload": self._decode_json(params["payload"]),
                "execution_result": None,
                "metadata": self._decode_json(params["metadata"]),
                "last_executed_at": None,
                "created_at": now,
                "updated_at": now,
            }
            self.actions.append(row)
            return _FakeResult(scalar_value=action_id)

        if "insert into action_logs" in query:
            log_id = uuid4()
            row = {
                "id": str(log_id),
                "action_id": params["action_id"],
                "event_name": params["event_name"],
                "status": params["action_status"],
                "message": params["message"],
                "metadata": self._decode_json(params["metadata"]),
                "created_at": datetime.now(UTC),
            }
            self.action_logs.append(
                {
                    **row,
                    "company_id": params["company_id"],
                }
            )
            return _FakeResult(rows=[row])

        if "update actions" in query:
            for action in self.actions:
                if action["id"] != params["action_id"]:
                    continue
                if action["company_id"] != params["company_id"]:
                    continue
                if "action_status" in params:
                    action["status"] = params["action_status"]
                if "delivery_channels" in params:
                    action["delivery_channels"] = list(params["delivery_channels"])
                if "execution_result" in params:
                    action["execution_result"] = self._decode_json(params["execution_result"])
                if "last_executed_at" in params:
                    action["last_executed_at"] = params["last_executed_at"]
                action["updated_at"] = datetime.now(UTC)
                break
            return _FakeResult()

        if (
            "from rules r" in query
            and "r.trigger = cast(:trigger as rule_trigger_enum)" in query
        ):
            rows = [
                rule.copy()
                for rule in self.rules
                if rule["company_id"] == params["company_id"]
                and rule["is_enabled"]
                and rule["trigger"] == params["trigger"]
                and rule["intent_key"] == params["intent_key"]
            ]
            return _FakeResult(rows=rows)

        if "from rule_actions ra" in query and "ra.rule_id = :rule_id" in query:
            return _FakeResult(rows=[row.copy() for row in self.rule_actions.get(params["rule_id"], [])])

        if (
            "select p.month, p.year from payroll p" in query
            and "limit 1" in query
        ):
            rows = [
                {
                    "month": record["month"],
                    "year": record["year"],
                }
                for record in self.payroll_records
                if record["employee_id"] == params["employee_id"]
                and record["company_id"] == params["company_id"]
                and ("year" not in params or record["year"] == params["year"])
            ]
            rows.sort(key=lambda item: (item["year"], item["month"]), reverse=True)
            return _FakeResult(rows=rows[:1])

        if (
            "select p.month, p.year, p.basic_salary" in query
            and "from payroll p" in query
            and "inner join employees e" in query
        ):
            rows = [
                {
                    "month": record["month"],
                    "year": record["year"],
                    "basic_salary": record["basic_salary"],
                    "allowances": record["allowances"],
                    "gross_salary": record["gross_salary"],
                    "deductions": record["deductions"],
                    "bpjs_kesehatan": record["bpjs_kesehatan"],
                    "bpjs_ketenagakerjaan": record["bpjs_ketenagakerjaan"],
                    "pph21": record["pph21"],
                    "net_pay": record["net_pay"],
                    "payment_status": record["payment_status"],
                    "payment_date": record["payment_date"],
                }
                for record in self.payroll_records
                if record["employee_id"] == params["employee_id"]
                and record["company_id"] == params["company_id"]
                and ("month" not in params or record["month"] == params["month"])
                and ("year" not in params or record["year"] == params["year"])
            ]
            rows.sort(key=lambda item: (item["year"], item["month"]), reverse=True)
            if "limit 1" in query:
                rows = rows[:1]
            elif "limit 3" in query:
                rows = rows[:3]
            return _FakeResult(rows=rows)

        if (
            "select c.name as company_name" in query
            and "from payroll p" in query
            and "inner join employees e" in query
        ):
            rows = []
            for record in self.payroll_records:
                if record["employee_id"] != params["employee_id"]:
                    continue
                if record["company_id"] != params["company_id"]:
                    continue
                if "month" in params and record["month"] != params["month"]:
                    continue
                if "year" in params and record["year"] != params["year"]:
                    continue
                employee = self.employees[record["employee_id"]]
                company = self.companies[record["company_id"]]
                rows.append(
                    {
                        "company_name": company["name"],
                        "employee_name": employee["name"],
                        "employee_email": employee["email"],
                        "position": employee["position"],
                        "department_name": employee["department_name"],
                        **record,
                    }
                )
            rows.sort(key=lambda item: (item["year"], item["month"]), reverse=True)
            return _FakeResult(rows=rows[:1])

        raise AssertionError(f"Unhandled query in fake session: {query}")

    async def commit(self) -> None:
        self.commit_count += 1

    @staticmethod
    def _decode_json(value):
        import json

        if isinstance(value, str):
            return json.loads(value)
        return value


@asynccontextmanager
async def _noop_lifespan(_app):
    yield


class ConversationsApiTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.db = FakeAsyncSession()
        self.session = SessionContext(
            employee_id="20000000-0000-0000-0000-000000000004",
            company_id="00000000-0000-0000-0000-000000000001",
            email="fakhrul.rijal@majubersama.id",
            role="employee",
        )
        self.original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = _noop_lifespan

        async def override_get_db():
            yield self.db

        async def override_get_current_session():
            return self.session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_session] = override_get_current_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        app.router.lifespan_context = self.original_lifespan

    def _create_conversation(self, *, title: str = "Test conversation") -> str:
        response = self.client.post(
            "/api/v1/conversations",
            json={
                "title": title,
                "metadata": {"source": "test"},
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_post_sensitive_message_marks_conversation_escalated(self) -> None:
        conversation_id = self._create_conversation(title="Sensitive test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Saya merasa dibully dan mengalami pelecehan di kantor.",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "sensitive_redirect")
        self.assertEqual(payload["conversation"]["status"], "escalated")
        self.assertEqual(payload["assistant_message"]["role"], "assistant")
        self.assertEqual(len(payload["conversation"]["messages"]), 2)

    def test_post_mixed_message_routes_to_hr_and_company_agents(self) -> None:
        conversation_id = self._create_conversation(title="Mixed route test")

        async def fake_hr_agent(*_args, **_kwargs):
            return HRDataAgentResult(
                topics=["time_off"],
                summary="Saldo cuti Anda tersisa 8 hari.",
                records={"time_off": {"balance_days": 8}},
                evidence=[
                    EvidenceItem(
                        source_type="hr_data",
                        title="Leave balance",
                        snippet="Sisa cuti 8 hari",
                    )
                ],
            )

        async def fake_company_agent(*_args, **_kwargs):
            return CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Carry over maksimal 5 hari sampai akhir Q1.",
                records={"matched_rules": [{"title": "Carry over leave"}]},
                evidence=[
                    EvidenceItem(
                        source_type="company_rule",
                        title="Carry over leave",
                        snippet="Maksimal 5 hari",
                    )
                ],
            )

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=AsyncMock(side_effect=fake_company_agent),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Berapa sisa cuti saya tahun ini dan apa aturan carry over?",
                    "attachments": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "mixed")
        self.assertIn("hr-data-agent", payload["orchestration"]["used_agents"])
        self.assertIn("company-agent", payload["orchestration"]["used_agents"])
        self.assertEqual(payload["conversation"]["status"], "active")

    def test_local_classifier_skips_minimax_for_clear_time_off_balance_request(self) -> None:
        conversation_id = self._create_conversation(title="Local classifier gate test")

        async def fake_hr_agent(*_args, **_kwargs):
            return HRDataAgentResult(
                topics=["time_off"],
                summary="Saldo cuti Anda tersisa 11 hari.",
                records={"time_off": {"balance_days": 11}},
                evidence=[],
            )

        minimax_mock = AsyncMock(return_value=None)
        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=minimax_mock,
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Cuti saya sisa berapa?",
                    "attachments": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["intent"]["primary_intent"], "time_off_balance")
        minimax_mock.assert_not_awaited()
        minimax_trace = next(
            step
            for step in payload["orchestration"]["trace"]
            if step["agent"] == "minimax-classifier"
        )
        self.assertEqual(minimax_trace["status"], "skipped")
        self.assertIn("local classifier", minimax_trace["detail"].lower())

    def test_attachment_context_can_drive_company_policy_route(self) -> None:
        conversation_id = self._create_conversation(title="Attachment route test")

        async def fake_company_agent(*_args, **_kwargs):
            return CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Aturan carry over cuti maksimal 5 hari.",
                records={"matched_rules": [{"title": "Carry over policy"}]},
                evidence=[],
            )

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=AsyncMock(side_effect=fake_company_agent),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Tolong cek lampiran ini",
                    "attachments": [
                        {
                            "file_name": "carry-over.txt",
                            "inline_text": "Aturan carry over cuti maksimal 5 hari sampai akhir kuartal pertama.",
                        }
                    ],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "company")
        self.assertIn("file-agent", payload["orchestration"]["used_agents"])

    def test_escalated_conversation_stays_escalated_after_follow_up(self) -> None:
        conversation_id = self._create_conversation(title="Escalation persistence test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            first_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Saya merasa dibully dan mengalami pelecehan di kantor.",
                    "attachments": [],
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(first_response.json()["conversation"]["status"], "escalated")

        async def fake_hr_agent(*_args, **_kwargs):
            return HRDataAgentResult(
                topics=["time_off"],
                summary="Saldo cuti Anda tersisa 8 hari.",
                records={"time_off": {"balance_days": 8}},
                evidence=[],
            )

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
        ):
            second_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Berapa sisa cuti saya tahun ini?",
                    "attachments": [],
                },
            )

        self.assertEqual(second_response.status_code, 200, second_response.text)
        self.assertEqual(second_response.json()["conversation"]["status"], "escalated")

    def test_employee_cannot_patch_conversation_to_escalated(self) -> None:
        conversation_id = self._create_conversation(title="Patch permission test")

        response = self.client.patch(
            f"/api/v1/conversations/{conversation_id}",
            json={
                "status": "escalated",
            },
        )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("cannot escalate", response.json()["detail"].lower())

    def test_get_conversation_actions_returns_linked_actions(self) -> None:
        conversation_id = self._create_conversation(title="Actions lookup test")
        self.db.actions.append(
            {
                "id": "50000000-0000-0000-0000-000000000001",
                "company_id": self.session.company_id,
                "employee_id": self.session.employee_id,
                "conversation_id": conversation_id,
                "rule_id": None,
                "type": "followup_chat",
                "title": "Send follow-up message",
                "summary": "Follow up on the conversation.",
                "status": "ready",
                "priority": "medium",
                "sensitivity": "low",
                "delivery_channels": ["in_app"],
                "payload": {
                    "type": "followup_chat",
                    "target_audience": "employee",
                    "message_template": "Halo, ini tindak lanjut dari percakapan sebelumnya.",
                    "scheduled_at": None,
                },
                "execution_result": None,
                "metadata": {},
                "last_executed_at": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )

        response = self.client.get(f"/api/v1/conversations/{conversation_id}/actions")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["conversation_id"], conversation_id)

    def test_payroll_document_request_creates_and_executes_payslip_action(self) -> None:
        conversation_id = self._create_conversation(title="Payslip generation test")

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.action_engine.upload_document_bytes",
                new=AsyncMock(
                    return_value=StorageUploadResult(
                        bucket="enclosed-pocket-eojsv7k0c",
                        object_key=(
                            "companies/00000000-0000-0000-0000-000000000001/"
                            "employees/20000000-0000-0000-0000-000000000004/"
                            "documents/payslips/2026/03/payslip-2026-03-fakhrul-muhammad-rijal.pdf"
                        ),
                        url="https://storage.example/payslip.pdf?signature=test",
                        expires_at="2026-04-03T12:00:00+00:00",
                        etag="etag-test",
                    )
                ),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Bisakah kamu tolong generate pdf, payslip saya?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["intent"]["primary_intent"], "payroll_document_request")
        self.assertEqual(len(payload["triggered_actions"]), 1)

        triggered_action = payload["triggered_actions"][0]
        self.assertEqual(triggered_action["type"], "document_generation")
        self.assertEqual(triggered_action["status"], "completed")
        self.assertIn("PDF payslip", payload["assistant_message"]["content"])

        document = triggered_action["execution_result"]["document"]
        self.assertEqual(document["mime_type"], "application/pdf")
        self.assertEqual(document["period"]["label"], "Maret 2026")
        self.assertEqual(document["storage_provider"], "s3_compatible")
        self.assertIn("object_key", document)
        self.assertIn("download_url", document)
        self.assertNotIn("content_base64", document)

        actions_response = self.client.get(f"/api/v1/conversations/{conversation_id}/actions")
        self.assertEqual(actions_response.status_code, 200, actions_response.text)
        actions_payload = actions_response.json()
        self.assertEqual(actions_payload["total"], 1)
        self.assertEqual(actions_payload["items"][0]["status"], "completed")
        self.assertEqual(
            actions_payload["items"][0]["execution_result"]["document"]["file_name"],
            document["file_name"],
        )

    def test_minimax_fallback_reason_is_exposed_in_trace(self) -> None:
        conversation_id = self._create_conversation(title="MiniMax fallback reason test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(
                return_value=ProviderClassificationResult(
                    fallback_reason="MiniMax returned HTTP 401. Unauthorized.",
                )
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Tolong bantu cek ini ya",
                    "attachments": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        minimax_trace = next(
            step
            for step in payload["orchestration"]["trace"]
            if step["agent"] == "minimax-classifier"
        )
        self.assertEqual(minimax_trace["status"], "fallback")
        self.assertIn("401", minimax_trace["detail"])

    def test_semantic_candidates_are_forwarded_to_minimax_classifier(self) -> None:
        conversation_id = self._create_conversation(title="Semantic routing judge test")

        async def fake_hr_agent(*_args, **_kwargs):
            return HRDataAgentResult(
                topics=["attendance"],
                summary="Rata-rata jam masuk kamu bulan lalu adalah 08:59 WIB.",
                records={"attendance": {"average_check_in": "08:59"}},
                evidence=[],
            )

        semantic_result = SemanticIntentResult(
            candidates=[
                SemanticIntentCandidate(
                    intent=ConversationIntent.ATTENDANCE_REVIEW,
                    example_text="jam masuk kantor saya bulan kemarin",
                    similarity=0.84,
                    source="vector",
                    weight=3,
                    company_specific=True,
                )
            ],
            retrieval_mode="vector",
        )
        minimax_mock = AsyncMock(
            return_value=ProviderClassificationResult(
                intent=IntentAssessment(
                    primary_intent=ConversationIntent.ATTENDANCE_REVIEW,
                    secondary_intents=[],
                    confidence=0.88,
                    matched_keywords=["semantic:attendance_review"],
                ),
                sensitivity=SensitivityAssessment(
                    level=SensitivityLevel.LOW,
                    matched_keywords=[],
                    rationale="Attendance review request.",
                ),
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=AsyncMock(return_value=semantic_result),
            ),
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=minimax_mock,
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Tolong bantu lihat pola kedatangan saya bulan lalu",
                    "attachments": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "hr_data")
        self.assertEqual(
            payload["orchestration"]["context"]["semantic_routing"]["retrieval_mode"],
            "vector",
        )
        self.assertEqual(
            minimax_mock.await_args.kwargs["candidate_intents"][0]["intent"],
            "attendance_review",
        )

    def test_agent_capabilities_are_forwarded_to_minimax_classifier(self) -> None:
        conversation_id = self._create_conversation(title="Agent capability judge test")

        async def fake_company_agent(*_args, **_kwargs):
            return CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Aturan carry over cuti maksimal 5 hari sampai akhir Q1.",
                records={"matched_rules": [{"title": "Carry over leave"}]},
                evidence=[],
            )

        agent_result = AgentCapabilityResult(
            candidates=[
                AgentCapabilityCandidate(
                    agent_key="company-agent",
                    title="Company Policy and Structure Agent",
                    description="Menangani company policy dan company structure.",
                    similarity=0.83,
                    source="vector",
                    execution_mode="policy_lookup",
                    requires_trusted_employee_context=False,
                    can_run_in_parallel=True,
                    supported_intents=["company_policy", "company_structure"],
                    data_sources=["company_rules", "departments"],
                    sample_queries=["apa aturan carry over cuti"],
                )
            ],
            retrieval_mode="vector",
        )
        minimax_mock = AsyncMock(
            return_value=ProviderClassificationResult(
                intent=IntentAssessment(
                    primary_intent=ConversationIntent.COMPANY_POLICY,
                    secondary_intents=[],
                    confidence=0.86,
                    matched_keywords=["semantic:company_policy"],
                ),
                sensitivity=SensitivityAssessment(
                    level=SensitivityLevel.LOW,
                    matched_keywords=[],
                    rationale="Company policy request.",
                ),
                chosen_agents=["company-agent"],
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=AsyncMock(return_value=agent_result),
            ),
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=minimax_mock,
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=AsyncMock(side_effect=fake_company_agent),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Tolong bantu cek handbook perusahaan terbaru",
                    "attachments": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "company")
        self.assertEqual(
            minimax_mock.await_args.kwargs["candidate_agents"][0]["agent_key"],
            "company-agent",
        )

    def test_agent_capabilities_can_promote_route_when_classifier_is_out_of_scope(self) -> None:
        conversation_id = self._create_conversation(title="Agent capability fallback test")

        async def fake_company_agent(*_args, **_kwargs):
            return CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Handbook perusahaan berisi aturan umum kerja dan cuti.",
                records={"matched_rules": [{"title": "Employee handbook"}]},
                evidence=[],
            )

        agent_result = AgentCapabilityResult(
            candidates=[
                AgentCapabilityCandidate(
                    agent_key="company-agent",
                    title="Company Policy and Structure Agent",
                    description="Menangani company policy dan company structure.",
                    similarity=0.88,
                    source="vector",
                    execution_mode="policy_lookup",
                    requires_trusted_employee_context=False,
                    can_run_in_parallel=True,
                    supported_intents=["company_policy", "company_structure"],
                    data_sources=["company_rules", "departments"],
                    sample_queries=["tolong cek handbook perusahaan terbaru"],
                )
            ],
            retrieval_mode="vector",
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=AsyncMock(return_value=agent_result),
            ),
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(
                    return_value=ProviderClassificationResult(
                        fallback_reason="MiniMax network error: timed out",
                    )
                ),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=AsyncMock(side_effect=fake_company_agent),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Tolong bantu cek handbook perusahaan terbaru",
                    "attachments": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "company")
        self.assertEqual(
            payload["orchestration"]["intent"]["primary_intent"],
            "company_policy",
        )
        self.assertEqual(
            payload["orchestration"]["context"]["agent_routing"]["planned_agents"],
            ["company-agent"],
        )
        self.assertIn(
            "intent_alignment_reason",
            payload["orchestration"]["context"]["agent_routing"],
        )
        self.assertTrue(
            payload["orchestration"]["context"]["metrics"]["capability_route_promotion_used"]
        )

    def test_semantic_fallback_can_replace_out_of_scope_when_provider_is_unavailable(self) -> None:
        conversation_id = self._create_conversation(title="Semantic fallback test")

        async def fake_hr_agent(*_args, **_kwargs):
            return HRDataAgentResult(
                topics=["time_off"],
                summary="Saldo cuti Anda tersisa 11 hari.",
                records={"time_off": {"balance_days": 11}},
                evidence=[],
            )

        semantic_result = SemanticIntentResult(
            candidates=[
                SemanticIntentCandidate(
                    intent=ConversationIntent.TIME_OFF_BALANCE,
                    example_text="cuti saya sisa berapa",
                    similarity=0.86,
                    source="vector",
                    weight=3,
                    company_specific=True,
                )
            ],
            retrieval_mode="vector",
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=AsyncMock(return_value=semantic_result),
            ),
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(
                    return_value=ProviderClassificationResult(
                        fallback_reason="Remote providers are disabled by configuration.",
                    )
                ),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Boleh bantu cek hak libur saya yang masih ada?",
                    "attachments": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "hr_data")
        self.assertEqual(
            payload["orchestration"]["intent"]["primary_intent"],
            "time_off_balance",
        )
        self.assertEqual(
            payload["orchestration"]["context"]["metrics"]["classifier_source"],
            "semantic_retrieval",
        )
        self.assertTrue(
            payload["orchestration"]["context"]["metrics"]["semantic_fallback_used"]
        )

    def test_local_classifier_routes_month_ago_check_in_question_to_attendance(self) -> None:
        assessment = classify_intent(
            "Saya minta data jam masuk kantor saya, brdasrkan bulan kemarin",
        )

        self.assertEqual(assessment.primary_intent.value, "attendance_review")
        self.assertGreaterEqual(assessment.confidence, 0.9)

    async def test_company_agent_summary_keeps_full_policy_content(self) -> None:
        full_policy = (
            "Karyawan tetap berhak atas 12 hari cuti tahunan per tahun kalender. "
            "Cuti tahunan dapat diambil setelah melewati masa percobaan 3 bulan. "
            "Pengajuan cuti harus dilakukan minimal 3 hari kerja sebelum tanggal "
            "cuti dimulai dan persetujuan atasan wajib diperoleh sebelum karyawan "
            "tidak masuk bekerja."
        )

        matched_rule = {
            "id": "rule-1",
            "title": "Kebijakan Cuti Tahunan",
            "category": "leave",
            "content": full_policy,
            "effective_date": "2024-01-01",
            "is_active": True,
            "matched_terms": ["cuti tahunan"],
        }

        with (
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=AsyncMock(return_value=[matched_rule]),
            ),
            patch(
                "app.agents.company_agent._rank_rules",
                return_value=[matched_rule],
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Apa aturan cuti tahunan di perusahaan?",
            )

        self.assertIn(full_policy, result.summary)
        self.assertNotIn("...", result.summary)

    def test_relative_period_helper_supports_relative_phrases(self) -> None:
        current_month, current_year = _resolve_relative_period(
            "Tolong kirim payslip saya bulan ini",
            now=datetime(2026, 4, 3, tzinfo=UTC),
        )
        self.assertEqual((current_month, current_year), (4, 2026))

        previous_month, previous_year = _resolve_relative_period(
            "Saya mau lihat payroll bulan lalu",
            now=datetime(2026, 1, 5, tzinfo=UTC),
        )
        self.assertEqual((previous_month, previous_year), (12, 2025))

        previous_month_alias, previous_year_alias = _resolve_relative_period(
            "Saya minta data absensi berdasarkan bulan kemarin",
            now=datetime(2026, 4, 3, tzinfo=UTC),
        )
        self.assertEqual((previous_month_alias, previous_year_alias), (3, 2026))

    def test_classifier_override_can_shift_local_intent(self) -> None:
        assessment = classify_intent(
            "Saya butuh slip bulan ini",
            {
                "intent": {
                    "payroll_document_request": [
                        {"keyword": "slip bulan ini", "weight": 4},
                    ]
                },
                "sensitivity": {},
            },
        )

        self.assertEqual(assessment.primary_intent.value, "payroll_document_request")
        self.assertGreaterEqual(assessment.confidence, 0.78)
