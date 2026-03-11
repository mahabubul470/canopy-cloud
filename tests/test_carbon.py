"""Tests for the carbon intensity client and estimator."""

from canopy.engine.carbon.client import CarbonIntensityClient
from canopy.engine.carbon.estimator import CarbonEstimator
from canopy.models.core import Workload, WorkloadType


class TestCarbonIntensityClient:
    def setup_method(self) -> None:
        self.client = CarbonIntensityClient()

    def test_get_known_region(self) -> None:
        region = self.client.get_region("aws", "us-east-1")
        assert region is not None
        assert region.grid_intensity_gco2_kwh == 312

    def test_get_unknown_region_returns_none(self) -> None:
        region = self.client.get_region("aws", "nonexistent-region")
        assert region is None

    def test_get_intensity_known(self) -> None:
        intensity = self.client.get_intensity("gcp", "europe-north2")
        assert intensity == 3

    def test_get_intensity_unknown_returns_default(self) -> None:
        intensity = self.client.get_intensity("aws", "unknown-1")
        assert intensity == 500.0

    def test_get_all_regions(self) -> None:
        regions = self.client.get_all_regions()
        assert len(regions) > 10
        providers = {r.provider for r in regions}
        assert "aws" in providers
        assert "gcp" in providers

    def test_fetch_live_without_api_key(self) -> None:
        result = self.client.fetch_live_intensity(59.33, 18.07)
        assert result is None


class TestCarbonEstimator:
    def setup_method(self) -> None:
        self.estimator = CarbonEstimator()

    def _make_workload(self, **kwargs: object) -> Workload:
        defaults: dict[str, object] = {
            "id": "w1",
            "name": "test",
            "provider": "aws",
            "region": "us-east-1",
            "workload_type": WorkloadType.COMPUTE,
            "vcpus": 4,
            "memory_gb": 16.0,
            "avg_cpu_percent": 50.0,
        }
        defaults.update(kwargs)
        return Workload(**defaults)

    def test_estimate_power_scales_with_cpu(self) -> None:
        low_cpu = self._make_workload(avg_cpu_percent=10.0)
        high_cpu = self._make_workload(avg_cpu_percent=90.0)

        low_power = self.estimator.estimate_power_kw(low_cpu)
        high_power = self.estimator.estimate_power_kw(high_cpu)
        assert high_power > low_power

    def test_gpu_workload_draws_more_power(self) -> None:
        cpu_only = self._make_workload()
        with_gpu = self._make_workload(gpu_count=1, gpu_type="NVIDIA", avg_gpu_percent=80.0)

        cpu_power = self.estimator.estimate_power_kw(cpu_only)
        gpu_power = self.estimator.estimate_power_kw(with_gpu)
        assert gpu_power > cpu_power

    def test_estimate_produces_snapshot(self) -> None:
        workload = self._make_workload()
        snapshot = self.estimator.estimate(workload)

        assert snapshot.workload_id == "w1"
        assert snapshot.region == "us-east-1"
        assert snapshot.grid_intensity_gco2_kwh == 312
        assert snapshot.estimated_power_kw > 0
        assert snapshot.hourly_carbon_gco2 > 0
        assert snapshot.monthly_carbon_kg_co2 > 0

    def test_clean_region_less_carbon(self) -> None:
        dirty = self._make_workload(region="us-east-1")
        clean = self._make_workload(region="eu-north-1")

        dirty_snapshot = self.estimator.estimate(dirty)
        clean_snapshot = self.estimator.estimate(clean)
        assert clean_snapshot.hourly_carbon_gco2 < dirty_snapshot.hourly_carbon_gco2

    def test_pue_applied(self) -> None:
        workload = self._make_workload()
        power = self.estimator.estimate_power_kw(workload)
        # Power should be > raw CPU power due to PUE multiplier
        raw_cpu_power = 4 * 0.007 * (0.4 + 0.6 * 0.5) + 0.010
        assert power > raw_cpu_power
