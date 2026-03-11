"""Audit engine — scans infrastructure and computes EcoWeight scores."""

from canopy.engine.carbon.client import CarbonIntensityClient
from canopy.engine.carbon.estimator import CarbonEstimator
from canopy.engine.providers.aws import AWSProvider
from canopy.engine.providers.base import CloudProvider
from canopy.models.core import EcoWeight

# Default budget allocations when no policy is configured
DEFAULT_BUDGET_HOURLY_USD = 1.0
DEFAULT_CARBON_HOURLY_GCO2 = 100.0


def get_provider(name: str) -> CloudProvider:
    providers: dict[str, type[CloudProvider]] = {
        "aws": AWSProvider,
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
    cloud = get_provider(provider)
    carbon_client = CarbonIntensityClient()
    estimator = CarbonEstimator(carbon_client)

    workloads = cloud.list_workloads(region=region)
    results: list[EcoWeight] = []

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

    results.sort(key=lambda x: x.score, reverse=True)
    return results
