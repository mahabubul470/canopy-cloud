"""Workload optimization detectors for Canopy."""

from canopy.engine.carbon.client import CarbonIntensityClient
from canopy.engine.carbon.estimator import CarbonEstimator
from canopy.engine.providers.aws import INSTANCE_PRICING, INSTANCE_SPECS
from canopy.models.core import (
    CarbonSnapshot,
    CostSnapshot,
    Recommendation,
    RecommendationType,
    Workload,
)

# Maps instance types to the next smaller size in the same family.
DOWNGRADE_MAP: dict[str, str] = {
    "t3.xlarge": "t3.large",
    "t3.large": "t3.medium",
    "t3.medium": "t3.small",
    "t3.small": "t3.micro",
    "m5.4xlarge": "m5.2xlarge",
    "m5.2xlarge": "m5.xlarge",
    "m5.xlarge": "m5.large",
    "c5.4xlarge": "c5.2xlarge",
    "c5.2xlarge": "c5.xlarge",
    "c5.xlarge": "c5.large",
    "r5.2xlarge": "r5.xlarge",
    "r5.xlarge": "r5.large",
    "g5.2xlarge": "g5.xlarge",
}


def detect_idle(
    workload: Workload,
    cost: CostSnapshot,
    carbon: CarbonSnapshot,
    threshold: float = 2.0,
) -> Recommendation | None:
    """Flag workloads with avg CPU below threshold as idle (candidate for termination)."""
    if workload.avg_cpu_percent >= threshold:
        return None

    return Recommendation(
        workload_id=workload.id,
        workload_name=workload.name,
        recommendation_type=RecommendationType.IDLE,
        reason=(
            f"Avg CPU {workload.avg_cpu_percent:.1f}% < {threshold}%"
            f" over 7 days — consider terminating"
        ),
        current_instance_type=workload.instance_type,
        estimated_monthly_cost_savings_usd=cost.monthly_cost_usd,
        estimated_monthly_carbon_savings_kg=carbon.monthly_carbon_kg_co2,
    )


def detect_rightsize(
    workload: Workload,
    cost: CostSnapshot,
    carbon: CarbonSnapshot,
    threshold: float = 15.0,
) -> Recommendation | None:
    """Flag workloads with avg CPU below threshold for downsizing."""
    if workload.avg_cpu_percent >= threshold:
        return None

    instance_type = workload.instance_type or ""
    suggested = DOWNGRADE_MAP.get(instance_type)
    if not suggested:
        return None

    suggested_hourly = INSTANCE_PRICING.get(suggested, 0.0)
    current_hourly = cost.hourly_cost_usd
    cost_savings = (current_hourly - suggested_hourly) * 730

    # Estimate carbon savings proportional to vCPU reduction
    current_vcpus = INSTANCE_SPECS.get(instance_type, (0, 0.0))[0]
    suggested_vcpus = INSTANCE_SPECS.get(suggested, (0, 0.0))[0]
    if current_vcpus > 0:
        carbon_ratio = 1.0 - (suggested_vcpus / current_vcpus)
    else:
        carbon_ratio = 0.0
    carbon_savings = carbon.monthly_carbon_kg_co2 * carbon_ratio

    return Recommendation(
        workload_id=workload.id,
        workload_name=workload.name,
        recommendation_type=RecommendationType.RIGHTSIZE,
        reason=(
            f"Avg CPU {workload.avg_cpu_percent:.1f}% < {threshold}% over 7 days"
            f" — downsize {instance_type} → {suggested}"
        ),
        current_instance_type=instance_type,
        suggested_instance_type=suggested,
        estimated_monthly_cost_savings_usd=max(cost_savings, 0.0),
        estimated_monthly_carbon_savings_kg=max(carbon_savings, 0.0),
    )


def detect_region_move(
    workload: Workload,
    carbon: CarbonSnapshot,
    carbon_client: CarbonIntensityClient,
) -> Recommendation | None:
    """Suggest moving to a greener region if significantly cleaner options exist."""
    current_intensity = carbon.grid_intensity_gco2_kwh
    all_regions = carbon_client.get_all_regions()

    # Find the greenest region for the same provider
    same_provider = [r for r in all_regions if r.provider == workload.provider]
    if not same_provider:
        return None

    greenest = min(same_provider, key=lambda r: r.grid_intensity_gco2_kwh)

    # Only recommend if the greenest region is at least 50% cleaner
    if greenest.grid_intensity_gco2_kwh >= current_intensity * 0.5:
        return None

    if greenest.name == workload.region:
        return None

    # Estimate carbon savings: proportional to intensity reduction
    intensity_ratio = 1.0 - (greenest.grid_intensity_gco2_kwh / current_intensity)
    carbon_savings = carbon.monthly_carbon_kg_co2 * intensity_ratio

    # Re-estimate carbon in the new region for accuracy
    estimator = CarbonEstimator(carbon_client)
    new_workload = workload.model_copy(update={"region": greenest.name})
    new_carbon = estimator.estimate(new_workload)
    carbon_savings = carbon.monthly_carbon_kg_co2 - new_carbon.monthly_carbon_kg_co2

    return Recommendation(
        workload_id=workload.id,
        workload_name=workload.name,
        recommendation_type=RecommendationType.REGION_MOVE,
        reason=(
            f"{workload.region} ({current_intensity:.0f} gCO₂/kWh)"
            f" → {greenest.name} ({greenest.grid_intensity_gco2_kwh:.0f} gCO₂/kWh)"
        ),
        current_region=workload.region,
        suggested_region=greenest.name,
        estimated_monthly_carbon_savings_kg=max(carbon_savings, 0.0),
    )
