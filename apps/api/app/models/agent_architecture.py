from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared import SensitivityLevel


class ConversationIntent(StrEnum):
    PAYROLL_INFO = "payroll_info"
    PAYROLL_DOCUMENT_REQUEST = "payroll_document_request"
    ATTENDANCE_REVIEW = "attendance_review"
    ATTENDANCE_CORRECTION = "attendance_correction"
    TIME_OFF_BALANCE = "time_off_balance"
    TIME_OFF_REQUEST_STATUS = "time_off_request_status"
    TIME_OFF_SIMULATION = "time_off_simulation"
    PERSONAL_PROFILE = "personal_profile"
    COMPANY_POLICY = "company_policy"
    COMPANY_STRUCTURE = "company_structure"
    EMPLOYEE_WELLBEING_CONCERN = "employee_wellbeing_concern"
    GENERAL_HR_SUPPORT = "general_hr_support"
    OUT_OF_SCOPE = "out_of_scope"


class AgentRoute(StrEnum):
    HR_DATA = "hr_data"
    COMPANY = "company"
    MIXED = "mixed"
    SENSITIVE_REDIRECT = "sensitive_redirect"
    OUT_OF_SCOPE = "out_of_scope"


class ConversationRequestCategory(StrEnum):
    INFORMATIONAL_QUESTION = "informational_question"
    GUIDANCE_REQUEST = "guidance_request"
    POLICY_REASONING_REQUEST = "policy_reasoning_request"
    SIMULATION_REQUEST = "simulation_request"
    WORKFLOW_REQUEST = "workflow_request"
    SENSITIVE_REPORT = "sensitive_report"
    DECISION_SUPPORT = "decision_support"


class ResponseMode(StrEnum):
    INFORMATIONAL = "informational"
    GUIDANCE = "guidance"
    POLICY_REASONING = "policy_reasoning"
    WORKFLOW_INTAKE = "workflow_intake"
    SENSITIVE_GUARDED = "sensitive_guarded"
    HR_OPS_SUMMARY = "hr_ops_summary"


class AttachmentInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_name": "salary-slip-march-2026.pdf",
                "file_path": "C:/workspace/docs/salary-slip-march-2026.pdf",
            }
        }
    )

    file_name: str | None = Field(default=None, min_length=1, max_length=255)
    file_path: str | None = Field(default=None, min_length=1, max_length=1024)
    content_type: str | None = Field(default=None, min_length=3, max_length=100)
    inline_text: str | None = Field(default=None, min_length=1, max_length=8000)

    @model_validator(mode="after")
    def validate_source(self) -> AttachmentInput:
        if not any([self.file_name, self.file_path, self.inline_text]):
            raise ValueError(
                "Attachment input requires at least one of `file_name`, `file_path`, "
                "or `inline_text`."
            )
        return self

    @property
    def resolved_name(self) -> str:
        if self.file_name:
            return self.file_name
        if self.file_path:
            return Path(self.file_path).name
        return "attachment"

    @property
    def suffix(self) -> str:
        if self.file_path:
            return Path(self.file_path).suffix.lower()
        if self.file_name:
            return Path(self.file_name).suffix.lower()
        return ""


class IntentAssessment(BaseModel):
    primary_intent: ConversationIntent
    secondary_intents: list[ConversationIntent] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)


class SensitivityAssessment(BaseModel):
    level: SensitivityLevel
    matched_keywords: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=2, max_length=500)


class EvidenceItem(BaseModel):
    source_type: Literal["hr_data", "company_rule", "company_structure", "file"]
    title: str = Field(min_length=2, max_length=200)
    snippet: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTraceStep(BaseModel):
    agent: str = Field(min_length=2, max_length=50)
    status: Literal["used", "skipped", "fallback", "error"]
    detail: str = Field(min_length=2)


class OrchestratorRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Berapa sisa cuti saya tahun ini dan apa aturan carry-over?",
                "attachments": [],
            }
        }
    )

    message: str = Field(min_length=1, max_length=4000)
    attachments: list[AttachmentInput] = Field(default_factory=list)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


class HRDataAgentResult(BaseModel):
    topics: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=2)
    records: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class CompanyAgentResult(BaseModel):
    retrieval_mode: Literal["policy_lookup", "structure_lookup", "mixed_lookup"]
    summary: str = Field(min_length=2)
    records: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class FileAgentResult(BaseModel):
    attachments_processed: int = Field(ge=0)
    summary: str = Field(min_length=2)
    extracted_text: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class OrchestratorResponse(BaseModel):
    route: AgentRoute
    intent: IntentAssessment
    sensitivity: SensitivityAssessment
    request_category: ConversationRequestCategory = (
        ConversationRequestCategory.INFORMATIONAL_QUESTION
    )
    response_mode: ResponseMode = ResponseMode.INFORMATIONAL
    answer: str = Field(min_length=2)
    recommended_next_steps: list[str] = Field(default_factory=list)
    used_agents: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)
    extracted_attachment_text: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
