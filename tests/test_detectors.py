"""Tests for workload optimization detectors."""

from canopy.engine.carbon.client import CarbonIntensityClient
from canopy.engine.detectors import detect_idle, detect_region_move, detect_rightsize
from canopy.models.core import (
    CarbonSnapshot,
    CostSnapshot,
    RecommendationType,
    Workload,
    WorkloadType,
)


def _make_workload(**kwargs: object) -> Workload:
    defaults: dict[str, object] = {
        "id": "i-test",
        "name": "test-workload",
        "provider": "aws",
        "region": "us-east-1",
        "workload_type": WorkloadType.COMPUTE,
        "instance_type": "m5.2xlarge",
        "vcpus": 8,
        "memory_gb": 32.0,
        "avg_cpu_percent": 5.0,
    }
    defaults.update(kwargs)
    return Workload(**defaults)


def _make_cost(hourly: float = 0.384) -> CostSnapshot:
    return CostSnapshot(
        workload_id="i-test",
        hourly_cost_usd=hourly,
        monthly_cost_usd=hourly * 730,
    )


def _make_carbon(
    hourly_gco2: float = 10.0,
    monthly_kg: float = 7.3,
) -> CarbonSnapshot:
    return CarbonSnapshot(
        workload_id="i-test",
        region="us-east-1",
        grid_intensity_gco2_kwh=312,
        estimated_power_kw=0.032,
        hourly_carbon_gco2=hourly_gco2,
        monthly_carbon_kg_co2=monthly_kg,
    )


class TestDetectIdle:
    def test_idle_below_threshold(self) -> None:
        workload = _make_workload(avg_cpu_percent=0.5)
        rec = detect_idle(workload, _make_cost(), _make_carbon())
        assert rec is not None
        assert rec.recommendation_type == RecommendationType.IDLE
        assert rec.estimated_monthly_cost_savings_usd > 0

    def test_not_idle_above_threshold(self) -> None:
        workload = _make_workload(avg_cpu_percent=5.0)
        rec = detect_idle(workload, _make_cost(), _make_carbon())
        assert rec is None

    def test_idle_at_threshold(self) -> None:
        workload = _make_workload(avg_cpu_percent=2.0)
        rec = detect_idle(workload, _make_cost(), _make_carbon())
        assert rec is None

    def test_idle_custom_threshold(self) -> None:
        workload = _make_workload(avg_cpu_percent=4.0)
        rec = detect_idle(workload, _make_cost(), _make_carbon(), threshold=5.0)
        assert rec is not None


class TestDetectRightsize:
    def test_rightsize_below_threshold(self) -> None:
        workload = _make_workload(avg_cpu_percent=8.0, instance_type="m5.2xlarge")
        rec = detect_rightsize(workload, _make_cost(0.384), _make_carbon())
        assert rec is not None
        assert rec.recommendation_type == RecommendationType.RIGHTSIZE
        assert rec.suggested_instance_type == "m5.xlarge"
        assert rec.estimated_monthly_cost_savings_usd > 0

    def test_not_rightsize_above_threshold(self) -> None:
        workload = _make_workload(avg_cpu_percent=20.0)
        rec = detect_rightsize(workload, _make_cost(), _make_carbon())
        assert rec is None

    def test_no_downgrade_for_smallest(self) -> None:
        workload = _make_workload(avg_cpu_percent=5.0, instance_type="m5.large")
        rec = detect_rightsize(workload, _make_cost(), _make_carbon())
        assert rec is None  # m5.large has no smaller variant in DOWNGRADE_MAP

    def test_rightsize_carbon_savings(self) -> None:
        workload = _make_workload(avg_cpu_percent=8.0, instance_type="c5.2xlarge")
        rec = detect_rightsize(workload, _make_cost(0.34), _make_carbon())
        assert rec is not None
        assert rec.estimated_monthly_carbon_savings_kg > 0


class TestDetectRegionMove:
    def test_suggest_greener_region(self) -> None:
        # us-east-1 has 312 gCO2/kWh, eu-north-1 has 8 — well over 50% cleaner
        workload = _make_workload(region="us-east-1")
        carbon = _make_carbon()
        client = CarbonIntensityClient()
        rec = detect_region_move(workload, carbon, client)
        assert rec is not None
        assert rec.recommendation_type == RecommendationType.REGION_MOVE
        assert rec.suggested_region is not None
        assert rec.estimated_monthly_carbon_savings_kg > 0

    def test_no_move_for_clean_region(self) -> None:
        workload = _make_workload(region="eu-north-1")
        carbon = CarbonSnapshot(
            workload_id="i-test",
            region="eu-north-1",
            grid_intensity_gco2_kwh=8,
            estimated_power_kw=0.032,
            hourly_carbon_gco2=0.256,
            monthly_carbon_kg_co2=0.187,
        )
        client = CarbonIntensityClient()
        rec = detect_region_move(workload, carbon, client)
        assert rec is None  # already in cleanest region
