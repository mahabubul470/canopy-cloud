"""Models for IaC plan analysis."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ChangeAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_OP = "no-op"
    READ = "read"


class ResourceChange(BaseModel):
    """A single resource change from an IaC plan."""

    address: str  # e.g., "aws_instance.api_server"
    resource_type: str  # e.g., "aws_instance"
    name: str  # e.g., "api_server"
    provider: str = "aws"
    action: ChangeAction
    region: str | None = None
    instance_type: str | None = None
    count: int = 1
    tags: dict[str, str] = Field(default_factory=dict)

    # Before values (for updates/deletes)
    before_instance_type: str | None = None
    before_region: str | None = None

    # After values (for creates/updates)
    after_instance_type: str | None = None
    after_region: str | None = None


class PlanSummary(BaseModel):
    """Summary of an IaC plan analysis."""

    source: str  # "terraform", "pulumi", "opentofu"
    changes: list[ResourceChange] = Field(default_factory=list)

    @property
    def creates(self) -> list[ResourceChange]:
        return [c for c in self.changes if c.action == ChangeAction.CREATE]

    @property
    def updates(self) -> list[ResourceChange]:
        return [c for c in self.changes if c.action == ChangeAction.UPDATE]

    @property
    def deletes(self) -> list[ResourceChange]:
        return [c for c in self.changes if c.action == ChangeAction.DELETE]

    @property
    def has_changes(self) -> bool:
        return any(c.action != ChangeAction.NO_OP for c in self.changes)
