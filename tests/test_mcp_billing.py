"""Tests for MCP billing servers."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("mcp")


class TestMCPBillingAWS:
    @patch("canopy.mcp.billing_aws.get_provider")
    def test_get_workload_costs(self, mock_get_provider: MagicMock) -> None:
        from canopy.mcp.billing_aws import get_workload_costs
        from canopy.models.core import CostSnapshot, Workload, WorkloadType

        mock_provider = MagicMock()
        mock_provider.list_workloads.return_value = [
            Workload(
                id="i-1",
                name="web-1",
                provider="aws",
                region="us-east-1",
                workload_type=WorkloadType.COMPUTE,
                instance_type="t3.large",
                vcpus=2,
                memory_gb=8.0,
            ),
        ]
        mock_provider.get_cost.return_value = CostSnapshot(
            workload_id="i-1",
            hourly_cost_usd=0.0832,
            monthly_cost_usd=60.74,
        )
        mock_get_provider.return_value = mock_provider

        results = get_workload_costs(region="us-east-1")
        assert len(results) == 1
        assert results[0]["workload_id"] == "i-1"
        assert results[0]["monthly_cost_usd"] == 60.74

    @patch("canopy.mcp.billing_aws.run_audit_with_recommendations")
    def test_get_cost_breakdown(self, mock_audit: MagicMock) -> None:
        from canopy.mcp.billing_aws import get_cost_breakdown
        from canopy.models.core import (
            CarbonSnapshot,
            CostSnapshot,
            EcoWeight,
            SavingsSummary,
        )

        ew = EcoWeight(
            workload_id="i-1",
            workload_name="web-1",
            cost=CostSnapshot(workload_id="i-1", hourly_cost_usd=0.1, monthly_cost_usd=73),
            carbon=CarbonSnapshot(
                workload_id="i-1",
                region="us-east-1",
                grid_intensity_gco2_kwh=312,
                estimated_power_kw=0.05,
                hourly_carbon_gco2=15.6,
                monthly_carbon_kg_co2=11.4,
            ),
            budget_hourly_usd=1.0,
            carbon_hourly_gco2=100.0,
        )
        summary = SavingsSummary(
            total_monthly_cost_savings_usd=20.0,
            total_monthly_carbon_savings_kg=5.0,
            recommendation_count=1,
        )
        mock_audit.return_value = ([ew], summary)

        result = get_cost_breakdown()
        assert result["recommendation_count"] == 1
        assert len(result["workloads"]) == 1


class TestMCPBillingGCP:
    @patch("canopy.mcp.billing_gcp.get_provider")
    def test_get_workload_costs(self, mock_get_provider: MagicMock) -> None:
        from canopy.mcp.billing_gcp import get_workload_costs
        from canopy.models.core import CostSnapshot, Workload, WorkloadType

        mock_provider = MagicMock()
        mock_provider.list_workloads.return_value = [
            Workload(
                id="gce-1",
                name="api-1",
                provider="gcp",
                region="us-central1",
                workload_type=WorkloadType.COMPUTE,
                instance_type="e2-standard-2",
                vcpus=2,
                memory_gb=8.0,
            ),
        ]
        mock_provider.get_cost.return_value = CostSnapshot(
            workload_id="gce-1",
            hourly_cost_usd=0.0671,
            monthly_cost_usd=48.98,
        )
        mock_get_provider.return_value = mock_provider

        results = get_workload_costs()
        assert len(results) == 1
        assert results[0]["workload_id"] == "gce-1"
