"""Tests for MCP electricity (carbon intensity) server."""

import pytest

pytest.importorskip("mcp")

from canopy.mcp.electricity import get_all_region_intensities, get_carbon_intensity  # noqa: E402


class TestGetCarbonIntensity:
    def test_known_region(self) -> None:
        result = get_carbon_intensity("aws", "eu-north-1")
        assert result["region"] == "eu-north-1"
        assert result["grid_intensity_gco2_kwh"] == 8
        assert result["efficiency_tier"] == "platinum"
        assert result["source"] == "static_data"

    def test_unknown_region_returns_default(self) -> None:
        result = get_carbon_intensity("aws", "unknown-region-99")
        assert result["grid_intensity_gco2_kwh"] == 500.0
        assert result["source"] == "default_estimate"

    def test_gcp_region(self) -> None:
        result = get_carbon_intensity("gcp", "europe-north1")
        assert result["cfe_percent"] == 94
        assert result["location"] == "Finland"


class TestGetAllRegionIntensities:
    def test_returns_all_regions(self) -> None:
        results = get_all_region_intensities()
        assert len(results) > 20
        # Should be sorted by intensity
        intensities = [r["grid_intensity_gco2_kwh"] for r in results]
        assert intensities == sorted(intensities)

    def test_filter_by_provider(self) -> None:
        aws_results = get_all_region_intensities(provider="aws")
        gcp_results = get_all_region_intensities(provider="gcp")
        assert all(r["provider"] == "aws" for r in aws_results)
        assert all(r["provider"] == "gcp" for r in gcp_results)
        assert len(aws_results) > 0
        assert len(gcp_results) > 0
