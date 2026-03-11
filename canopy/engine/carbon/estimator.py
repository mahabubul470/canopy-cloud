"""Carbon emissions estimator for cloud workloads."""

from canopy.engine.carbon.client import CarbonIntensityClient
from canopy.models.core import CarbonSnapshot, Workload

# Estimated power draw per vCPU in kW (typical modern server)
POWER_PER_VCPU_KW = 0.007

# Base power overhead per instance (cooling, memory, networking) in kW
BASE_POWER_KW = 0.010

# GPU power draw estimates in kW
GPU_POWER_KW: dict[str, float] = {
    "NVIDIA": 0.350,  # Average across H100/A100/T4
}
DEFAULT_GPU_POWER_KW = 0.300

# Average PUE (Power Usage Effectiveness) for major cloud providers
PROVIDER_PUE: dict[str, float] = {
    "aws": 1.135,
    "gcp": 1.10,
    "azure": 1.18,
}
DEFAULT_PUE = 1.2


class CarbonEstimator:
    """Estimates carbon emissions for workloads based on power draw and grid intensity."""

    def __init__(self, carbon_client: CarbonIntensityClient | None = None) -> None:
        self._carbon_client = carbon_client or CarbonIntensityClient()

    def estimate_power_kw(self, workload: Workload) -> float:
        """Estimate the power draw of a workload in kW."""
        cpu_util = workload.avg_cpu_percent / 100.0 if workload.avg_cpu_percent > 0 else 0.5

        # CPU power (scales with utilization — idle CPUs still draw ~40% of peak)
        cpu_power = workload.vcpus * POWER_PER_VCPU_KW * (0.4 + 0.6 * cpu_util)

        # GPU power
        gpu_power = 0.0
        if workload.gpu_count > 0:
            per_gpu = GPU_POWER_KW.get(workload.gpu_type or "", DEFAULT_GPU_POWER_KW)
            gpu_util = workload.avg_gpu_percent / 100.0 if workload.avg_gpu_percent > 0 else 0.5
            gpu_power = workload.gpu_count * per_gpu * (0.3 + 0.7 * gpu_util)

        # Base overhead
        base = BASE_POWER_KW

        # Apply PUE
        pue = PROVIDER_PUE.get(workload.provider, DEFAULT_PUE)
        total = (cpu_power + gpu_power + base) * pue

        return total

    def estimate(self, workload: Workload) -> CarbonSnapshot:
        """Produce a carbon snapshot for a workload."""
        power_kw = self.estimate_power_kw(workload)
        intensity = self._carbon_client.get_intensity(workload.provider, workload.region)

        hourly_carbon_gco2 = power_kw * intensity
        monthly_carbon_kg = hourly_carbon_gco2 * 730 / 1000

        return CarbonSnapshot(
            workload_id=workload.id,
            region=workload.region,
            grid_intensity_gco2_kwh=intensity,
            estimated_power_kw=power_kw,
            hourly_carbon_gco2=hourly_carbon_gco2,
            monthly_carbon_kg_co2=monthly_carbon_kg,
        )
