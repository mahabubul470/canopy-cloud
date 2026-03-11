"""Audit engine — scans infrastructure and computes EcoWeight scores."""

from __future__ import annotations

from canopy.config import CanopyConfig
from canopy.engine.carbon.client import CarbonIntensityClient
from canopy.engine.carbon.estimator import CarbonEstimator
from canopy.engine.detectors import detect_idle, detect_region_move, detect_rightsize
from canopy.engine.providers.aws import AWSProvider
from canopy.engine.providers.base import CloudProvider
from canopy.engine.providers.gcp import GCPProvider
from canopy.models.core import EcoWeight, Recommendation, SavingsSummary

# Default budget allocations when no policy is configured
DEFAULT_BUDGET_HOURLY_USD = 1.0
DEFAULT_CARBON_HOURLY_GCO2 = 100.0


def get_provider(name: str) -> CloudProvider:
    providers: dict[str, type[CloudProvider]] = {
        "aws": AWSProvider,
        "gcp": GCPProvider,
    }
    provider_cls = providers.get(name)
    if not provider_cls:
        raise ValueError(f"Unknown provider: {name}. Available: {', '.join(providers)}")
    return provider_cls()


def run_audit(
    provider: str = "aws",
    region: str | None = None,
    alpha: float = 0.5,
    beta: float = 0.5,
    budget_hourly_usd: float = DEFAULT_BUDGET_HOURLY_USD,
    carbon_hourly_gco2: float = DEFAULT_CARBON_HOURLY_GCO2,
) -> list[EcoWeight]:
    """Run a full audit: discover workloads, estimate cost + carbon, compute EcoWeight."""
    results, _ = run_audit_with_recommendations(
        provider=provider,
        region=region,
        alpha=alpha,
        beta=beta,
        budget_hourly_usd=budget_hourly_usd,
        carbon_hourly_gco2=carbon_hourly_gco2,
    )
    return results


def run_audit_with_recommendations(
    provider: str = "aws",
    region: str | None = None,
    alpha: float = 0.5,
    beta: float = 0.5,
    budget_hourly_usd: float = DEFAULT_BUDGET_HOURLY_USD,
    carbon_hourly_gco2: float = DEFAULT_CARBON_HOURLY_GCO2,
    config: CanopyConfig | None = None,
) -> tuple[list[EcoWeight], SavingsSummary]:
    """Run audit with recommendations: discover, score, detect, recommend."""
    cfg = config or CanopyConfig()
    alpha = alpha if config is None else cfg.alpha
    beta = beta if config is None else cfg.beta
    budget_hourly_usd = budget_hourly_usd if config is None else cfg.budget_hourly_usd
    carbon_hourly_gco2 = carbon_hourly_gco2 if config is None else cfg.carbon_hourly_gco2

    cloud = get_provider(provider)
    carbon_client = CarbonIntensityClient()
    estimator = CarbonEstimator(carbon_client)

    workloads = cloud.list_workloads(region=region)
    results: list[EcoWeight] = []
    recommendations: list[Recommendation] = []

    for workload in workloads:
        cost = cloud.get_cost(workload)
        carbon = estimator.estimate(workload)

        ew = EcoWeight(
            workload_id=workload.id,
            workload_name=workload.name,
            cost=cost,
            carbon=carbon,
            alpha=alpha,
            beta=beta,
            budget_hourly_usd=budget_hourly_usd,
            carbon_hourly_gco2=carbon_hourly_gco2,
        )
        results.append(ew)

        # Detect optimization opportunities (idle takes priority over rightsize)
        idle_rec = detect_idle(workload, cost, carbon, threshold=cfg.idle_cpu_threshold)
        if idle_rec:
            recommendations.append(idle_rec)
        else:
            rightsize_rec = detect_rightsize(
                workload, cost, carbon, threshold=cfg.rightsize_cpu_threshold
            )
            if rightsize_rec:
                recommendations.append(rightsize_rec)

        region_rec = detect_region_move(workload, carbon, carbon_client)
        if region_rec:
            recommendations.append(region_rec)

    results.sort(key=lambda x: x.score, reverse=True)

    summary = SavingsSummary(
        total_monthly_cost_savings_usd=sum(
            r.estimated_monthly_cost_savings_usd for r in recommendations
        ),
        total_monthly_carbon_savings_kg=sum(
            r.estimated_monthly_carbon_savings_kg for r in recommendations
        ),
        recommendation_count=len(recommendations),
        recommendations=recommendations,
    )

    return results, summary
