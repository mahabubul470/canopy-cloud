"""Tests for report formatting helpers."""

import csv
import io
import json

from canopy.engine.report import format_csv, format_json
from canopy.models.core import (
    CarbonSnapshot,
    CostSnapshot,
    EcoWeight,
    Recommendation,
    RecommendationType,
    SavingsSummary,
)


def _make_ecoweight(workload_id: str = "w1", name: str = "test") -> EcoWeight:
    cost = CostSnapshot(
        workload_id=workload_id,
        hourly_cost_usd=0.192,
        monthly_cost_usd=140.16,
    )
    carbon = CarbonSnapshot(
        workload_id=workload_id,
        region="us-east-1",
        grid_intensity_gco2_kwh=312,
        estimated_power_kw=0.032,
        hourly_carbon_gco2=9.98,
        monthly_carbon_kg_co2=7.29,
    )
    return EcoWeight(
        workload_id=workload_id,
        workload_name=name,
        cost=cost,
        carbon=carbon,
        budget_hourly_usd=1.0,
        carbon_hourly_gco2=100.0,
    )


def _make_summary() -> SavingsSummary:
    rec = Recommendation(
        workload_id="w1",
        workload_name="test",
        recommendation_type=RecommendationType.RIGHTSIZE,
        reason="Avg CPU 8.0% < 15%",
        current_instance_type="m5.2xlarge",
        suggested_instance_type="m5.xlarge",
        estimated_monthly_cost_savings_usd=140.16,
        estimated_monthly_carbon_savings_kg=3.6,
    )
    return SavingsSummary(
        total_monthly_cost_savings_usd=140.16,
        total_monthly_carbon_savings_kg=3.6,
        recommendation_count=1,
        recommendations=[rec],
    )


class TestFormatJson:
    def test_valid_json(self) -> None:
        results = [_make_ecoweight()]
        summary = _make_summary()
        output = format_json(results, summary)
        data = json.loads(output)
        assert "workloads" in data
        assert "savings_summary" in data

    def test_workload_fields(self) -> None:
        results = [_make_ecoweight()]
        summary = SavingsSummary()
        output = format_json(results, summary)
        data = json.loads(output)
        workload = data["workloads"][0]
        assert workload["workload_id"] == "w1"
        assert workload["region"] == "us-east-1"
        assert "ecoweight_score" in workload
        assert "status" in workload

    def test_savings_summary_in_json(self) -> None:
        results = [_make_ecoweight()]
        summary = _make_summary()
        output = format_json(results, summary)
        data = json.loads(output)
        savings = data["savings_summary"]
        assert savings["recommendation_count"] == 1
        assert savings["total_monthly_cost_savings_usd"] == 140.16

    def test_empty_results(self) -> None:
        output = format_json([], SavingsSummary())
        data = json.loads(output)
        assert data["workloads"] == []
        assert data["savings_summary"]["recommendation_count"] == 0


class TestFormatCsv:
    def test_csv_headers(self) -> None:
        results = [_make_ecoweight()]
        summary = SavingsSummary()
        output = format_csv(results, summary)
        reader = csv.reader(io.StringIO(output))
        header = next(reader)
        assert "workload_id" in header
        assert "ecoweight_score" in header

    def test_csv_data_rows(self) -> None:
        results = [_make_ecoweight("w1", "a"), _make_ecoweight("w2", "b")]
        summary = SavingsSummary()
        output = format_csv(results, summary)
        reader = csv.reader(io.StringIO(output))
        next(reader)  # skip header
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0][0] == "w1"
        assert rows[1][0] == "w2"

    def test_csv_with_recommendations(self) -> None:
        results = [_make_ecoweight()]
        summary = _make_summary()
        output = format_csv(results, summary)
        assert "rightsize" in output
        assert "m5.xlarge" in output
