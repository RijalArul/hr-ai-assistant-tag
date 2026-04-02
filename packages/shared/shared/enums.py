from enum import StrEnum


class EmploymentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PROBATION = "probation"
    RESIGNED = "resigned"
    TERMINATED = "terminated"
    CONTRACT_END = "contract_end"


class EmploymentType(StrEnum):
    PERMANENT = "permanent"
    CONTRACT = "contract"
    INTERN = "intern"
    FREELANCE = "freelance"


class LeaveRecordType(StrEnum):
    BALANCE = "balance"
    REQUEST = "request"


class LeaveStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    WFH = "wfh"
    LEAVE = "leave"
    HOLIDAY = "holiday"


class PayrollPaymentStatus(StrEnum):
    DRAFT = "draft"
    PROCESSED = "processed"
    PAID = "paid"
    FAILED = "failed"


class ActionType(StrEnum):
    DOCUMENT_GENERATION = "document_generation"
    COUNSELING_TASK = "counseling_task"
    FOLLOWUP_CHAT = "followup_chat"
    ESCALATION = "escalation"
    CUSTOM_WEBHOOK = "custom_webhook"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class SensitivityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DeliveryChannel(StrEnum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
    MANUAL_REVIEW = "manual_review"
