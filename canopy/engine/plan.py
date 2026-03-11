"""Plan engine — estimates cost/carbon impact of IaC changes."""

from __future__ import annotations

from pydantic import BaseModel, Field

from canopy.engine.carbon.client import CarbonIntensityClient
from canopy.engine.carbon.estimator import CarbonEstimator
from canopy.engine.policy import evaluate_budget, evaluate_carbon, evaluate_region
from canopy.engine.providers.aws import INSTANCE_PRICING, INSTANCE_SPECS
from canopy.models.core import CarbonSnapshot, CostSnapshot, WorkloadType
from canopy.models.iac import ChangeAction, PlanSummary, ResourceChange
from canopy.models.policy import Policy, Violation


class ResourceEstimate(BaseModel):
    """Cost and carbon estimate for a single resource change."""

    address: str
    action: ChangeAction
    instance_type: str | None = None
    region: str | None = None
    monthly_cost_usd: float = 0.0
    monthly_carbon_kg_co2: float = 0.0
    # Delta from current state (negative = savings)
    cost_delta_usd: float = 0.0
    carbon_delta_kg: float = 0.0


class PlanEstimate(BaseModel):
    """Full cost/carbon estimate for an IaC plan."""

    source: str
    resources: list[ResourceEstimate] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)

    @property
    def total_monthly_cost_usd(self) -> float:
        return sum(r.monthly_cost_usd for r in self.resources)

    @property
    def total_cost_delta_usd(self) -> float:
        return sum(r.cost_delta_usd for r in self.resources)

    @property
    def total_monthly_carbon_kg(self) -> float:
        return sum(r.monthly_carbon_kg_co2 for r in self.resources)

    @property
    def total_carbon_delta_kg(self) -> float:
        return sum(r.carbon_delta_kg for r in self.resources)

    @property
    def has_blocking_violations(self) -> bool:
        return any(v.severity == "block" for v in self.violations)


def estimate_plan(
    plan: PlanSummary,
    policy: Policy | None = None,
    default_region: str = "us-east-1",
) -> PlanEstimate:
    """Estimate cost and carbon impact of an IaC plan."""
    carbon_client = CarbonIntensityClient()
    estimator = CarbonEstimator(carbon_client)
    pol = policy or Policy()

    resources: list[ResourceEstimate] = []
    violations: list[Violation] = []

    region_tiers = {r.name: r.efficiency_tier.value for r in carbon_client.get_all_regions()}

    for change in plan.changes:
        estimate = _estimate_change(change, estimator, default_region)
        resources.append(estimate)

        # Run policy checks on creates and updates
        if change.action in (ChangeAction.CREATE, ChangeAction.UPDATE):
            region = estimate.region or default_region
            tier = region_tiers.get(region, "bronze")

            cost_snap = CostSnapshot(
                workload_id=change.address,
                hourly_cost_usd=estimate.monthly_cost_usd / 730,
                monthly_cost_usd=estimate.monthly_cost_usd,
            )
            violations.extend(evaluate_budget(cost_snap, pol, change.address, change.name))

            carbon_snap = CarbonSnapshot(
                workload_id=change.address,
                region=region,
                grid_intensity_gco2_kwh=0,
                estimated_power_kw=0,
                hourly_carbon_gco2=estimate.monthly_carbon_kg_co2 * 1000 / 730,
                monthly_carbon_kg_co2=estimate.monthly_carbon_kg_co2,
            )
            violations.extend(evaluate_carbon(carbon_snap, pol, change.address, change.name))
            violations.extend(evaluate_region(region, tier, pol, change.address, change.name))

        # Check tagging on creates
        if change.action == ChangeAction.CREATE and pol.tagging.required_tags:
            missing = [t for t in pol.tagging.required_tags if t not in change.tags]
            if missing:
                violations.append(
                    Violation(
                        severity=pol.tagging.severity,
                        policy_name="tagging.required_tags",
                        message=f"Missing required tags: {', '.join(missing)}",
                        resource_id=change.address,
                        resource_name=change.name,
                    )
                )

    return PlanEstimate(source=plan.source, resources=resources, violations=violations)


def _estimate_change(
    change: ResourceChange,
    estimator: CarbonEstimator,
    default_region: str,
) -> ResourceEstimate:
    """Estimate cost and carbon for a single resource change."""
    region = change.after_region or change.before_region or default_region

    if change.action == ChangeAction.DELETE:
        # Deleting saves money and carbon
        before_cost = _get_monthly_cost(change.before_instance_type)
        before_carbon = _estimate_carbon(
            estimator, change.before_instance_type, change.before_region or default_region
        )
        return ResourceEstimate(
            address=change.address,
            action=change.action,
            instance_type=change.before_instance_type,
            region=change.before_region,
            monthly_cost_usd=0.0,
            monthly_carbon_kg_co2=0.0,
            cost_delta_usd=-before_cost,
            carbon_delta_kg=-before_carbon,
        )

    if change.action == ChangeAction.CREATE:
        after_cost = _get_monthly_cost(change.after_instance_type)
        after_carbon = _estimate_carbon(estimator, change.after_instance_type, region)
        return ResourceEstimate(
            address=change.address,
            action=change.action,
            instance_type=change.after_instance_type,
            region=region,
            monthly_cost_usd=after_cost,
            monthly_carbon_kg_co2=after_carbon,
            cost_delta_usd=after_cost,
            carbon_delta_kg=after_carbon,
        )

    if change.action == ChangeAction.UPDATE:
        before_cost = _get_monthly_cost(change.before_instance_type)
        after_cost = _get_monthly_cost(change.after_instance_type)
        before_region = change.before_region or default_region
        before_carbon = _estimate_carbon(estimator, change.before_instance_type, before_region)
        after_carbon = _estimate_carbon(estimator, change.after_instance_type, region)
        return ResourceEstimate(
            address=change.address,
            action=change.action,
            instance_type=change.after_instance_type,
            region=region,
            monthly_cost_usd=after_cost,
            monthly_carbon_kg_co2=after_carbon,
            cost_delta_usd=after_cost - before_cost,
            carbon_delta_kg=after_carbon - before_carbon,
        )

    # NO_OP or READ
    return ResourceEstimate(
        address=change.address,
        action=change.action,
        instance_type=change.instance_type,
        region=region,
    )


def _get_monthly_cost(instance_type: str | None) -> float:
    """Get monthly cost estimate from static pricing."""
    if not instance_type:
        return 0.0
    hourly = INSTANCE_PRICING.get(instance_type, 0.0)
    return hourly * 730


def _estimate_carbon(
    estimator: CarbonEstimator,
    instance_type: str | None,
    region: str,
) -> float:
    """Estimate monthly carbon for an instance type in a region."""
    if not instance_type:
        return 0.0
    from canopy.models.core import Workload

    vcpus, memory_gb = INSTANCE_SPECS.get(instance_type, (0, 0.0))
    gpu_count = 1 if instance_type.startswith(("p", "g")) else 0

    workload = Workload(
        id="plan-estimate",
        name="plan-estimate",
        provider="aws",
        region=region,
        workload_type=WorkloadType.COMPUTE,
        instance_type=instance_type,
        vcpus=vcpus,
        memory_gb=memory_gb,
        gpu_count=gpu_count,
        avg_cpu_percent=50.0,  # Assume 50% utilization for planning
    )
    carbon = estimator.estimate(workload)
    return carbon.monthly_carbon_kg_co2
