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

from app.agents.hr_data_agent import _resolve_relative_period, run_hr_data_agent
from app.agents.orchestrator import _build_fallback_ladder, classify_intent, orchestrate_message
from app.core.security import SessionContext, get_current_session
from app.models import (
    AgentRoute,
    CompanyAgentResult,
    ConversationRequestCategory,
    ConversationIntent,
    EvidenceItem,
    HRDataAgentResult,
    IntentAssessment,
    OrchestratorRequest,
    ResponseMode,
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
    def __init__(self, rows: list[dict] | None = None, scalar_value=None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self._scalar_value = scalar_value
        self.rowcount = rowcount

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
            },
            {
                "employee_id": "20000000-0000-0000-0000-000000000004",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "month": 2,
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
                "payment_date": "2026-02-25",
            },
            {
                "employee_id": "20000000-0000-0000-0000-000000000004",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "month": 1,
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
                "payment_date": "2026-01-28",
            }
        ]
        self.company_rules: list[dict] = []
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
            },
            {
                "id": "60000000-0000-0000-0000-000000000002",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Unsafe workplace escalation",
                "description": "Create a manual-review escalation task when an unsafe workplace report is detected.",
                "trigger": "sensitivity_detected",
                "intent_key": "sensitive_unsafe_workplace_case",
                "sensitivity_threshold": "high",
                "is_enabled": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
            {
                "id": "60000000-0000-0000-0000-000000000003",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Harassment escalation",
                "description": "Create a manual-review escalation task when harassment or discrimination is reported.",
                "trigger": "sensitivity_detected",
                "intent_key": "sensitive_harassment_case",
                "sensitivity_threshold": "high",
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
            ],
            "60000000-0000-0000-0000-000000000002": [
                {
                    "rule_id": "60000000-0000-0000-0000-000000000002",
                    "action_type": "escalation",
                    "title_template": "Open unsafe workplace review",
                    "summary_template": "Sensitive workplace safety concern detected and queued for manual HR review.",
                    "priority": "high",
                    "delivery_channels": ["manual_review"],
                    "payload_template": {
                        "reason": "Unsafe workplace report requires manual review.",
                        "target_role": "hr_admin",
                        "escalation_level": 2,
                        "note": "Review the report and triage the safest next step before any outbound follow-up.",
                    },
                }
            ],
            "60000000-0000-0000-0000-000000000003": [
                {
                    "rule_id": "60000000-0000-0000-0000-000000000003",
                    "action_type": "escalation",
                    "title_template": "Open harassment report review",
                    "summary_template": "Sensitive harassment or discrimination report detected and queued for manual HR review.",
                    "priority": "high",
                    "delivery_channels": ["manual_review"],
                    "payload_template": {
                        "reason": "Harassment or discrimination report requires manual review.",
                        "target_role": "hr_admin",
                        "escalation_level": 3,
                        "note": "Review the report, preserve confidentiality, and decide the formal handling path.",
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
            updated = 0
            for action in self.actions:
                if action["id"] != params["action_id"]:
                    continue
                if action["company_id"] != params["company_id"]:
                    continue
                # Honour atomic-claim status constraint: only update when the
                # action is in one of the permitted statuses (pending / ready).
                if "pending" in params and "ready" in params:
                    if action["status"] not in {params["pending"], params["ready"]}:
                        break
                if "action_status" in params:
                    action["status"] = params["action_status"]
                if "delivery_channels" in params:
                    action["delivery_channels"] = list(params["delivery_channels"])
                if "execution_result" in params:
                    action["execution_result"] = self._decode_json(params["execution_result"])
                if "last_executed_at" in params:
                    action["last_executed_at"] = params["last_executed_at"]
                action["updated_at"] = datetime.now(UTC)
                updated = 1
                break
            return _FakeResult(rowcount=updated)

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

        if (
            "from company_rules" in query
            and "where company_id = cast(:company_id as uuid)" in query
        ):
            rows = [
                rule.copy()
                for rule in self.company_rules
                if rule["company_id"] == params["company_id"]
                and rule.get("is_active", True)
            ]
            return _FakeResult(rows=rows)

        # Employee profile query (personal_profile intent path).
        # Returns empty so the HR-data agent skips profile data gracefully.
        if (
            "select e.id::text as employee_id" in query
            and "from employees e" in query
            and "left join departments d" in query
        ):
            return _FakeResult(rows=[])

        # Time-off balance query (time_off_request_status intent path).
        # Returns empty so the HR-data agent skips leave-balance data gracefully.
        if "from time_offs t" in query and "inner join employees e" in query:
            return _FakeResult(rows=[])

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

    def test_post_harassment_report_creates_manual_review_action(self) -> None:
        conversation_id = self._create_conversation(title="Harassment report test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Saya ingin melaporkan pelecehan dan diskriminasi dari rekan kerja di kantor.",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "sensitive_redirect")
        self.assertEqual(
            payload["orchestration"]["context"]["sensitive_handling"]["case_key"],
            "harassment_discrimination",
        )
        self.assertEqual(
            payload["orchestration"]["context"]["sensitive_handling"]["action_policy"],
            "create_task",
        )
        self.assertEqual(
            payload["orchestration"]["context"]["sensitive_handling"]["review_policy"],
            "mandatory_manual_review",
        )
        self.assertEqual(len(payload["triggered_actions"]), 1)
        triggered_action = payload["triggered_actions"][0]
        self.assertEqual(triggered_action["type"], "escalation")
        self.assertEqual(triggered_action["delivery_channels"], ["manual_review"])
        self.assertEqual(triggered_action["status"], "pending")
        self.assertIn("action tindak lanjut", payload["assistant_message"]["content"].lower())

    def test_post_resignation_guidance_does_not_create_action(self) -> None:
        conversation_id = self._create_conversation(title="Resignation guidance test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Saya sedang mempertimbangkan resign bulan depan dan masih bingung langkah amannya.",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "sensitive_redirect")
        self.assertEqual(
            payload["orchestration"]["context"]["sensitive_handling"]["case_key"],
            "resignation_intention",
        )
        self.assertEqual(
            payload["orchestration"]["context"]["sensitive_handling"]["action_policy"],
            "guidance_only",
        )
        self.assertEqual(payload["triggered_actions"], [])

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

    def test_deterministic_hr_query_ignores_provider_mixed_agent_widening(self) -> None:
        conversation_id = self._create_conversation(title="Deterministic boundary test")

        async def fake_hr_agent(*_args, **_kwargs):
            return HRDataAgentResult(
                topics=["payroll"],
                summary="Payroll terbaru yang ditemukan adalah periode Maret 2026 dengan net pay Rp12.016.000.",
                records={"payroll": [{"month": 3, "year": 2026, "net_pay": 12016000}]},
                evidence=[],
            )

        company_mock = AsyncMock()
        with (
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(True, "Forced provider path for deterministic-boundary regression test."),
            ),
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(
                    return_value=ProviderClassificationResult(
                        intent=IntentAssessment(
                            primary_intent=ConversationIntent.PAYROLL_INFO,
                            secondary_intents=[],
                            confidence=0.93,
                            matched_keywords=["salary"],
                        ),
                        sensitivity=SensitivityAssessment(
                            level=SensitivityLevel.LOW,
                            matched_keywords=[],
                            rationale="Structured payroll request.",
                        ),
                        chosen_agents=["hr-data-agent", "company-agent"],
                    )
                ),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=company_mock,
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "What is my salary this month?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["route"], "hr_data")
        self.assertEqual(
            payload["orchestration"]["context"]["query_policy"]["boundary_mode"],
            "must_be_deterministic",
        )
        self.assertIn(
            "deterministic boundary",
            payload["orchestration"]["context"]["agent_routing"]["planning_reason"].lower(),
        )
        company_mock.assert_not_awaited()

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

    def test_referential_follow_up_uses_conversation_grounding(self) -> None:
        conversation_id = self._create_conversation(title="Conversation grounding test")

        async def fake_company_agent(*_args, **_kwargs):
            return CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Aturan carry over cuti berlaku sampai akhir kuartal pertama.",
                records={"matched_rules": [{"title": "Carry over leave policy"}]},
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
            first_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Apa aturan carry over cuti?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )
            second_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Yang tadi berlaku sampai kapan?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        payload = second_response.json()
        self.assertEqual(payload["orchestration"]["route"], "company")
        self.assertTrue(payload["orchestration"]["context"]["conversation_grounding"]["used"])
        self.assertGreaterEqual(
            payload["orchestration"]["context"]["conversation_grounding"]["history_items"],
            2,
        )

    def test_short_standalone_query_does_not_force_conversation_grounding(self) -> None:
        conversation_id = self._create_conversation(title="Standalone query grounding test")

        async def fake_company_agent(*_args, **_kwargs):
            return CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Aturan carry over cuti berlaku sampai akhir kuartal pertama.",
                records={"matched_rules": [{"title": "Carry over leave policy"}]},
                evidence=[],
            )

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
                "app.agents.orchestrator.run_company_agent",
                new=AsyncMock(side_effect=fake_company_agent),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
        ):
            first_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Apa aturan carry over cuti?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )
            second_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Berapa sisa cuti saya?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        payload = second_response.json()
        self.assertEqual(payload["orchestration"]["route"], "hr_data")
        self.assertFalse(payload["orchestration"]["context"]["conversation_grounding"]["used"])

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

    def test_hr_admin_can_complete_action_after_manual_in_progress_claim(self) -> None:
        conversation_id = self._create_conversation(title="Manual claim execution test")
        self.session = SessionContext(
            employee_id="20000000-0000-0000-0000-000000000004",
            company_id="00000000-0000-0000-0000-000000000001",
            email="hr.admin@majubersama.id",
            role="hr_admin",
        )
        self.db.actions.append(
            {
                "id": "50000000-0000-0000-0000-000000000099",
                "company_id": self.session.company_id,
                "employee_id": "20000000-0000-0000-0000-000000000004",
                "conversation_id": conversation_id,
                "rule_id": None,
                "type": "followup_chat",
                "title": "Manual HR follow-up",
                "summary": "HR needs to review and close this case.",
                "status": "ready",
                "priority": "high",
                "sensitivity": "low",
                "delivery_channels": ["in_app"],
                "payload": {
                    "type": "followup_chat",
                    "target_audience": "employee",
                    "message_template": "HR follow-up is ready.",
                    "scheduled_at": None,
                },
                "execution_result": None,
                "metadata": {},
                "last_executed_at": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )

        claim_response = self.client.patch(
            "/api/v1/actions/50000000-0000-0000-0000-000000000099",
            json={"status": "in_progress"},
        )
        self.assertEqual(claim_response.status_code, 200, claim_response.text)
        self.assertEqual(claim_response.json()["status"], "in_progress")

        execute_response = self.client.post(
            "/api/v1/actions/50000000-0000-0000-0000-000000000099/execute",
            json={
                "trigger_delivery": False,
                "executor_note": "Completed after manual HR review.",
            },
        )
        self.assertEqual(execute_response.status_code, 200, execute_response.text)
        payload = execute_response.json()
        self.assertEqual(payload["action"]["status"], "completed")
        self.assertEqual(payload["execution_log"]["status"], "completed")

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

    def test_exploratory_payslip_question_does_not_trigger_action(self) -> None:
        conversation_id = self._create_conversation(title="Payslip exploratory gate test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Apakah saya bisa minta payslip saya bulan ini?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["intent"]["primary_intent"], "payroll_document_request")
        self.assertEqual(payload["triggered_actions"], [])
        self.assertFalse(payload["orchestration"]["context"]["action_gate"]["should_trigger"])
        self.assertEqual(
            payload["orchestration"]["context"]["action_gate"]["mode"],
            "exploratory_request",
        )
        self.assertIn(
            "minta secara eksplisit",
            payload["assistant_message"]["content"].lower(),
        )

        actions_response = self.client.get(f"/api/v1/conversations/{conversation_id}/actions")
        self.assertEqual(actions_response.status_code, 200, actions_response.text)
        self.assertEqual(actions_response.json()["total"], 0)

    def test_how_to_download_payslip_question_does_not_trigger_action(self) -> None:
        conversation_id = self._create_conversation(title="Payslip how-to gate test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Bagaimana cara download payslip saya bulan ini?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["orchestration"]["intent"]["primary_intent"], "payroll_document_request")
        self.assertEqual(payload["triggered_actions"], [])
        self.assertFalse(payload["orchestration"]["context"]["action_gate"]["should_trigger"])
        self.assertEqual(
            payload["orchestration"]["context"]["action_gate"]["mode"],
            "exploratory_request",
        )

    def test_payroll_document_request_for_unavailable_period_stays_graceful(self) -> None:
        conversation_id = self._create_conversation(title="Payslip unavailable period test")

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Bisakah kamu tolong generate pdf, payslip saya April 2026?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload["triggered_actions"]), 1)
        triggered_action = payload["triggered_actions"][0]
        # The in-memory ActionResponse appended in the except path still holds
        # the pre-attempt status (pending). The persisted DB record gets
        # transitioned to FAILED by the I.10 retry-hardening logic.
        self.assertEqual(triggered_action["status"], "pending")
        self.assertIsNone(triggered_action["execution_result"])
        self.assertIn(
            "payroll untuk periode yang diminta belum tersedia",
            payload["assistant_message"]["content"].lower(),
        )
        self.assertEqual(
            payload["orchestration"]["context"]["auto_execution_issues"][0]["action_type"],
            "document_generation",
        )
        self.assertIn(
            "Payroll record not found",
            payload["orchestration"]["context"]["auto_execution_issues"][0]["detail"],
        )

        actions_response = self.client.get(f"/api/v1/conversations/{conversation_id}/actions")
        self.assertEqual(actions_response.status_code, 200, actions_response.text)
        actions_payload = actions_response.json()
        self.assertEqual(actions_payload["total"], 1)
        # DB record is now FAILED (I.10: failed auto-executions mark the action
        # as failed so they are NOT silently retried on the next message).
        self.assertEqual(actions_payload["items"][0]["status"], "failed")

    def test_repeated_payslip_request_reuses_completed_action_without_reexecution(self) -> None:
        conversation_id = self._create_conversation(title="Payslip idempotency test")

        upload_mock = AsyncMock(
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
        )

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.action_engine.upload_document_bytes",
                new=upload_mock,
            ),
        ):
            first_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Bisakah kamu tolong generate pdf, payslip saya?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )
            second_response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Bisakah kamu tolong generate pdf, payslip saya?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.text)
        self.assertEqual(second_response.status_code, 200, second_response.text)
        self.assertEqual(upload_mock.await_count, 1)

        first_payload = first_response.json()
        second_payload = second_response.json()
        self.assertEqual(len(first_payload["triggered_actions"]), 1)
        self.assertEqual(len(second_payload["triggered_actions"]), 1)
        self.assertEqual(
            second_payload["triggered_actions"][0]["id"],
            first_payload["triggered_actions"][0]["id"],
        )
        self.assertEqual(second_payload["triggered_actions"][0]["status"], "completed")

        actions_response = self.client.get(f"/api/v1/conversations/{conversation_id}/actions")
        self.assertEqual(actions_response.status_code, 200, actions_response.text)
        actions_payload = actions_response.json()
        self.assertEqual(actions_payload["total"], 1)

    def test_payroll_question_for_current_month_uses_latest_available_context(self) -> None:
        conversation_id = self._create_conversation(title="Payroll current month fallback test")

        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 4, 3, tzinfo=tz or UTC)

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.agents.hr_data_agent.datetime",
                _FixedDateTime,
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Why my salary this month is lower ?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        content = payload["assistant_message"]["content"]
        self.assertEqual(payload["orchestration"]["route"], "hr_data")
        self.assertIn("belum menemukan payroll untuk periode April 2026", content)
        self.assertIn("Payroll terbaru yang tersedia adalah periode Maret 2026", content)
        self.assertIn("tidak lebih rendah", content)
        self.assertEqual(
            payload["orchestration"]["context"]["retrieval_assessment"]["hr_data"]["payroll"]["status"],
            "partial",
        )
        self.assertEqual(
            payload["orchestration"]["context"]["fallback_ladder"][-1]["stage"],
            "answer_completeness",
        )
        self.assertEqual(
            payload["orchestration"]["context"]["fallback_ladder"][-1]["status"],
            "partial_answer",
        )

    def test_fallback_ladder_uses_answer_completeness_stage_name(self) -> None:
        ladder = _build_fallback_ladder(
            query_policy={
                "query_class": "temporal_lookup",
                "boundary_mode": "must_be_deterministic",
            },
            conversation_grounding={
                "used": False,
                "reason": "Conversation grounding was not needed for this message.",
                "history_items": 0,
            },
            classifier_source="local",
            provider_status="skipped",
            provider_reason="Local classifier result was used directly.",
            semantic_result=SemanticIntentResult(
                candidates=[],
                retrieval_mode="empty",
                fallback_reason="No semantic candidates.",
            ),
            agent_capability_result=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="empty",
                fallback_reason="No agent candidates.",
            ),
            retrieval_assessment={
                "hr_data": {
                    "payroll": {
                        "status": "partial",
                        "reason": "Fallback payroll answer used latest available period.",
                    }
                }
            },
        )

        self.assertEqual(ladder[-1]["stage"], "answer_completeness")
        self.assertEqual(ladder[-1]["status"], "partial_answer")

    def test_payroll_question_explains_drop_against_previous_period(self) -> None:
        conversation_id = self._create_conversation(title="Payroll comparison explanation test")
        self.db.payroll_records[0]["net_pay"] = 11500000
        self.db.payroll_records[0]["deductions"] = 916000

        with patch(
            "app.agents.orchestrator.classify_with_minimax",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Why my salary in March 2026 is lower ?",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        content = payload["assistant_message"]["content"]
        self.assertIn("periode Maret 2026", content)
        self.assertIn("net pay turun", content)
        self.assertIn("potongan naik", content)

    async def test_hr_data_agent_early_month_attendance_average_uses_last_complete_period(self) -> None:
        class _FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 4, 3, tzinfo=tz or UTC)

        current_month_records = [
            {
                "attendance_date": "2026-04-02",
                "check_in": "09:12:00",
                "check_out": "18:01:00",
                "status": "present",
            },
            {
                "attendance_date": "2026-04-01",
                "check_in": "09:05:00",
                "check_out": "17:55:00",
                "status": "present",
            },
        ]
        last_complete_month_records = [
            {
                "attendance_date": "2026-03-31",
                "check_in": "08:58:00",
                "check_out": "17:57:00",
                "status": "present",
            },
            {
                "attendance_date": "2026-03-30",
                "check_in": "08:56:00",
                "check_out": "17:59:00",
                "status": "present",
            },
            {
                "attendance_date": "2026-03-27",
                "check_in": "09:01:00",
                "check_out": "18:02:00",
                "status": "present",
            },
            {
                "attendance_date": "2026-03-26",
                "check_in": "08:59:00",
                "check_out": "17:58:00",
                "status": "present",
            },
        ]

        with (
            patch("app.agents.hr_data_agent.datetime", _FixedDateTime),
            patch(
                "app.agents.hr_data_agent._get_attendance_records",
                new=AsyncMock(
                    side_effect=[current_month_records, last_complete_month_records]
                ),
            ),
        ):
            result = await run_hr_data_agent(
                self.db,
                self.session,
                "Rata-rata jam masuk saya bulan ini berapa?",
                ConversationIntent.ATTENDANCE_REVIEW,
            )

        assessment = result.records["retrieval_assessment"]["attendance"]
        self.assertEqual(assessment["status"], "partial")
        self.assertEqual(assessment["fallback_mode"], "last_complete_period")
        self.assertEqual(assessment["fallback_period_label"], "Maret 2026")
        self.assertIn("periode lengkap terakhir Maret 2026", result.summary)

    async def test_hr_data_agent_referential_follow_up_inherits_recent_period(self) -> None:
        payroll_mock = AsyncMock(
            return_value=[
                {
                    "month": 3,
                    "year": 2026,
                    "gross_salary": 13500000,
                    "net_pay": 12016000,
                    "payment_status": "paid",
                }
            ]
        )

        with patch(
            "app.agents.hr_data_agent._get_payroll_records",
            new=payroll_mock,
        ):
            result = await run_hr_data_agent(
                self.db,
                self.session,
                "Yang tadi potongan apa saja?",
                ConversationIntent.PAYROLL_INFO,
                conversation_history=[
                    {
                        "role": "user",
                        "content": "Kenapa gaji Maret 2026 saya lebih rendah?",
                    },
                    {
                        "role": "assistant",
                        "content": "Net pay Maret 2026 lebih rendah karena potongan naik.",
                    },
                ],
            )

        self.assertEqual(payroll_mock.await_count, 1)
        self.assertEqual(payroll_mock.await_args.args[2:], (3, 2026))
        self.assertIn("Maret 2026", result.summary)

    async def test_hr_data_agent_explicit_period_overrides_inherited_history_period(self) -> None:
        payroll_mock = AsyncMock(
            return_value=[
                {
                    "month": 4,
                    "year": 2026,
                    "gross_salary": 13650000,
                    "net_pay": 12100000,
                    "payment_status": "paid",
                }
            ]
        )

        with patch(
            "app.agents.hr_data_agent._get_payroll_records",
            new=payroll_mock,
        ):
            result = await run_hr_data_agent(
                self.db,
                self.session,
                "Yang tadi tapi untuk April 2026 bagaimana?",
                ConversationIntent.PAYROLL_INFO,
                conversation_history=[
                    {
                        "role": "user",
                        "content": "Kenapa gaji Maret 2026 saya lebih rendah?",
                    },
                    {
                        "role": "assistant",
                        "content": "Net pay Maret 2026 lebih rendah karena potongan naik.",
                    },
                ],
            )

        self.assertEqual(payroll_mock.await_count, 1)
        self.assertEqual(payroll_mock.await_args.args[2:], (4, 2026))
        self.assertIn("April 2026", result.summary)

    async def test_company_agent_marks_limited_policy_match_as_partial(self) -> None:
        with (
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=AsyncMock(
                    return_value=[
                        {
                            "id": "rule-1",
                            "title": "Remote Work Guideline",
                            "category": "work_arrangement",
                            "content": "Remote work is allowed for approved hybrid schedules only.",
                            "effective_date": "2026-01-01",
                            "is_active": True,
                        }
                    ]
                ),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Apa aturan remote?",
            )

        assessment = result.records["retrieval_assessment"]["policy"]
        self.assertEqual(assessment["status"], "partial")
        self.assertIn("bersifat awal", result.summary.lower())

    async def test_company_agent_can_reason_about_mental_health_reimbursement(self) -> None:
        matched_rule = {
            "id": "rule-benefit-mental",
            "title": "Kebijakan Reimbursement Mental Health",
            "category": "benefit",
            "content": (
                "Perusahaan memberikan reimbursement konsultasi psikolog online maksimal "
                "Rp 300.000 per sesi. Klaim wajib dilampiri invoice, receipt, dan bukti bayar."
            ),
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["psikolog", "reimburse"],
            "ranking_score": 8,
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
                "Saya tadi ke psikolog online 150 ribu, bisa reimburse nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "eligible")
        self.assertEqual(reasoning["amount_requested"], 150000)
        self.assertEqual(reasoning["estimated_maximum_reimbursement"], 150000)
        self.assertIn("invoice", reasoning["required_documents"])
        self.assertIn("receipt", reasoning["required_documents"])
        self.assertIn("kemungkinan eligible", result.summary.lower())

    async def test_company_agent_reasoning_caps_optical_reimbursement_at_policy_limit(self) -> None:
        matched_rule = {
            "id": "rule-benefit-optical",
            "title": "Kebijakan Reimbursement Optical",
            "category": "benefit",
            "content": (
                "Reimbursement kacamata maksimal Rp 750.000 per tahun kalender. "
                "Klaim wajib dilampiri kuitansi atau invoice pembelian."
            ),
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["kacamata", "reimburse"],
            "ranking_score": 9,
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
                "Kalau beli kacamata 1,2 juta bisa reimburse nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "eligible")
        self.assertEqual(reasoning["amount_requested"], 1200000)
        self.assertEqual(reasoning["estimated_maximum_reimbursement"], 750000)
        self.assertIn("750.000", result.summary)

    async def test_company_agent_reasoning_marks_excluded_wellness_subscription_as_not_eligible(self) -> None:
        matched_rule = {
            "id": "rule-benefit-mental",
            "title": "Kebijakan Reimbursement Mental Health",
            "category": "benefit",
            "content": (
                "Perusahaan memberikan reimbursement konsultasi psikolog online maksimal "
                "Rp 300.000 per sesi. Klaim wajib dilampiri invoice, receipt, dan bukti bayar. "
                "Reimbursement tidak mencakup subscription konten wellness."
            ),
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["psikolog", "reimburse"],
            "ranking_score": 8,
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
                "Kalau saya beli subscription wellness app, bisa reimburse nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "not_eligible")
        self.assertIsNone(reasoning["estimated_maximum_reimbursement"])
        self.assertEqual(reasoning["required_documents"], [])
        self.assertIn("kemungkinan tidak ditanggung", reasoning["reason"].lower())
        self.assertIn("jangan ajukan klaim dulu", reasoning["next_action"].lower())
        self.assertIn("tidak eligible", result.summary.lower())

    async def test_company_agent_reasoning_marks_needs_review_when_policy_is_missing(self) -> None:
        with (
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Saya tadi ke psikolog online 150 ribu, bisa reimburse nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "needs_review")
        self.assertIn("belum menemukan policy", reasoning["reason"].lower())
        self.assertIn("needs review", result.summary.lower())

    async def test_company_agent_reasoning_uses_frequency_limit_for_mental_health(self) -> None:
        matched_rule = {
            "id": "rule-benefit-mental",
            "title": "Kebijakan Reimbursement Mental Health",
            "category": "benefit",
            "content": (
                "Perusahaan memberikan reimbursement konsultasi psikolog online maksimal "
                "Rp 300.000 per sesi dan maksimal 6 sesi per tahun kalender."
            ),
            "metadata": {
                "policy_key": "benefit.mental_health_reimbursement",
                "case_type": "mental_health",
                "coverage_type": "reimbursement",
                "amount_limit": {"max_value": 300000, "unit": "idr", "period": "session"},
                "frequency_limit": {"max_count": 6, "unit": "session", "period": "year"},
                "eligible_levels": ["permanent", "contract"],
                "required_documents": ["invoice", "receipt", "bukti bayar"],
                "constraints": {"excluded_keywords": ["subscription", "wellness"]},
            },
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["psikolog", "reimburse"],
            "ranking_score": 10,
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
                "Saya mau klaim sesi ke-7 psikolog tahun ini, masih bisa reimburse nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "not_eligible")
        self.assertIn("frequency_limit", reasoning["constraints_triggered"])
        self.assertEqual(reasoning["policy_frequency_limit"]["max_count"], 6)
        self.assertIn("6 sesi per tahun", result.summary.lower())

    async def test_company_agent_reasoning_marks_probation_leave_case_as_not_eligible(self) -> None:
        matched_rule = {
            "id": "rule-leave-annual",
            "title": "Kebijakan Cuti Tahunan",
            "category": "leave",
            "content": (
                "Karyawan tetap berhak atas 12 hari cuti tahunan per tahun kalender. "
                "Cuti tahunan dapat diambil setelah melewati masa probation selama 3 bulan."
            ),
            "metadata": {
                "policy_key": "leave.annual_leave",
                "case_type": "annual_leave",
                "coverage_type": "entitlement",
                "amount_limit": {"max_value": 12, "unit": "day", "period": "year"},
                "eligible_levels": ["permanent", "contract", "intern"],
                "required_documents": [],
                "constraints": {"min_tenure_months": 3, "carry_over_allowed": False},
            },
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["cuti tahunan", "probation"],
            "ranking_score": 10,
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
                "Saya masih probation 2 bulan, bisa ambil cuti tahunan nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "not_eligible")
        self.assertIn("minimum_tenure", reasoning["constraints_triggered"])
        self.assertEqual(reasoning["policy_limit"]["max_value"], 12)
        self.assertIn("probation", result.summary.lower())

    async def test_company_agent_reasoning_marks_payroll_day_outside_policy_as_not_eligible(self) -> None:
        matched_rule = {
            "id": "rule-payroll",
            "title": "Kebijakan Gaji dan Kompensasi",
            "category": "payroll",
            "content": (
                "Gaji dibayarkan setiap akhir bulan, selambat-lambatnya tanggal 28 setiap bulan. "
                "Slip gaji dikirimkan melalui email pada tanggal pembayaran gaji."
            ),
            "metadata": {
                "policy_key": "payroll.salary_compensation",
                "case_type": "payroll",
                "coverage_type": "schedule",
                "frequency_limit": {"max_count": 1, "unit": "payment", "period": "month"},
                "eligible_levels": ["permanent", "contract", "intern"],
                "required_documents": [],
                "constraints": {"salary_payment_day_max": 28, "payslip_delivery": "payment_day"},
            },
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["gaji", "policy"],
            "ranking_score": 9,
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
                "Kalau gaji dibayar tanggal 30, masih sesuai policy nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "not_eligible")
        self.assertIn("salary_payment_day_max", reasoning["constraints_triggered"])
        self.assertEqual(reasoning["requested_day_of_month"], 30)
        self.assertIn("tanggal 28", reasoning["reason"].lower())

    async def test_company_agent_reasoning_marks_intern_allowance_case_as_not_eligible(self) -> None:
        matched_rule = {
            "id": "rule-allowance",
            "title": "Kebijakan Tunjangan Komunikasi dan Internet",
            "category": "payroll",
            "content": (
                "Tunjangan komunikasi dan internet sebesar Rp 250.000 per bulan berlaku "
                "untuk karyawan tetap dan kontrak aktif, tidak berlaku untuk magang "
                "atau probation."
            ),
            "metadata": {
                "policy_key": "payroll.communication_allowance",
                "case_type": "allowance",
                "coverage_type": "allowance",
                "amount_limit": {"max_value": 250000, "unit": "idr", "period": "month"},
                "frequency_limit": {"max_count": 1, "unit": "allowance", "period": "month"},
                "eligible_levels": ["permanent", "contract"],
                "required_documents": [],
                "constraints": {"excluded_levels": ["intern", "probation"]},
            },
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["tunjangan", "internet"],
            "ranking_score": 9,
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
                "Saya masih magang, apakah dapat tunjangan internet 250 ribu per bulan?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "not_eligible")
        self.assertIn("employee_level", reasoning["constraints_triggered"])
        self.assertEqual(reasoning["detected_employee_level"], "intern")
        self.assertIn("karyawan magang", result.summary.lower())

    async def test_company_agent_reasoning_marks_medical_case_without_docs_as_needs_review(self) -> None:
        matched_rule = {
            "id": "rule-medical",
            "title": "Kebijakan Reimbursement Medical Outpatient",
            "category": "benefit",
            "content": (
                "Reimbursement rawat jalan maksimal Rp 500.000 per kunjungan dan wajib "
                "dilengkapi invoice, bukti bayar, serta surat dokter atau resep."
            ),
            "metadata": {
                "policy_key": "benefit.medical_outpatient_reimbursement",
                "case_type": "medical",
                "coverage_type": "reimbursement",
                "amount_limit": {"max_value": 500000, "unit": "idr", "period": "visit"},
                "frequency_limit": {"max_count": 10, "unit": "claim", "period": "year"},
                "eligible_levels": ["permanent", "contract"],
                "required_documents": ["invoice", "bukti bayar", "surat dokter", "resep"],
                "constraints": {"excluded_keywords": ["vitamin", "suplemen"]},
            },
            "effective_date": "2026-01-01",
            "is_active": True,
            "matched_terms": ["medical", "rawat jalan"],
            "ranking_score": 9,
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
                "Saya habis rawat jalan 400 ribu tapi belum ada invoice dan surat dokter, bisa claim nggak?",
            )

        reasoning = result.records["policy_reasoning"]
        self.assertEqual(reasoning["eligibility"], "needs_review")
        self.assertIn("missing_documents", reasoning["constraints_triggered"])
        self.assertIn("invoice", reasoning["missing_required_documents"])
        self.assertIn("surat dokter", reasoning["missing_required_documents"])
        self.assertIn("lengkapi dokumen", reasoning["next_action"].lower())

    async def test_company_agent_prefers_current_policy_version_when_versions_compete(self) -> None:
        with (
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(
                    return_value=[
                        {
                            "id": "rule-old",
                            "title": "Work From Home Policy",
                            "category": "work_arrangement",
                            "content": "Old remote work policy.",
                            "effective_date": "2025-01-01",
                            "is_active": True,
                            "matched_terms": ["vector_search"],
                            "matched_chunk": "Old remote work policy.",
                            "similarity": 0.88,
                            "ranking_score": 0.88,
                        },
                        {
                            "id": "rule-new",
                            "title": "Work From Home Policy",
                            "category": "work_arrangement",
                            "content": "Current remote work policy.",
                            "effective_date": "2026-02-01",
                            "is_active": True,
                            "matched_terms": ["vector_search"],
                            "matched_chunk": "Current remote work policy.",
                            "similarity": 0.85,
                            "ranking_score": 0.85,
                        },
                    ]
                ),
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=AsyncMock(
                    return_value=[
                        {
                            "id": "rule-old",
                            "title": "Work From Home Policy",
                            "category": "work_arrangement",
                            "content": "Old remote work policy.",
                            "effective_date": "2025-01-01",
                            "is_active": True,
                        },
                        {
                            "id": "rule-new",
                            "title": "Work From Home Policy",
                            "category": "work_arrangement",
                            "content": "Current remote work policy.",
                            "effective_date": "2026-02-01",
                            "is_active": True,
                        },
                    ]
                ),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Apa aturan remote work terbaru?",
            )

        matched_rules = result.records["matched_rules"]
        self.assertEqual(matched_rules[0]["id"], "rule-new")
        self.assertEqual(matched_rules[0]["freshness_status"], "current")
        self.assertEqual(matched_rules[0]["version_source"], "latest_active_version")
        self.assertIn("Current remote work policy.", result.summary)
        self.assertNotIn("Old remote work policy.", result.summary)

    async def test_company_agent_promotes_latest_policy_when_only_old_version_matches(self) -> None:
        with (
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(
                    return_value=[
                        {
                            "id": "rule-old",
                            "title": "Work From Home Policy",
                            "category": "work_arrangement",
                            "content": "Old remote work policy.",
                            "effective_date": "2025-01-01",
                            "is_active": True,
                            "matched_terms": ["vector_search"],
                            "matched_chunk": "Old remote work policy.",
                            "similarity": 0.88,
                            "ranking_score": 0.88,
                        }
                    ]
                ),
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=AsyncMock(
                    return_value=[
                        {
                            "id": "rule-old",
                            "title": "Work From Home Policy",
                            "category": "work_arrangement",
                            "content": "Old remote work policy.",
                            "effective_date": "2025-01-01",
                            "is_active": True,
                        },
                        {
                            "id": "rule-new",
                            "title": "Work From Home Policy",
                            "category": "work_arrangement",
                            "content": "Current remote work policy.",
                            "effective_date": "2026-02-01",
                            "is_active": True,
                        },
                    ]
                ),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Apa aturan remote work terbaru?",
            )

        assessment = result.records["retrieval_assessment"]["policy"]
        matched_rules = result.records["matched_rules"]
        self.assertEqual(assessment["status"], "partial")
        self.assertTrue(assessment["version_promotion_used"])
        self.assertEqual(matched_rules[0]["id"], "rule-new")
        self.assertEqual(matched_rules[0]["promoted_from_rule_id"], "rule-old")
        self.assertEqual(matched_rules[0]["version_source"], "latest_active_version")
        self.assertIn("Current remote work policy.", result.summary)
        self.assertNotIn("Old remote work policy.", result.summary)

    async def test_company_agent_contact_guidance_prefers_hr_structure_without_policy_lookup(self) -> None:
        load_structure_mock = AsyncMock(
            return_value=[
                {
                    "department_id": "dept-hr",
                    "department_name": "Human Resources",
                    "parent_department_name": None,
                    "head_employee_name": "Siti Rahayu",
                },
                {
                    "department_id": "dept-it",
                    "department_name": "IT",
                    "parent_department_name": None,
                    "head_employee_name": "Budi Santoso",
                },
            ]
        )
        load_rules_mock = AsyncMock(
            return_value=[
                {
                    "id": "rule-1",
                    "title": "Kebijakan Cuti Tahunan",
                    "category": "leave",
                    "content": "Cuti tahunan mengikuti kebijakan perusahaan.",
                    "effective_date": "2026-01-01",
                    "is_active": True,
                }
            ]
        )

        with (
            patch(
                "app.agents.company_agent._load_company_structure",
                new=load_structure_mock,
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=load_rules_mock,
            ),
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Kalau saya bingung urusan cuti atau administrasi, saya harus hubungi siapa?",
            )

        self.assertEqual(load_rules_mock.await_count, 0)
        self.assertEqual(result.retrieval_mode, "structure_lookup")
        self.assertTrue(result.records["contact_guidance_requested"])
        self.assertIn("Siti Rahayu", result.summary)
        self.assertNotIn("Kebijakan", result.summary)
        self.assertEqual(
            result.records["retrieval_assessment"]["structure"]["department_count"],
            1,
        )

    async def test_company_agent_structure_query_skips_irrelevant_policy_lookup(self) -> None:
        load_structure_mock = AsyncMock(
            return_value=[
                {
                    "department_id": "dept-hr",
                    "department_name": "Human Resources",
                    "parent_department_name": None,
                    "head_employee_name": "Siti Rahayu",
                }
            ]
        )
        load_rules_mock = AsyncMock(return_value=[])

        with (
            patch(
                "app.agents.company_agent._load_company_structure",
                new=load_structure_mock,
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=load_rules_mock,
            ),
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Tim HR di perusahaan ini siapa?",
            )

        self.assertEqual(load_rules_mock.await_count, 0)
        self.assertEqual(result.retrieval_mode, "structure_lookup")
        self.assertEqual(result.records["departments"][0]["department_name"], "Human Resources")
        self.assertNotIn("matched_rules", result.records)

    async def test_company_agent_referral_guidance_maps_to_hr_with_preparation_metadata(self) -> None:
        load_structure_mock = AsyncMock(
            return_value=[
                {
                    "department_id": "dept-hr",
                    "department_name": "Human Resources",
                    "parent_department_name": None,
                    "head_employee_name": "Siti Rahayu",
                },
                {
                    "department_id": "dept-it",
                    "department_name": "IT",
                    "parent_department_name": None,
                    "head_employee_name": "Budi Santoso",
                },
            ]
        )
        load_rules_mock = AsyncMock(return_value=[])

        with (
            patch(
                "app.agents.company_agent._load_company_structure",
                new=load_structure_mock,
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=load_rules_mock,
            ),
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Kalau mau refer temen harus ke siapa ya?",
            )

        self.assertEqual(load_rules_mock.await_count, 0)
        self.assertEqual(result.retrieval_mode, "structure_lookup")
        self.assertEqual(result.records["contact_guidance_topic"], "recruiting")
        self.assertIn("recruiter", result.records["recommended_channel"].lower())
        self.assertGreaterEqual(len(result.records["preparation_checklist"]), 2)
        self.assertIn("referral hiring", result.summary.lower())

    async def test_company_agent_guidance_prefers_functional_owner_route_over_department_head(self) -> None:
        load_structure_mock = AsyncMock(
            return_value=[
                {
                    "department_id": "dept-hr",
                    "department_name": "Human Resources",
                    "parent_department_name": None,
                    "head_employee_name": "Siti Rahayu",
                }
            ]
        )
        load_rules_mock = AsyncMock(return_value=[])
        load_responsibility_routes_mock = AsyncMock(
            return_value=[
                {
                    "route_id": "route-recruiting",
                    "topic_key": "recruiting",
                    "department_id": "dept-hr",
                    "department_name": "Human Resources",
                    "primary_employee_id": "emp-ta",
                    "primary_contact_name": "Nadya Putri",
                    "primary_contact_role": "Talent Acquisition Specialist",
                    "alternate_employee_id": "emp-hr-manager",
                    "alternate_contact_name": "Siti Rahayu",
                    "alternate_contact_role": "HR Manager",
                    "recommended_channel": "chat atau email internal recruiter / TA",
                    "preparation_checklist": [
                        "Siapkan nama kandidat dan posisi yang ingin direferensikan.",
                        "Kalau ada CV, LinkedIn, atau ringkasan profil kandidat, siapkan juga sebelum menghubungi tim terkait.",
                    ],
                }
            ]
        )

        with (
            patch(
                "app.agents.company_agent._load_company_structure",
                new=load_structure_mock,
            ),
            patch(
                "app.agents.company_agent._load_company_rules",
                new=load_rules_mock,
            ),
            patch(
                "app.agents.company_agent._load_responsibility_routes",
                new=load_responsibility_routes_mock,
            ),
            patch(
                "app.agents.company_agent._search_rule_chunks_by_vector",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await run_company_agent(
                self.db,
                self.session,
                "Kalau mau refer temen harus ke siapa ya?",
            )

        self.assertEqual(load_rules_mock.await_count, 0)
        self.assertEqual(result.records["contact_guidance_route_source"], "responsibility_route")
        self.assertEqual(result.records["primary_contact_name"], "Nadya Putri")
        self.assertEqual(result.records["alternate_contact_name"], "Siti Rahayu")
        self.assertIn("Nadya Putri", result.summary)
        self.assertIn("Talent Acquisition Specialist", result.summary)
        self.assertIn("alternatif", result.summary.lower())

    async def test_orchestrator_marks_contact_guidance_as_guidance_response_mode(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        company_agent_mock = AsyncMock(
            return_value=CompanyAgentResult(
                retrieval_mode="structure_lookup",
                summary=(
                    "Untuk urusan administrasi HR, onboarding, cuti, payroll, atau "
                    "policy internal, kamu bisa mulai dari Siti Rahayu di departemen "
                    "Human Resources."
                ),
                records={
                    "contact_guidance_requested": True,
                    "departments": [
                        {
                            "department_id": "dept-hr",
                            "department_name": "Human Resources",
                            "parent_department_name": None,
                            "head_employee_name": "Siti Rahayu",
                        }
                    ],
                },
                evidence=[],
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=company_agent_mock,
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Kalau saya bingung urusan cuti atau administrasi, saya harus hubungi siapa?",
                    attachments=[],
                ),
            )

        self.assertEqual(result.route, AgentRoute.COMPANY)
        self.assertEqual(
            result.request_category,
            ConversationRequestCategory.GUIDANCE_REQUEST,
        )
        self.assertEqual(result.response_mode, ResponseMode.GUIDANCE)
        self.assertTrue(result.recommended_next_steps)
        self.assertEqual(
            result.context["response_contract"]["response_mode"],
            ResponseMode.GUIDANCE.value,
        )

    async def test_orchestrator_guidance_next_steps_use_company_contact_metadata(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        company_agent_mock = AsyncMock(
            return_value=CompanyAgentResult(
                retrieval_mode="structure_lookup",
                summary=(
                    "Untuk urusan referral hiring, rekrutmen, recruiter, atau TA, kamu "
                    "bisa mulai dari Siti Rahayu di departemen Human Resources."
                ),
                records={
                    "contact_guidance_requested": True,
                    "contact_guidance_topic": "recruiting",
                    "recommended_channel": "chat atau email internal tim HR / recruiter / TA",
                    "preparation_checklist": [
                        "Siapkan nama kandidat dan posisi yang ingin direferensikan.",
                        "Kalau ada CV, LinkedIn, atau ringkasan profil kandidat, siapkan juga sebelum menghubungi tim terkait.",
                    ],
                    "departments": [
                        {
                            "department_id": "dept-hr",
                            "department_name": "Human Resources",
                            "parent_department_name": None,
                            "head_employee_name": "Siti Rahayu",
                        }
                    ],
                },
                evidence=[],
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=company_agent_mock,
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Kalau mau refer temen harus ke siapa ya?",
                    attachments=[],
                ),
            )

        self.assertEqual(result.response_mode, ResponseMode.GUIDANCE)
        self.assertIn("channel yang disarankan", result.recommended_next_steps[0].lower())
        self.assertIn("nama kandidat", " ".join(result.recommended_next_steps).lower())

    async def test_orchestrator_marks_explicit_payslip_request_as_workflow_intake(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        hr_agent_mock = AsyncMock(
            return_value=HRDataAgentResult(
                topics=["payroll"],
                summary="Payroll terbaru yang ditemukan adalah periode April 2026.",
                records={"payroll": [{"month": 4, "year": 2026}]},
                evidence=[],
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=hr_agent_mock,
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Tolong kirimkan PDF slip gaji saya bulan ini.",
                    attachments=[],
                ),
            )

        self.assertEqual(result.route, AgentRoute.HR_DATA)
        self.assertEqual(
            result.request_category,
            ConversationRequestCategory.WORKFLOW_REQUEST,
        )
        self.assertEqual(result.response_mode, ResponseMode.WORKFLOW_INTAKE)
        self.assertGreaterEqual(len(result.recommended_next_steps), 1)

    async def test_orchestrator_keeps_workflow_intake_aligned_with_action_gate_for_soft_request(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        hr_agent_mock = AsyncMock(
            return_value=HRDataAgentResult(
                topics=["payroll"],
                summary="Payroll terbaru yang ditemukan adalah periode April 2026.",
                records={"payroll": [{"month": 4, "year": 2026}]},
                evidence=[],
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=hr_agent_mock,
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Tolong bantu payslip saya dong.",
                    attachments=[],
                ),
            )

        self.assertEqual(result.route, AgentRoute.HR_DATA)
        self.assertEqual(
            result.request_category,
            ConversationRequestCategory.WORKFLOW_REQUEST,
        )
        self.assertEqual(result.response_mode, ResponseMode.WORKFLOW_INTAKE)

    async def test_orchestrator_marks_policy_case_as_policy_reasoning_response_mode(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        company_agent_mock = AsyncMock(
            return_value=CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Klaim psikolog online kemungkinan perlu verifikasi policy benefit kesehatan.",
                records={
                    "matched_rules": [{"title": "Mental Health Benefit"}],
                    "policy_reasoning": {
                        "eligibility": "needs_review",
                        "required_documents": ["invoice", "receipt"],
                        "next_action": "Siapkan dokumen pendukung lalu verifikasi ke HR atau tim benefits.",
                    },
                },
                evidence=[],
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
            patch(
                "app.agents.orchestrator.classify_intent",
                return_value=IntentAssessment(
                    primary_intent=ConversationIntent.COMPANY_POLICY,
                    secondary_intents=[],
                    confidence=0.9,
                    matched_keywords=["semantic:company_policy"],
                ),
            ),
            patch(
                "app.agents.orchestrator.assess_sensitivity",
                return_value=SensitivityAssessment(
                    level=SensitivityLevel.LOW,
                    matched_keywords=[],
                    rationale="Policy reasoning request.",
                ),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=company_agent_mock,
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Saya tadi ke psikolog online 150 ribu, bisa reimburse nggak?",
                    attachments=[],
                ),
            )

        self.assertEqual(result.route, AgentRoute.COMPANY)
        self.assertEqual(
            result.request_category,
            ConversationRequestCategory.POLICY_REASONING_REQUEST,
        )
        self.assertEqual(result.response_mode, ResponseMode.POLICY_REASONING)
        self.assertGreaterEqual(len(result.recommended_next_steps), 1)
        self.assertIn("invoice", " ".join(result.recommended_next_steps).lower())

    async def test_orchestrator_not_eligible_policy_reasoning_skips_claim_document_steps(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        company_agent_mock = AsyncMock(
            return_value=CompanyAgentResult(
                retrieval_mode="policy_lookup",
                summary="Kasus benefit ini kemungkinan tidak eligible.",
                records={
                    "matched_rules": [{"title": "Mental Health Benefit"}],
                    "policy_reasoning": {
                        "eligibility": "not_eligible",
                        "required_documents": ["invoice", "receipt"],
                        "next_action": "Jangan ajukan klaim dulu. Verifikasi manual dulu ke HR atau tim benefits kalau kamu yakin kasusnya berbeda.",
                    },
                },
                evidence=[],
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
            patch(
                "app.agents.orchestrator.classify_intent",
                return_value=IntentAssessment(
                    primary_intent=ConversationIntent.COMPANY_POLICY,
                    secondary_intents=[],
                    confidence=0.9,
                    matched_keywords=["semantic:company_policy"],
                ),
            ),
            patch(
                "app.agents.orchestrator.assess_sensitivity",
                return_value=SensitivityAssessment(
                    level=SensitivityLevel.LOW,
                    matched_keywords=[],
                    rationale="Policy reasoning request.",
                ),
            ),
            patch(
                "app.agents.orchestrator.run_company_agent",
                new=company_agent_mock,
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Kalau saya beli subscription wellness app, bisa reimburse nggak?",
                    attachments=[],
                ),
            )

        self.assertEqual(result.response_mode, ResponseMode.POLICY_REASONING)
        joined_steps = " ".join(result.recommended_next_steps).lower()
        self.assertNotIn("invoice", joined_steps)
        self.assertNotIn("receipt", joined_steps)
        self.assertIn("jangan ajukan klaim dulu", joined_steps)

    async def test_orchestrator_marks_sensitive_decision_support_as_guarded(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Saya burnout berat dan kepikiran resign bulan ini.",
                    attachments=[],
                ),
            )

        self.assertEqual(result.route, AgentRoute.SENSITIVE_REDIRECT)
        self.assertEqual(
            result.request_category,
            ConversationRequestCategory.DECISION_SUPPORT,
        )
        self.assertEqual(result.response_mode, ResponseMode.SENSITIVE_GUARDED)
        self.assertGreaterEqual(len(result.recommended_next_steps), 1)

    async def test_orchestrator_applies_session_d_sensitive_templates_and_policy_matrix(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )

        cases = [
            {
                "message": "Saya sedang mempertimbangkan resign bulan depan dan belum tahu langkah yang aman.",
                "case_key": "resignation_intention",
                "request_category": ConversationRequestCategory.DECISION_SUPPORT,
                "action_policy": "guidance_only",
                "review_policy": "redirect_only",
                "answer_fragment": "niat resign",
            },
            {
                "message": "Saya burnout dan mulai merasa kewalahan dengan pekerjaan sekarang.",
                "case_key": "burnout_emotional_distress",
                "request_category": ConversationRequestCategory.DECISION_SUPPORT,
                "action_policy": "guidance_only",
                "review_policy": "redirect_only",
                "answer_fragment": "burnout",
            },
            {
                "message": "Saya punya konflik serius dengan atasan saya dan butuh arahan.",
                "case_key": "manager_conflict",
                "request_category": ConversationRequestCategory.DECISION_SUPPORT,
                "action_policy": "guidance_only",
                "review_policy": "redirect_only",
                "answer_fragment": "atasan atau manager",
            },
            {
                "message": "Saya merasa tempat kerja ini tidak aman dan ada ancaman di kantor.",
                "case_key": "unsafe_workplace",
                "request_category": ConversationRequestCategory.SENSITIVE_REPORT,
                "action_policy": "create_task",
                "review_policy": "mandatory_manual_review",
                "answer_fragment": "tidak aman di tempat kerja",
            },
            {
                "message": "Saya ingin melaporkan pelecehan dan diskriminasi di kantor.",
                "case_key": "harassment_discrimination",
                "request_category": ConversationRequestCategory.SENSITIVE_REPORT,
                "action_policy": "create_task",
                "review_policy": "mandatory_manual_review",
                "answer_fragment": "pelecehan atau diskriminasi",
            },
        ]

        for case in cases:
            with (
                patch(
                    "app.agents.orchestrator.retrieve_intent_candidates",
                    new=semantic_mock,
                ),
                patch(
                    "app.agents.orchestrator.retrieve_agent_capabilities",
                    new=capability_mock,
                ),
                patch(
                    "app.agents.orchestrator._should_use_provider_classifier",
                    return_value=(False, "Test skipped provider."),
                ),
            ):
                result = await orchestrate_message(
                    self.db,
                    self.session,
                    OrchestratorRequest(
                        message=case["message"],
                        attachments=[],
                    ),
                )

            self.assertEqual(result.route, AgentRoute.SENSITIVE_REDIRECT)
            self.assertEqual(result.request_category, case["request_category"])
            self.assertEqual(result.response_mode, ResponseMode.SENSITIVE_GUARDED)
            self.assertIn(case["answer_fragment"], result.answer.lower())
            handling = result.context["sensitive_handling"]
            self.assertEqual(handling["case_key"], case["case_key"])
            self.assertEqual(handling["action_policy"], case["action_policy"])
            self.assertEqual(handling["review_policy"], case["review_policy"])
            self.assertGreaterEqual(len(result.recommended_next_steps), 1)

    async def test_orchestrator_uses_grounding_for_routing_without_polluting_hr_agent_input(self) -> None:
        semantic_mock = AsyncMock(
            return_value=SemanticIntentResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )
        capability_mock = AsyncMock(
            return_value=AgentCapabilityResult(
                candidates=[],
                retrieval_mode="disabled",
                fallback_reason="test",
            )
        )

        async def fake_hr_agent(*args, **kwargs):
            self.assertEqual(args[2], "Yang tadi tapi untuk April 2026 bagaimana?")
            self.assertEqual(
                kwargs["conversation_history"][0]["content"],
                "Kenapa gaji Maret 2026 saya lebih rendah?",
            )
            return HRDataAgentResult(
                topics=["payroll"],
                summary="Payroll terbaru yang ditemukan adalah periode April 2026 dengan net pay Rp12.100.000.",
                records={
                    "payroll": [
                        {
                            "month": 4,
                            "year": 2026,
                            "net_pay": 12100000,
                            "gross_salary": 13650000,
                            "payment_status": "paid",
                        }
                    ]
                },
                evidence=[],
            )

        with (
            patch(
                "app.agents.orchestrator.retrieve_intent_candidates",
                new=semantic_mock,
            ),
            patch(
                "app.agents.orchestrator.retrieve_agent_capabilities",
                new=capability_mock,
            ),
            patch(
                "app.agents.orchestrator._should_use_provider_classifier",
                return_value=(False, "Test skipped provider."),
            ),
            patch(
                "app.agents.orchestrator.run_hr_data_agent",
                new=AsyncMock(side_effect=fake_hr_agent),
            ),
        ):
            result = await orchestrate_message(
                self.db,
                self.session,
                OrchestratorRequest(
                    message="Yang tadi tapi untuk April 2026 bagaimana?",
                    attachments=[],
                    conversation_history=[
                        {
                            "role": "user",
                            "content": "Kenapa gaji Maret 2026 saya lebih rendah?",
                        },
                        {
                            "role": "assistant",
                            "content": "Net pay Maret 2026 lebih rendah karena potongan naik.",
                        },
                    ],
                ),
            )

        self.assertEqual(result.route, AgentRoute.HR_DATA)
        self.assertTrue(result.context["conversation_grounding"]["used"])
        self.assertIn(
            "Kenapa gaji Maret 2026 saya lebih rendah?",
            semantic_mock.await_args.args[2],
        )
        self.assertIn(
            "Yang tadi tapi untuk April 2026 bagaimana?",
            semantic_mock.await_args.args[2],
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

    def test_classifier_can_route_contact_guidance_to_company_structure(self) -> None:
        assessment = classify_intent(
            "Kalau saya bingung urusan cuti atau administrasi, saya harus hubungi siapa?",
        )

        self.assertEqual(assessment.primary_intent, ConversationIntent.COMPANY_STRUCTURE)
        self.assertIn("company_structure_contact_signal", assessment.matched_keywords)
        self.assertGreaterEqual(assessment.confidence, 0.75)

    def test_classifier_can_route_referral_hiring_guidance_to_company_structure(self) -> None:
        assessment = classify_intent(
            "Kalau mau refer temen harus ke siapa ya?",
        )

        self.assertEqual(assessment.primary_intent, ConversationIntent.COMPANY_STRUCTURE)
        self.assertIn("company_structure_contact_signal", assessment.matched_keywords)
        self.assertGreaterEqual(assessment.confidence, 0.75)

    def test_classifier_can_route_payroll_contact_guidance_to_company_structure(self) -> None:
        assessment = classify_intent(
            "Kalau mau nanya payroll ke siapa ya?",
        )

        self.assertEqual(assessment.primary_intent, ConversationIntent.COMPANY_STRUCTURE)
        self.assertIn("company_structure_contact_signal", assessment.matched_keywords)
        self.assertGreaterEqual(assessment.confidence, 0.75)

    def test_classifier_can_route_reimbursement_case_to_company_policy(self) -> None:
        assessment = classify_intent(
            "Saya tadi ke psikolog online 150 ribu, bisa reimburse nggak?",
        )

        self.assertEqual(assessment.primary_intent, ConversationIntent.COMPANY_POLICY)
        self.assertIn("company_policy_reasoning_signal", assessment.matched_keywords)
        self.assertGreaterEqual(assessment.confidence, 0.75)

    def test_classifier_can_route_probation_leave_policy_case_to_company_policy(self) -> None:
        assessment = classify_intent(
            "Saya masih probation 2 bulan, bisa ambil cuti tahunan nggak?",
        )

        self.assertEqual(assessment.primary_intent, ConversationIntent.COMPANY_POLICY)
        self.assertIn("company_policy_reasoning_signal", assessment.matched_keywords)
        self.assertGreaterEqual(assessment.confidence, 0.75)

    def test_classifier_can_route_payroll_policy_case_to_company_policy(self) -> None:
        assessment = classify_intent(
            "Kalau gaji dibayar tanggal 30, masih sesuai policy nggak?",
        )

        self.assertEqual(assessment.primary_intent, ConversationIntent.COMPANY_POLICY)
        self.assertIn("company_policy_reasoning_signal", assessment.matched_keywords)
        self.assertGreaterEqual(assessment.confidence, 0.75)

    def test_classifier_can_route_allowance_policy_case_to_company_policy(self) -> None:
        assessment = classify_intent(
            "Saya masih magang, apakah dapat tunjangan internet 250 ribu per bulan?",
        )

        self.assertEqual(assessment.primary_intent, ConversationIntent.COMPANY_POLICY)
        self.assertIn("company_policy_reasoning_signal", assessment.matched_keywords)
        self.assertGreaterEqual(assessment.confidence, 0.75)

    def test_classifier_does_not_route_plain_optical_statement_to_company_policy(self) -> None:
        assessment = classify_intent(
            "Kacamata saya pecah.",
        )

        self.assertNotEqual(assessment.primary_intent, ConversationIntent.COMPANY_POLICY)
        self.assertEqual(assessment.primary_intent, ConversationIntent.OUT_OF_SCOPE)

    # ------------------------------------------------------------------
    # Session E – Conversational Request Intake (F.1–F.4) tests
    # ------------------------------------------------------------------

    # --- Gate unit tests (execution_intent.py) ---

    def test_leave_gate_returns_execution_when_both_dates_present(self) -> None:
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Saya ingin ajukan pengajuan cuti sakit dari 10 April 2026 sampai 14 April 2026.",
            intent_key="time_off_request_status",
        )
        self.assertEqual(result["mode"], "execution_request")
        self.assertTrue(result["should_trigger"])
        self.assertEqual(result["extracted"]["leave_type"], "sick")
        self.assertIsNotNone(result["extracted"]["start_date"])
        self.assertIsNotNone(result["extracted"]["end_date"])

    def test_leave_gate_returns_missing_info_when_dates_absent(self) -> None:
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Saya mau ajukan cuti saya.",
            intent_key="time_off_request_status",
        )
        self.assertEqual(result["mode"], "missing_info")
        self.assertFalse(result["should_trigger"])
        self.assertIn("start_date", result["missing_fields"])
        self.assertIn("end_date", result["missing_fields"])
        self.assertIn("follow_up_prompt", result)

    def test_leave_gate_returns_not_applicable_for_exploratory_message(self) -> None:
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Apakah saya bisa mengambil cuti tahunan minggu ini?",
            intent_key="time_off_request_status",
        )
        self.assertEqual(result["mode"], "not_applicable")
        self.assertFalse(result["should_trigger"])

    def test_reimbursement_gate_returns_execution_when_amount_and_date_present(self) -> None:
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Saya mau klaim kacamata sebesar 500 ribu pada 3 April 2026.",
            intent_key="company_policy",
        )
        self.assertEqual(result["mode"], "execution_request")
        self.assertTrue(result["should_trigger"])
        self.assertEqual(result["extracted"]["category"], "optical")
        self.assertAlmostEqual(result["extracted"]["amount"], 500_000.0)
        self.assertIsNotNone(result["extracted"]["expense_date"])

    def test_reimbursement_gate_returns_missing_info_when_amount_absent(self) -> None:
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Saya mau klaim kacamata pada 3 April 2026.",
            intent_key="company_policy",
        )
        self.assertEqual(result["mode"], "missing_info")
        self.assertFalse(result["should_trigger"])
        self.assertIn("amount", result["missing_fields"])
        self.assertIn("follow_up_prompt", result)

    def test_profile_update_gate_returns_execution_when_field_identified(self) -> None:
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Tolong update data saya nomor hp.",
            intent_key="personal_profile",
        )
        self.assertEqual(result["mode"], "execution_request")
        self.assertTrue(result["should_trigger"])
        self.assertIn("phone_number", result["extracted"]["fields_to_update"])

    def test_profile_update_gate_returns_missing_info_when_no_field_identified(self) -> None:
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Tolong update data saya.",
            intent_key="personal_profile",
        )
        self.assertEqual(result["mode"], "missing_info")
        self.assertFalse(result["should_trigger"])
        self.assertIn("fields_to_update", result["missing_fields"])

    def test_leave_gate_does_not_false_negative_when_bisa_present_with_execution_verb(self) -> None:
        """'bisa' inside a leave submission phrase must not mark it as exploratory."""
        from app.services.execution_intent import assess_action_execution_intent

        result = assess_action_execution_intent(
            "Saya mau ajukan cuti sakit, bisa mulai 10 April sampai 14 April 2026?",
            intent_key="time_off_request_status",
        )
        # Should detect as execution (both dates present), not not_applicable.
        self.assertIn(result["mode"], {"execution_request", "missing_info"})
        self.assertTrue(result["should_trigger"] or result.get("missing_fields") is not None)

    def test_extract_amount_does_not_match_year_without_preceding_small_number(self) -> None:
        """Year-like tokens (2026) must not be returned as monetary amount."""
        from app.services.execution_intent import _extract_amount

        self.assertIsNone(_extract_amount("klaim kacamata April 2026"))
        self.assertIsNone(_extract_amount("tanggal 2026"))

    def test_extract_amount_handles_decimal_suffix_correctly(self) -> None:
        """'1,5jt' must parse as 1_500_000, not 15_000_000."""
        from app.services.execution_intent import _extract_amount

        self.assertAlmostEqual(_extract_amount("klaim 1,5jt"), 1_500_000.0)
        self.assertAlmostEqual(_extract_amount("klaim 1.5jt"), 1_500_000.0)
        self.assertAlmostEqual(_extract_amount("klaim 500rb"), 500_000.0)
        self.assertAlmostEqual(_extract_amount("klaim 500.000"), 500_000.0)

    # --- Integration tests (conversations API) ---

    def test_leave_request_creates_action_when_gate_approves(self) -> None:
        self.db.rules.append(
            {
                "id": "60000000-0000-0000-0000-000000000010",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Leave request intake",
                "description": "Create a leave request action after a resolved conversation.",
                "trigger": "conversation_resolved",
                "intent_key": "time_off_request_status",
                "sensitivity_threshold": "medium",
                "is_enabled": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self.db.rule_actions["60000000-0000-0000-0000-000000000010"] = [
            {
                "rule_id": "60000000-0000-0000-0000-000000000010",
                "action_type": "leave_request",
                "title_template": "Leave request",
                "summary_template": "Employee leave request pending HR review.",
                "priority": "medium",
                "delivery_channels": ["in_app"],
                "payload_template": {"leave_type": "annual"},
            }
        ]
        conversation_id = self._create_conversation(title="Leave request test")

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.conversations._assess_action_execution_intent",
                return_value={
                    "mode": "execution_request",
                    "should_trigger": True,
                    "reason": "Leave request with valid dates.",
                    "extracted": {
                        "leave_type": "sick",
                        "start_date": "10 April 2026",
                        "end_date": "14 April 2026",
                    },
                },
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Saya ingin ajukan pengajuan cuti sakit dari 10 April 2026 sampai 14 April 2026.",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload["triggered_actions"]), 1)
        triggered = payload["triggered_actions"][0]
        self.assertEqual(triggered["type"], "leave_request")

    def test_leave_request_missing_dates_appends_follow_up_prompt(self) -> None:
        self.db.rules.append(
            {
                "id": "60000000-0000-0000-0000-000000000011",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Leave request intake",
                "description": "Create a leave request action after a resolved conversation.",
                "trigger": "conversation_resolved",
                "intent_key": "time_off_request_status",
                "sensitivity_threshold": "medium",
                "is_enabled": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self.db.rule_actions["60000000-0000-0000-0000-000000000011"] = []
        conversation_id = self._create_conversation(title="Leave missing dates test")

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.conversations._assess_action_execution_intent",
                return_value={
                    "mode": "missing_info",
                    "should_trigger": False,
                    "reason": "Date fields missing.",
                    "missing_fields": ["start_date", "end_date"],
                    "extracted": {
                        "leave_type": "annual",
                        "start_date": None,
                        "end_date": None,
                    },
                    "follow_up_prompt": "Mulai tanggal berapa cutinya, dan sampai kapan?",
                },
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Saya mau ajukan cuti saya.",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["triggered_actions"], [])
        self.assertIn(
            "Mulai tanggal berapa cutinya",
            payload["assistant_message"]["content"],
        )

    def test_reimbursement_request_creates_action_when_gate_approves(self) -> None:
        self.db.rules.append(
            {
                "id": "60000000-0000-0000-0000-000000000012",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Reimbursement request intake",
                "description": "Create a reimbursement action after a resolved conversation.",
                "trigger": "conversation_resolved",
                "intent_key": "company_policy",
                "sensitivity_threshold": "medium",
                "is_enabled": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self.db.rule_actions["60000000-0000-0000-0000-000000000012"] = [
            {
                "rule_id": "60000000-0000-0000-0000-000000000012",
                "action_type": "reimbursement_request",
                "title_template": "Reimbursement request",
                "summary_template": "Employee reimbursement claim pending review.",
                "priority": "medium",
                "delivery_channels": ["in_app"],
                "payload_template": {"category": "general"},
            }
        ]
        conversation_id = self._create_conversation(title="Reimbursement test")

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.conversations._assess_action_execution_intent",
                return_value={
                    "mode": "execution_request",
                    "should_trigger": True,
                    "reason": "Reimbursement request with all required fields.",
                    "extracted": {
                        "category": "optical",
                        "amount": 500_000.0,
                        "expense_date": "3 April 2026",
                    },
                },
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Saya mau klaim kacamata sebesar 500 ribu pada 3 April 2026.",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload["triggered_actions"]), 1)
        triggered = payload["triggered_actions"][0]
        self.assertEqual(triggered["type"], "reimbursement_request")

    def test_profile_update_creates_action_when_gate_approves(self) -> None:
        self.db.rules.append(
            {
                "id": "60000000-0000-0000-0000-000000000013",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "name": "Profile update request intake",
                "description": "Create a profile update action after a resolved conversation.",
                "trigger": "conversation_resolved",
                "intent_key": "personal_profile",
                "sensitivity_threshold": "medium",
                "is_enabled": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self.db.rule_actions["60000000-0000-0000-0000-000000000013"] = [
            {
                "rule_id": "60000000-0000-0000-0000-000000000013",
                "action_type": "profile_update_request",
                "title_template": "Profile update request",
                "summary_template": "Employee profile update pending HR review.",
                "priority": "low",
                "delivery_channels": ["in_app"],
                "payload_template": {},
            }
        ]
        conversation_id = self._create_conversation(title="Profile update test")

        with (
            patch(
                "app.agents.orchestrator.classify_with_minimax",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.conversations._assess_action_execution_intent",
                return_value={
                    "mode": "execution_request",
                    "should_trigger": True,
                    "reason": "Profile update with identifiable fields.",
                    "extracted": {
                        "fields_to_update": {"phone_number": None},
                    },
                },
            ),
        ):
            response = self.client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message": "Tolong update data saya nomor hp.",
                    "attachments": [],
                    "metadata": {"channel": "test"},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload["triggered_actions"]), 1)
        triggered = payload["triggered_actions"][0]
        self.assertEqual(triggered["type"], "profile_update_request")
