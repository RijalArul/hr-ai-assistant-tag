from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from shared import (
    ActionPriority,
    ActionStatus,
    ActionType,
    DeliveryChannel,
    RuleTrigger,
    SensitivityLevel,
    WebhookEvent,
)


def _dedupe_preserve_order[T](values: list[T]) -> list[T]:
    seen: set[T] = set()
    result: list[T] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


class DocumentGenerationPayload(BaseModel):
    type: Literal["document_generation"] = "document_generation"
    document_type: str = Field(min_length=2, max_length=100)
    template_key: str | None = Field(default=None, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    delivery_note: str | None = Field(default=None, max_length=500)


class CounselingTaskPayload(BaseModel):
    type: Literal["counseling_task"] = "counseling_task"
    topic: str = Field(min_length=2, max_length=120)
    assigned_role: str = Field(default="hr_admin", min_length=2, max_length=50)
    due_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)


class FollowupChatPayload(BaseModel):
    type: Literal["followup_chat"] = "followup_chat"
    target_audience: str = Field(default="employee", min_length=2, max_length=50)
    message_template: str = Field(min_length=2, max_length=2000)
    scheduled_at: datetime | None = None


class EscalationPayload(BaseModel):
    type: Literal["escalation"] = "escalation"
    reason: str = Field(min_length=2, max_length=500)
    target_role: str = Field(min_length=2, max_length=50)
    escalation_level: int = Field(default=1, ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)


class CustomWebhookPayload(BaseModel):
    type: Literal["custom_webhook"] = "custom_webhook"
    event_name: str = Field(min_length=2, max_length=100)
    payload_template: dict[str, Any] = Field(default_factory=dict)
    target_reference: str | None = Field(default=None, max_length=255)


ActionPayload = Annotated[
    DocumentGenerationPayload
    | CounselingTaskPayload
    | FollowupChatPayload
    | EscalationPayload
    | CustomWebhookPayload,
    Field(discriminator="type"),
]

ACTION_TYPE_TO_PAYLOAD_MODEL = {
    ActionType.DOCUMENT_GENERATION: DocumentGenerationPayload,
    ActionType.COUNSELING_TASK: CounselingTaskPayload,
    ActionType.FOLLOWUP_CHAT: FollowupChatPayload,
    ActionType.ESCALATION: EscalationPayload,
    ActionType.CUSTOM_WEBHOOK: CustomWebhookPayload,
}


class ActionCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "40000000-0000-0000-0000-000000000001",
                "title": "Generate salary slip for March 2026",
                "summary": "Prepare a payroll document and deliver it to the employee.",
                "priority": "medium",
                "sensitivity": "low",
                "delivery_channels": ["email", "in_app"],
                "payload": {
                    "type": "document_generation",
                    "document_type": "salary_slip",
                    "template_key": "payroll_salary_slip_v1",
                    "parameters": {
                        "month": 3,
                        "year": 2026,
                    },
                },
            }
        }
    )

    conversation_id: UUID
    title: str = Field(min_length=2, max_length=160)
    summary: str | None = Field(default=None, max_length=500)
    priority: ActionPriority = ActionPriority.MEDIUM
    sensitivity: SensitivityLevel = SensitivityLevel.LOW
    delivery_channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.IN_APP],
        min_length=1,
    )
    payload: ActionPayload
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("delivery_channels")
    @classmethod
    def dedupe_delivery_channels(
        cls,
        value: list[DeliveryChannel],
    ) -> list[DeliveryChannel]:
        return _dedupe_preserve_order(value)


class ActionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    summary: str | None = Field(default=None, max_length=500)
    priority: ActionPriority | None = None
    sensitivity: SensitivityLevel | None = None
    status: ActionStatus | None = None
    delivery_channels: list[DeliveryChannel] | None = Field(default=None, min_length=1)
    metadata: dict[str, Any] | None = None

    @field_validator("delivery_channels")
    @classmethod
    def dedupe_delivery_channels(
        cls,
        value: list[DeliveryChannel] | None,
    ) -> list[DeliveryChannel] | None:
        if value is None:
            return None
        return _dedupe_preserve_order(value)

    @model_validator(mode="after")
    def validate_manual_status_updates(self) -> ActionUpdateRequest:
        if self.status in {ActionStatus.COMPLETED, ActionStatus.FAILED}:
            raise ValueError(
                "Use the action execution flow for terminal statuses such as "
                "`completed` or `failed`."
            )
        return self


class ActionExecutionRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "delivery_channels": ["manual_review"],
                "trigger_delivery": True,
                "executor_note": "Escalated for HR review before outbound delivery.",
            }
        }
    )

    delivery_channels: list[DeliveryChannel] | None = Field(default=None, min_length=1)
    trigger_delivery: bool = True
    executor_note: str | None = Field(default=None, max_length=500)

    @field_validator("delivery_channels")
    @classmethod
    def dedupe_delivery_channels(
        cls,
        value: list[DeliveryChannel] | None,
    ) -> list[DeliveryChannel] | None:
        if value is None:
            return None
        return _dedupe_preserve_order(value)


class ActionLogResponse(BaseModel):
    id: UUID
    action_id: UUID
    event_name: str
    status: ActionStatus
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ActionDeliveryResponse(BaseModel):
    id: UUID
    action_id: UUID
    channel: DeliveryChannel
    delivery_status: str
    target_reference: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ActionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "50000000-0000-0000-0000-000000000001",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "employee_id": "20000000-0000-0000-0000-000000000004",
                "conversation_id": "40000000-0000-0000-0000-000000000001",
                "type": "document_generation",
                "title": "Generate salary slip for March 2026",
                "summary": "Prepare a payroll document and deliver it to the employee.",
                "status": "pending",
                "priority": "medium",
                "sensitivity": "low",
                "delivery_channels": ["email", "in_app"],
                "payload": {
                    "type": "document_generation",
                    "document_type": "salary_slip",
                    "template_key": "payroll_salary_slip_v1",
                    "parameters": {
                        "month": 3,
                        "year": 2026,
                    },
                },
                "execution_result": None,
                "metadata": {},
                "last_executed_at": None,
                "created_at": "2026-04-03T10:15:00Z",
                "updated_at": "2026-04-03T10:15:00Z",
            }
        }
    )

    id: UUID
    company_id: UUID
    employee_id: UUID
    conversation_id: UUID
    type: ActionType
    title: str
    summary: str | None = None
    status: ActionStatus
    priority: ActionPriority
    sensitivity: SensitivityLevel
    delivery_channels: list[DeliveryChannel]
    payload: ActionPayload
    execution_result: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_executed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("delivery_channels")
    @classmethod
    def dedupe_delivery_channels(
        cls,
        value: list[DeliveryChannel],
    ) -> list[DeliveryChannel]:
        return _dedupe_preserve_order(value)

    @model_validator(mode="after")
    def validate_type_matches_payload(self) -> ActionResponse:
        if self.type != ActionType(self.payload.type):
            raise ValueError("action type must match payload type")
        return self


class ActionListResponse(BaseModel):
    items: list[ActionResponse]
    total: int


class ActionExecutionResponse(BaseModel):
    action: ActionResponse
    delivery_channels: list[DeliveryChannel]
    delivery_requested: bool
    execution_log: ActionLogResponse | None = None
    delivery_requests: list[ActionDeliveryResponse] = Field(default_factory=list)
    webhook_deliveries_queued: int = 0


class ActionResultResponse(BaseModel):
    action_id: UUID
    status: ActionStatus
    execution_result: dict[str, Any] | None = None
    last_executed_at: datetime | None = None


class RuleActionConfig(BaseModel):
    action_type: ActionType
    title_template: str = Field(min_length=2, max_length=160)
    summary_template: str | None = Field(default=None, max_length=500)
    priority: ActionPriority = ActionPriority.MEDIUM
    delivery_channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.IN_APP],
        min_length=1,
    )
    payload_template: dict[str, Any] = Field(default_factory=dict)

    @field_validator("delivery_channels")
    @classmethod
    def dedupe_delivery_channels(
        cls,
        value: list[DeliveryChannel],
    ) -> list[DeliveryChannel]:
        return _dedupe_preserve_order(value)

    @model_validator(mode="after")
    def validate_payload_template(self) -> RuleActionConfig:
        if "type" in self.payload_template:
            raise ValueError("payload_template must not define `type`; it is derived from action_type.")

        payload_model = ACTION_TYPE_TO_PAYLOAD_MODEL[self.action_type]
        payload_model.model_validate(
            {
                "type": self.action_type.value,
                **self.payload_template,
            }
        )
        return self


class RuleCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Payroll document follow-up",
                "description": "Generate a salary slip when the payroll request intent is resolved.",
                "trigger": "conversation_resolved",
                "intent_key": "payroll_document_request",
                "sensitivity_threshold": "medium",
                "is_enabled": True,
                "actions": [
                    {
                        "action_type": "document_generation",
                        "title_template": "Generate salary slip",
                        "summary_template": "Prepare payroll document for delivery.",
                        "priority": "medium",
                        "delivery_channels": ["email", "in_app"],
                        "payload_template": {
                            "document_type": "salary_slip",
                            "template_key": "payroll_salary_slip_v1",
                        },
                    }
                ],
            }
        }
    )

    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    trigger: RuleTrigger = RuleTrigger.CONVERSATION_RESOLVED
    intent_key: str = Field(min_length=2, max_length=100)
    sensitivity_threshold: SensitivityLevel | None = None
    is_enabled: bool = True
    actions: list[RuleActionConfig] = Field(min_length=1)


class RuleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    trigger: RuleTrigger | None = None
    intent_key: str | None = Field(default=None, min_length=2, max_length=100)
    sensitivity_threshold: SensitivityLevel | None = None
    is_enabled: bool | None = None
    actions: list[RuleActionConfig] | None = Field(default=None, min_length=1)


class RuleResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    description: str | None = None
    trigger: RuleTrigger
    intent_key: str
    sensitivity_threshold: SensitivityLevel | None = None
    is_enabled: bool
    actions: list[RuleActionConfig]
    created_at: datetime
    updated_at: datetime


class RuleListResponse(BaseModel):
    items: list[RuleResponse]
    total: int


class WebhookCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Primary HRIS webhook",
                "target_url": "https://example.com/webhooks/hr-ai",
                "subscribed_events": [
                    "action.created",
                    "action.executed",
                ],
                "secret": "super-secret-signing-key",
                "is_active": True,
            }
        }
    )

    name: str = Field(min_length=2, max_length=120)
    target_url: HttpUrl
    subscribed_events: list[WebhookEvent] = Field(min_length=1)
    secret: str = Field(min_length=16, max_length=200)
    is_active: bool = True

    @field_validator("subscribed_events")
    @classmethod
    def dedupe_subscribed_events(
        cls,
        value: list[WebhookEvent],
    ) -> list[WebhookEvent]:
        return _dedupe_preserve_order(value)


class WebhookUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    target_url: HttpUrl | None = None
    subscribed_events: list[WebhookEvent] | None = Field(default=None, min_length=1)
    secret: str | None = Field(default=None, min_length=16, max_length=200)
    is_active: bool | None = None

    @field_validator("subscribed_events")
    @classmethod
    def dedupe_subscribed_events(
        cls,
        value: list[WebhookEvent] | None,
    ) -> list[WebhookEvent] | None:
        if value is None:
            return None
        return _dedupe_preserve_order(value)


class WebhookResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    target_url: HttpUrl
    subscribed_events: list[WebhookEvent]
    secret_preview: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WebhookListResponse(BaseModel):
    items: list[WebhookResponse]
    total: int


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Resource not found.",
            }
        }
    )

    detail: str
