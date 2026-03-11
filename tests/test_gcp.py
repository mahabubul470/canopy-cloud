"""Tests for the GCP provider."""

from canopy.engine.providers.gcp import INSTANCE_PRICING, INSTANCE_SPECS, GCPProvider
from canopy.models.core import Workload, WorkloadType


def test_provider_name() -> None:
    provider = GCPProvider()
    assert provider.name == "gcp"


def test_get_regions_static_fallback() -> None:
    """When google-cloud-compute is not installed, falls back to static list."""
    provider = GCPProvider()
    regions = provider.get_regions()
    assert len(regions) > 0
    assert "us-central1" in regions


def test_get_cost_known_instance() -> None:
    provider = GCPProvider()
    workload = Workload(
        id="test-1",
        name="test",
        provider="gcp",
        region="us-central1",
        workload_type=WorkloadType.COMPUTE,
        instance_type="n2-standard-4",
    )
    cost = provider.get_cost(workload)
    assert cost.hourly_cost_usd == INSTANCE_PRICING["n2-standard-4"]
    assert cost.monthly_cost_usd == cost.hourly_cost_usd * 730


def test_get_cost_unknown_instance() -> None:
    provider = GCPProvider()
    workload = Workload(
        id="test-1",
        name="test",
        provider="gcp",
        region="us-central1",
        workload_type=WorkloadType.COMPUTE,
        instance_type="custom-128-524288",
    )
    cost = provider.get_cost(workload)
    assert cost.hourly_cost_usd == 0.0


def test_instance_specs_consistency() -> None:
    """Every priced instance should have specs."""
    for instance_type in INSTANCE_PRICING:
        assert instance_type in INSTANCE_SPECS, f"{instance_type} missing from INSTANCE_SPECS"


def test_list_workloads_returns_empty_without_gcp_sdk() -> None:
    """Without google-cloud-compute, list_workloads returns empty."""
    provider = GCPProvider()
    workloads = provider.list_workloads()
    assert workloads == []


def test_gpu_detection() -> None:
    """GPU machine types should be detected."""
    provider = GCPProvider()
    workload = Workload(
        id="test-gpu",
        name="gpu-worker",
        provider="gcp",
        region="us-central1",
        workload_type=WorkloadType.COMPUTE,
        instance_type="a2-highgpu-1g",
    )
    cost = provider.get_cost(workload)
    assert cost.hourly_cost_usd > 0
