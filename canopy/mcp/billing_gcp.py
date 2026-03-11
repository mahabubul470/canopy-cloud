"""MCP server for GCP billing and cost data."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from canopy.engine.audit import get_provider, run_audit_with_recommendations

mcp = FastMCP("canopy-billing-gcp")


@mcp.tool()  # type: ignore[misc,untyped-decorator]
def get_workload_costs(region: str | None = None) -> list[dict[str, object]]:
    """Get cost data for all GCP workloads, optionally filtered by region."""
    provider = get_provider("gcp")
    workloads = provider.list_workloads(region=region)
    results: list[dict[str, object]] = []
    for w in workloads:
        cost = provider.get_cost(w)
        results.append(
            {
                "workload_id": w.id,
                "workload_name": w.name,
                "region": w.region,
                "instance_type": w.instance_type,
                "hourly_cost_usd": cost.hourly_cost_usd,
                "monthly_cost_usd": cost.monthly_cost_usd,
            }
        )
    return results


@mcp.tool()  # type: ignore[misc,untyped-decorator]
def get_cost_breakdown(region: str | None = None) -> dict[str, object]:
    """Get aggregated cost breakdown with EcoWeight scores and recommendations."""
    results, summary = run_audit_with_recommendations(provider="gcp", region=region)
    workloads: list[dict[str, object]] = []
    for ew in results:
        workloads.append(
            {
                "workload_id": ew.workload_id,
                "workload_name": ew.workload_name,
                "monthly_cost_usd": ew.cost.monthly_cost_usd,
                "monthly_carbon_kg": ew.carbon.monthly_carbon_kg_co2,
                "ecoweight_score": round(ew.score, 3),
                "status": ew.status,
            }
        )
    return {
        "workloads": workloads,
        "total_potential_savings_usd": round(summary.total_monthly_cost_savings_usd, 2),
        "total_potential_carbon_savings_kg": round(summary.total_monthly_carbon_savings_kg, 2),
        "recommendation_count": summary.recommendation_count,
    }
