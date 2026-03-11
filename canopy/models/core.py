"""Core data models for Canopy."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class WorkloadType(StrEnum):
    COMPUTE = "compute"
    CONTAINER = "container"
    SERVERLESS = "serverless"
    DATABASE = "database"
    STORAGE = "storage"
    AI_INFERENCE = "ai_inference"
    AI_TRAINING = "ai_training"


class EfficiencyTier(StrEnum):
    PLATINUM = "platinum"  # CFE% >= 95% or intensity <= 20
    GOLD = "gold"  # CFE% >= 75% or intensity <= 100
    SILVER = "silver"  # CFE% >= 50% or intensity <= 300
    BRONZE = "bronze"  # Everything else


class Region(BaseModel):
    """A cloud region with its carbon characteristics."""

    provider: str
    name: str
    location: str
    cfe_percent: float = Field(ge=0, le=100, description="Carbon-Free Energy percentage")
    grid_intensity_gco2_kwh: float = Field(ge=0, description="gCO2eq per kWh")

    @property
    def efficiency_tier(self) -> EfficiencyTier:
        if self.cfe_percent >= 95 or self.grid_intensity_gco2_kwh <= 20:
            return EfficiencyTier.PLATINUM
        if self.cfe_percent >= 75 or self.grid_intensity_gco2_kwh <= 100:
            return EfficiencyTier.GOLD
        if self.cfe_percent >= 50 or self.grid_intensity_gco2_kwh <= 300:
            return EfficiencyTier.SILVER
        return EfficiencyTier.BRONZE


class Workload(BaseModel):
    """A cloud workload (instance, container, function, etc.)."""

    id: str
    name: str
    provider: str
    region: str
    workload_type: WorkloadType
    instance_type: str | None = None
    vcpus: int = 0
    memory_gb: float = 0.0
    gpu_count: int = 0
    gpu_type: str | None = None
    avg_cpu_percent: float = Field(default=0.0, ge=0, le=100)
    avg_memory_percent: float = Field(default=0.0, ge=0, le=100)
    avg_gpu_percent: float = Field(default=0.0, ge=0, le=100)
    tags: dict[str, str] = Field(default_factory=dict)
    launched_at: datetime | None = None


class CostSnapshot(BaseModel):
    """Cost data for a workload at a point in time."""

    workload_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    hourly_cost_usd: float = Field(ge=0)
    monthly_cost_usd: float = Field(ge=0)
    currency: str = "USD"

    @property
    def daily_cost_usd(self) -> float:
        return self.hourly_cost_usd * 24


class CarbonSnapshot(BaseModel):
    """Carbon emissions data for a workload at a point in time."""

    workload_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    region: str
    grid_intensity_gco2_kwh: float = Field(ge=0)
    estimated_power_kw: float = Field(ge=0, description="Estimated power draw in kW")
    hourly_carbon_gco2: float = Field(ge=0, description="gCO2eq per hour")
    monthly_carbon_kg_co2: float = Field(ge=0, description="kg CO2eq per month")

    @property
    def daily_carbon_kg_co2(self) -> float:
        return self.hourly_carbon_gco2 * 24 / 1000


class EcoWeight(BaseModel):
    """The unified efficiency score combining cost and carbon."""

    workload_id: str
    workload_name: str
    timestamp: datetime = Field(default_factory=datetime.now)
    cost: CostSnapshot
    carbon: CarbonSnapshot
    alpha: float = Field(default=0.5, ge=0, le=1, description="Cost weight")
    beta: float = Field(default=0.5, ge=0, le=1, description="Carbon weight")
    budget_hourly_usd: float = Field(gt=0, description="Allocated hourly budget")
    carbon_hourly_gco2: float = Field(gt=0, description="Allocated hourly carbon budget")

    @property
    def normalized_cost(self) -> float:
        return self.cost.hourly_cost_usd / self.budget_hourly_usd

    @property
    def normalized_carbon(self) -> float:
        return self.carbon.hourly_carbon_gco2 / self.carbon_hourly_gco2

    @property
    def score(self) -> float:
        """EcoWeight score. 1.0 = on budget. >1.0 = over. <1.0 = headroom."""
        return self.alpha * self.normalized_cost + self.beta * self.normalized_carbon

    @property
    def is_over_budget(self) -> bool:
        return self.score > 1.0

    @property
    def status(self) -> str:
        score = self.score
        if score <= 0.7:
            return "excellent"
        if score <= 0.9:
            return "good"
        if score <= 1.0:
            return "warning"
        if score <= 1.2:
            return "over"
        return "critical"
