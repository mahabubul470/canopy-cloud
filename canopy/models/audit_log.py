"""Audit log data models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    AUDIT_RUN = "audit_run"
    APPLY_STARTED = "apply_started"
    APPLY_COMPLETED = "apply_completed"
    APPLY_FAILED = "apply_failed"
    CARL_DECISION = "carl_decision"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"


class AuditEntry(BaseModel):
    """A single entry in the audit log."""

    timestamp: datetime = Field(default_factory=datetime.now)
    action: ActionType
    workload_id: str | None = None
    workload_name: str | None = None
    provider: str | None = None
    region: str | None = None
    details: dict[str, object] = Field(default_factory=dict)
    user: str | None = None
    dry_run: bool = False
