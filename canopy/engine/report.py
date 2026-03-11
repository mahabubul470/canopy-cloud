"""Report formatting helpers for Canopy."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from canopy.models.core import EcoWeight, SavingsSummary


def format_json(results: list[EcoWeight], summary: SavingsSummary) -> str:
    """Format audit results and savings summary as JSON."""
    data: dict[str, Any] = {
        "workloads": [_ecoweight_to_dict(ew) for ew in results],
        "savings_summary": {
            "total_monthly_cost_savings_usd": summary.total_monthly_cost_savings_usd,
            "total_monthly_carbon_savings_kg": summary.total_monthly_carbon_savings_kg,
            "recommendation_count": summary.recommendation_count,
            "recommendations": [r.model_dump(mode="json") for r in summary.recommendations],
        },
    }
    return json.dumps(data, indent=2, default=str)


def format_csv(results: list[EcoWeight], summary: SavingsSummary) -> str:
    """Format audit results as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Workloads section
    writer.writerow(
        [
            "workload_id",
            "workload_name",
            "region",
            "instance_type",
            "avg_cpu_percent",
            "monthly_cost_usd",
            "monthly_carbon_kg_co2",
            "ecoweight_score",
            "status",
        ]
    )
    for ew in results:
        writer.writerow(
            [
                ew.workload_id,
                ew.workload_name,
                ew.carbon.region,
                "",  # instance_type not on EcoWeight directly
                "",  # avg_cpu not on EcoWeight directly
                f"{ew.cost.monthly_cost_usd:.2f}",
                f"{ew.carbon.monthly_carbon_kg_co2:.3f}",
                f"{ew.score:.3f}",
                ew.status,
            ]
        )

    # Recommendations section
    if summary.recommendations:
        writer.writerow([])
        writer.writerow(
            [
                "recommendation_workload_id",
                "workload_name",
                "type",
                "reason",
                "current_instance",
                "suggested_instance",
                "current_region",
                "suggested_region",
                "monthly_cost_savings_usd",
                "monthly_carbon_savings_kg",
            ]
        )
        for rec in summary.recommendations:
            writer.writerow(
                [
                    rec.workload_id,
                    rec.workload_name,
                    rec.recommendation_type.value,
                    rec.reason,
                    rec.current_instance_type or "",
                    rec.suggested_instance_type or "",
                    rec.current_region or "",
                    rec.suggested_region or "",
                    f"{rec.estimated_monthly_cost_savings_usd:.2f}",
                    f"{rec.estimated_monthly_carbon_savings_kg:.3f}",
                ]
            )

    return output.getvalue()


def _ecoweight_to_dict(ew: EcoWeight) -> dict[str, object]:
    """Convert an EcoWeight to a flat dictionary for reporting."""
    return {
        "workload_id": ew.workload_id,
        "workload_name": ew.workload_name,
        "region": ew.carbon.region,
        "monthly_cost_usd": round(ew.cost.monthly_cost_usd, 2),
        "monthly_carbon_kg_co2": round(ew.carbon.monthly_carbon_kg_co2, 3),
        "ecoweight_score": round(ew.score, 3),
        "status": ew.status,
    }
