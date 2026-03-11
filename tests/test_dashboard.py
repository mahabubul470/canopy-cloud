"""Tests for the Canopy dashboard."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Skip all tests if fastapi is not installed
fastapi = pytest.importorskip("fastapi")


from fastapi.testclient import TestClient  # type: ignore[import-not-found]  # noqa: E402

from canopy.dashboard.app import create_app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


class TestDashboardRoutes:
    def test_index_returns_html(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "Canopy Dashboard" in response.text

    def test_stylesheet(self, client: TestClient) -> None:
        response = client.get("/style.css")
        assert response.status_code == 200
        assert "body" in response.text

    @patch("canopy.engine.audit.run_audit_with_recommendations")
    @patch("canopy.config.load_config")
    def test_api_overview(
        self, mock_config: MagicMock, mock_audit: MagicMock, client: TestClient
    ) -> None:
        from canopy.config import CanopyConfig
        from canopy.models.core import (
            CarbonSnapshot,
            CostSnapshot,
            EcoWeight,
            SavingsSummary,
        )

        mock_config.return_value = CanopyConfig()
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
        mock_audit.return_value = (
            [ew],
            SavingsSummary(
                total_monthly_cost_savings_usd=20,
                total_monthly_carbon_savings_kg=5,
                recommendation_count=1,
            ),
        )

        response = client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["workload_count"] == 1
        assert data["total_monthly_cost_usd"] == 73.0
        assert data["recommendation_count"] == 1

    @patch("canopy.engine.audit.run_audit_with_recommendations")
    @patch("canopy.config.load_config")
    def test_api_overview_error_handling(
        self, mock_config: MagicMock, mock_audit: MagicMock, client: TestClient
    ) -> None:
        from canopy.config import CanopyConfig

        mock_config.return_value = CanopyConfig()
        mock_audit.side_effect = Exception("AWS not configured")

        response = client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["workload_count"] == 0
        assert "error" in data

    def test_api_trends(self, client: TestClient) -> None:
        response = client.get("/api/trends")
        assert response.status_code == 200
        data = response.json()
        assert "regions" in data
        assert len(data["regions"]) > 20

    def test_api_audit_log_empty(self, client: TestClient) -> None:
        response = client.get("/api/audit-log")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data

    @patch("canopy.engine.audit.run_audit_with_recommendations")
    @patch("canopy.config.load_config")
    def test_api_workloads(
        self, mock_config: MagicMock, mock_audit: MagicMock, client: TestClient
    ) -> None:
        from canopy.config import CanopyConfig
        from canopy.models.core import SavingsSummary

        mock_config.return_value = CanopyConfig()
        mock_audit.return_value = ([], SavingsSummary())

        response = client.get("/api/workloads")
        assert response.status_code == 200
        data = response.json()
        assert "workloads" in data
        assert "recommendations" in data

    @patch("canopy.engine.audit.run_audit_with_recommendations")
    @patch("canopy.config.load_config")
    def test_api_recommendations(
        self, mock_config: MagicMock, mock_audit: MagicMock, client: TestClient
    ) -> None:
        from canopy.config import CanopyConfig
        from canopy.models.core import SavingsSummary

        mock_config.return_value = CanopyConfig()
        mock_audit.return_value = ([], SavingsSummary())

        response = client.get("/api/recommendations")
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
