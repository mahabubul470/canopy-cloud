"""Tests for core data models."""

from canopy.models.core import (
    CarbonSnapshot,
    CostSnapshot,
    EcoWeight,
    EfficiencyTier,
    Region,
    Workload,
    WorkloadType,
)


class TestRegion:
    def test_platinum_tier_high_cfe(self) -> None:
        region = Region(
            provider="gcp",
            name="europe-north2",
            location="Stockholm",
            cfe_percent=100,
            grid_intensity_gco2_kwh=3,
        )
        assert region.efficiency_tier == EfficiencyTier.PLATINUM

    def test_gold_tier(self) -> None:
        region = Region(
            provider="aws",
            name="us-west-2",
            location="Oregon",
            cfe_percent=85,
            grid_intensity_gco2_kwh=79,
        )
        assert region.efficiency_tier == EfficiencyTier.GOLD

    def test_bronze_tier(self) -> None:
        region = Region(
            provider="aws",
            name="ap-south-1",
            location="Mumbai",
            cfe_percent=9,
            grid_intensity_gco2_kwh=679,
        )
        assert region.efficiency_tier == EfficiencyTier.BRONZE

    def test_silver_tier(self) -> None:
        region = Region(
            provider="aws",
            name="eu-central-1",
            location="Frankfurt",
            cfe_percent=55,
            grid_intensity_gco2_kwh=252,
        )
        assert region.efficiency_tier == EfficiencyTier.SILVER


class TestWorkload:
    def test_basic_workload(self) -> None:
        w = Workload(
            id="i-123",
            name="api-server",
            provider="aws",
            region="us-east-1",
            workload_type=WorkloadType.COMPUTE,
            instance_type="m5.xlarge",
            vcpus=4,
            memory_gb=16.0,
            avg_cpu_percent=25.0,
        )
        assert w.vcpus == 4
        assert w.tags == {}

    def test_gpu_workload(self) -> None:
        w = Workload(
            id="i-456",
            name="training-node",
            provider="aws",
            region="us-west-2",
            workload_type=WorkloadType.AI_TRAINING,
            instance_type="p4d.24xlarge",
            vcpus=96,
            memory_gb=1152.0,
            gpu_count=8,
            gpu_type="NVIDIA A100",
            avg_gpu_percent=90.0,
        )
        assert w.gpu_count == 8


class TestEcoWeight:
    def _make_ecoweight(
        self,
        hourly_cost: float = 0.5,
        hourly_carbon: float = 50.0,
        budget: float = 1.0,
        carbon_budget: float = 100.0,
        alpha: float = 0.5,
        beta: float = 0.5,
    ) -> EcoWeight:
        cost = CostSnapshot(
            workload_id="w1",
            hourly_cost_usd=hourly_cost,
            monthly_cost_usd=hourly_cost * 730,
        )
        carbon = CarbonSnapshot(
            workload_id="w1",
            region="us-east-1",
            grid_intensity_gco2_kwh=312,
            estimated_power_kw=0.05,
            hourly_carbon_gco2=hourly_carbon,
            monthly_carbon_kg_co2=hourly_carbon * 730 / 1000,
        )
        return EcoWeight(
            workload_id="w1",
            workload_name="test",
            cost=cost,
            carbon=carbon,
            alpha=alpha,
            beta=beta,
            budget_hourly_usd=budget,
            carbon_hourly_gco2=carbon_budget,
        )

    def test_perfect_score(self) -> None:
        ew = self._make_ecoweight(hourly_cost=1.0, hourly_carbon=100.0)
        assert ew.score == 1.0
        assert ew.status == "warning"

    def test_under_budget(self) -> None:
        ew = self._make_ecoweight(hourly_cost=0.3, hourly_carbon=30.0)
        assert ew.score < 1.0
        assert not ew.is_over_budget

    def test_over_budget(self) -> None:
        ew = self._make_ecoweight(hourly_cost=2.0, hourly_carbon=200.0)
        assert ew.score > 1.0
        assert ew.is_over_budget
        assert ew.status in ("over", "critical")

    def test_cost_weighted(self) -> None:
        ew = self._make_ecoweight(
            hourly_cost=2.0,
            hourly_carbon=0.0,
            alpha=1.0,
            beta=0.0,
            carbon_budget=1.0,
        )
        assert ew.score == 2.0

    def test_carbon_weighted(self) -> None:
        ew = self._make_ecoweight(
            hourly_cost=0.0,
            hourly_carbon=200.0,
            alpha=0.0,
            beta=1.0,
            budget=1.0,
        )
        assert ew.score == 2.0

    def test_excellent_status(self) -> None:
        ew = self._make_ecoweight(hourly_cost=0.2, hourly_carbon=20.0)
        assert ew.status == "excellent"

    def test_good_status(self) -> None:
        ew = self._make_ecoweight(hourly_cost=0.8, hourly_carbon=80.0)
        assert ew.status == "good"
