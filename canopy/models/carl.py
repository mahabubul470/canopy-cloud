"""CARL (Carbon-Aware Resource Launcher) scheduler models."""

from enum import StrEnum

from pydantic import BaseModel, Field


class CarlStrategy(StrEnum):
    PASS_THROUGH = "pass_through"
    THROTTLE = "throttle"
    DEFER = "defer"


class Urgency(StrEnum):
    CRITICAL = "critical"
    NORMAL = "normal"
    FLEXIBLE = "flexible"


class CarlDecision(BaseModel):
    """Decision made by the CARL scheduler."""

    strategy: CarlStrategy
    reason: str
    current_intensity: float = Field(ge=0, description="Current grid intensity gCO2/kWh")
    throttle_factor: float = Field(default=1.0, ge=0, le=1.0)
    defer_until: str | None = None
    recommended_window: str | None = None
