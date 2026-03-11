"""Canopy web dashboard — FastAPI application."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI  # type: ignore[import-not-found]
from fastapi.responses import FileResponse, JSONResponse  # type: ignore[import-not-found]

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI dashboard application."""
    app = FastAPI(title="Canopy Dashboard", version="0.3.0")

    @app.get("/api/overview")  # type: ignore[misc,untyped-decorator]
    def api_overview() -> JSONResponse:
        """Overview stats: total workloads, cost, carbon, recommendations."""
        from canopy.config import load_config
        from canopy.engine.audit import run_audit_with_recommendations

        cfg = load_config()
        try:
            results, summary = run_audit_with_recommendations(provider=cfg.provider, config=cfg)
        except Exception:
            return JSONResponse(
                {
                    "workload_count": 0,
                    "total_monthly_cost_usd": 0,
                    "total_monthly_carbon_kg": 0,
                    "recommendation_count": 0,
                    "potential_savings_usd": 0,
                    "potential_carbon_savings_kg": 0,
                    "error": "Could not connect to cloud provider",
                }
            )

        return JSONResponse(
            {
                "workload_count": len(results),
                "total_monthly_cost_usd": round(sum(ew.cost.monthly_cost_usd for ew in results), 2),
                "total_monthly_carbon_kg": round(
                    sum(ew.carbon.monthly_carbon_kg_co2 for ew in results), 2
                ),
                "recommendation_count": summary.recommendation_count,
                "potential_savings_usd": round(summary.total_monthly_cost_savings_usd, 2),
                "potential_carbon_savings_kg": round(summary.total_monthly_carbon_savings_kg, 2),
            }
        )

    @app.get("/api/workloads")  # type: ignore[misc,untyped-decorator]
    def api_workloads() -> JSONResponse:
        """List all workloads with EcoWeight scores."""
        from canopy.config import load_config
        from canopy.engine.audit import run_audit_with_recommendations

        cfg = load_config()
        try:
            results, summary = run_audit_with_recommendations(provider=cfg.provider, config=cfg)
        except Exception:
            return JSONResponse({"workloads": [], "recommendations": []})

        workloads = [
            {
                "workload_id": ew.workload_id,
                "workload_name": ew.workload_name,
                "region": ew.carbon.region,
                "monthly_cost_usd": round(ew.cost.monthly_cost_usd, 2),
                "monthly_carbon_kg": round(ew.carbon.monthly_carbon_kg_co2, 2),
                "ecoweight_score": round(ew.score, 3),
                "status": ew.status,
            }
            for ew in results
        ]
        recommendations = [
            {
                "workload_id": rec.workload_id,
                "workload_name": rec.workload_name,
                "type": rec.recommendation_type.value,
                "reason": rec.reason,
                "cost_savings_usd": round(rec.estimated_monthly_cost_savings_usd, 2),
                "carbon_savings_kg": round(rec.estimated_monthly_carbon_savings_kg, 2),
            }
            for rec in summary.recommendations
        ]
        return JSONResponse({"workloads": workloads, "recommendations": recommendations})

    @app.get("/api/trends")  # type: ignore[misc,untyped-decorator]
    def api_trends() -> JSONResponse:
        """Return region efficiency data for trend visualization."""
        from canopy.engine.carbon.client import CarbonIntensityClient

        client = CarbonIntensityClient()
        regions = client.get_all_regions()
        data = [
            {
                "provider": r.provider,
                "region": r.name,
                "location": r.location,
                "cfe_percent": r.cfe_percent,
                "grid_intensity": r.grid_intensity_gco2_kwh,
                "tier": r.efficiency_tier.value,
            }
            for r in sorted(regions, key=lambda x: x.grid_intensity_gco2_kwh)
        ]
        return JSONResponse({"regions": data})

    @app.get("/api/audit-log")  # type: ignore[misc,untyped-decorator]
    def api_audit_log(days: int = 7) -> JSONResponse:
        """Return recent audit log entries."""
        from canopy.engine.audit_log.reader import AuditLogReader

        reader = AuditLogReader()
        today = date.today()
        start = today - timedelta(days=days)

        try:
            entries = reader.read_range(start, today)
        except Exception:
            entries = []

        return JSONResponse(
            {
                "entries": [
                    {
                        "timestamp": entry.timestamp.isoformat(),
                        "action": entry.action.value,
                        "workload_id": entry.workload_id,
                        "workload_name": entry.workload_name,
                        "provider": entry.provider,
                        "dry_run": entry.dry_run,
                    }
                    for entry in entries[-100:]  # Last 100 entries
                ]
            }
        )

    @app.get("/api/recommendations")  # type: ignore[misc,untyped-decorator]
    def api_recommendations() -> JSONResponse:
        """Get all current recommendations."""
        from canopy.config import load_config
        from canopy.engine.audit import run_audit_with_recommendations

        cfg = load_config()
        try:
            _, summary = run_audit_with_recommendations(provider=cfg.provider, config=cfg)
        except Exception:
            return JSONResponse({"recommendations": []})

        return JSONResponse(
            {
                "recommendations": [
                    {
                        "workload_id": rec.workload_id,
                        "workload_name": rec.workload_name,
                        "type": rec.recommendation_type.value,
                        "reason": rec.reason,
                        "current_instance_type": rec.current_instance_type,
                        "suggested_instance_type": rec.suggested_instance_type,
                        "current_region": rec.current_region,
                        "suggested_region": rec.suggested_region,
                        "cost_savings_usd": round(rec.estimated_monthly_cost_savings_usd, 2),
                        "carbon_savings_kg": round(rec.estimated_monthly_carbon_savings_kg, 2),
                    }
                    for rec in summary.recommendations
                ]
            }
        )

    @app.get("/")  # type: ignore[misc,untyped-decorator]
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/style.css")  # type: ignore[misc,untyped-decorator]
    def stylesheet() -> FileResponse:
        return FileResponse(_STATIC_DIR / "style.css", media_type="text/css")

    return app
