"""Policy models for Canopy governance."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    INFO = "info"


class BudgetPolicy(BaseModel):
    """Monthly budget constraints."""

    monthly_cap_usd: float | None = Field(default=None, ge=0)
    alert_threshold: float = Field(default=0.8, ge=0, le=1)


class CarbonPolicy(BaseModel):
    """Carbon emission constraints."""

    monthly_cap_kg_co2: float | None = Field(default=None, ge=0)
    min_region_tier: str = Field(default="bronze")
    allowed_regions: list[str] = Field(default_factory=list)


class EcoWeightPolicy(BaseModel):
    """EcoWeight threshold constraints."""

    max_score: float = Field(default=1.2, gt=0)
    alert_threshold: float = Field(default=0.9, gt=0)


class TaggingPolicy(BaseModel):
    """Resource tagging requirements."""

    required_tags: list[str] = Field(default_factory=list)
    severity: Severity = Severity.WARN


class Policy(BaseModel):
    """Complete Canopy policy definition."""

    version: str = "1.0"
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)
    carbon: CarbonPolicy = Field(default_factory=CarbonPolicy)
    ecoweight: EcoWeightPolicy = Field(default_factory=EcoWeightPolicy)
    tagging: TaggingPolicy = Field(default_factory=TaggingPolicy)


class Violation(BaseModel):
    """A policy violation detected during evaluation."""

    severity: Severity
    policy_name: str
    message: str
    resource_id: str | None = None
    resource_name: str | None = None


class PolicyResult(BaseModel):
    """Result of evaluating a set of resources against a policy."""

    violations: list[Violation] = Field(default_factory=list)
    resource_count: int = 0

    @property
    def has_blocking_violations(self) -> bool:
        return any(v.severity == Severity.BLOCK for v in self.violations)

    @property
    def blocking_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.BLOCK)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.WARN)

    @property
    def info_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.INFO)
