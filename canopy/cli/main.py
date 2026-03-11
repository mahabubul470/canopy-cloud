"""Canopy CLI entry point."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

import canopy

app = typer.Typer(
    name="canopy",
    help="Canopy: Budget & Carbon-Aware Infrastructure Architect",
    no_args_is_help=True,
)
console = Console()

STATUS_COLORS: dict[str, str] = {
    "excellent": "green",
    "good": "blue",
    "warning": "yellow",
    "over": "red",
    "critical": "bold red",
}

REC_TYPE_COLORS: dict[str, str] = {
    "idle": "red",
    "rightsize": "yellow",
    "region_move": "cyan",
}


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[green]canopy[/green] v{canopy.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Canopy: Budget & Carbon-Aware Infrastructure Architect."""


@app.command()
def audit(
    provider: Annotated[str, typer.Option(help="Cloud provider (aws, gcp)")] = "aws",
    region: Annotated[str | None, typer.Option(help="Filter by region")] = None,
    output: Annotated[str, typer.Option(help="Output format (table, json)")] = "table",
    config: Annotated[str | None, typer.Option(help="Path to canopy.yaml config file")] = None,
) -> None:
    """Scan running infrastructure and compute EcoWeight scores."""
    from canopy.config import load_config
    from canopy.engine.audit import run_audit_with_recommendations
    from canopy.engine.report import format_json

    cfg = load_config(Path(config) if config else None)
    results, summary = run_audit_with_recommendations(provider=provider, region=region, config=cfg)

    if output == "json":
        console.print_json(format_json(results, summary))
        return

    if not results:
        console.print("[yellow]No workloads found.[/yellow]")
        return

    # EcoWeight results table
    table = Table(title="Canopy Audit Results", show_lines=True)
    table.add_column("Workload", style="cyan")
    table.add_column("Region")
    table.add_column("Type")
    table.add_column("CPU %", justify="right")
    table.add_column("Cost/mo", justify="right", style="yellow")
    table.add_column("Carbon/mo", justify="right", style="green")
    table.add_column("EcoWeight", justify="right")
    table.add_column("Status")

    for ew in results:
        score = ew.score
        status_color = STATUS_COLORS.get(ew.status, "white")

        table.add_row(
            ew.workload_name,
            ew.carbon.region,
            "—",
            "—",
            f"${ew.cost.monthly_cost_usd:,.2f}",
            f"{ew.carbon.monthly_carbon_kg_co2:,.1f} kg",
            f"{score:.2f}",
            f"[{status_color}]{ew.status.upper()}[/{status_color}]",
        )

    console.print(table)

    # Recommendations table
    if summary.recommendations:
        console.print()
        rec_table = Table(title="Optimization Recommendations", show_lines=True)
        rec_table.add_column("Workload", style="cyan")
        rec_table.add_column("Type")
        rec_table.add_column("Recommendation")
        rec_table.add_column("Cost Savings/mo", justify="right", style="yellow")
        rec_table.add_column("Carbon Savings/mo", justify="right", style="green")

        for rec in summary.recommendations:
            type_color = REC_TYPE_COLORS.get(rec.recommendation_type.value, "white")
            rec_table.add_row(
                rec.workload_name,
                f"[{type_color}]{rec.recommendation_type.value.upper()}[/{type_color}]",
                rec.reason,
                f"${rec.estimated_monthly_cost_savings_usd:,.2f}",
                f"{rec.estimated_monthly_carbon_savings_kg:,.1f} kg",
            )

        console.print(rec_table)

        # Savings summary
        console.print()
        console.print(
            f"[bold]Total potential savings:[/bold] "
            f"[yellow]${summary.total_monthly_cost_savings_usd:,.2f}/mo[/yellow]"
            f" | [green]{summary.total_monthly_carbon_savings_kg:,.1f} kg CO₂/mo[/green]"
            f" ({summary.recommendation_count} recommendations)"
        )


SEVERITY_COLORS: dict[str, str] = {
    "block": "bold red",
    "warn": "yellow",
    "info": "blue",
}


@app.command()
def plan(
    plan_file: Annotated[str, typer.Argument(help="Terraform/Pulumi plan JSON file")],
    source: Annotated[str, typer.Option(help="IaC source (auto, terraform, pulumi)")] = "auto",
    policy: Annotated[str | None, typer.Option(help="Path to canopy-policy.yaml")] = None,
    region: Annotated[str, typer.Option(help="Default region for resources")] = "us-east-1",
    output: Annotated[str, typer.Option(help="Output format (table, json)")] = "table",
) -> None:
    """Preview cost and carbon impact of infrastructure changes."""
    import json as json_mod

    from canopy.engine.iac.pulumi import parse_preview_dict
    from canopy.engine.iac.terraform import parse_plan_json
    from canopy.engine.plan import estimate_plan
    from canopy.engine.policy import load_policy

    plan_path = Path(plan_file)
    if not plan_path.is_file():
        console.print(f"[red]Plan file not found: {plan_file}[/red]")
        raise typer.Exit(1)

    # Auto-detect IaC source or use explicit override
    if source == "auto":
        raw = json_mod.loads(plan_path.read_text(encoding="utf-8"))
        if "resource_changes" in raw:
            parsed = parse_plan_json(plan_path)
        elif "steps" in raw:
            parsed = parse_preview_dict(raw)
        else:
            console.print("[red]Could not detect plan format. Use --source.[/red]")
            raise typer.Exit(1)
    elif source == "pulumi":
        raw = json_mod.loads(plan_path.read_text(encoding="utf-8"))
        parsed = parse_preview_dict(raw)
    else:
        parsed = parse_plan_json(plan_path)

    pol = load_policy(Path(policy) if policy else None)
    estimate = estimate_plan(parsed, policy=pol, default_region=region)

    if output == "json":
        data = {
            "source": estimate.source,
            "resources": [r.model_dump(mode="json") for r in estimate.resources],
            "violations": [v.model_dump(mode="json") for v in estimate.violations],
            "summary": {
                "total_monthly_cost_usd": round(estimate.total_monthly_cost_usd, 2),
                "total_cost_delta_usd": round(estimate.total_cost_delta_usd, 2),
                "total_monthly_carbon_kg": round(estimate.total_monthly_carbon_kg, 3),
                "total_carbon_delta_kg": round(estimate.total_carbon_delta_kg, 3),
            },
        }
        console.print_json(json_mod.dumps(data, indent=2, default=str))
        return

    if not estimate.resources:
        console.print("[yellow]No compute resource changes found in plan.[/yellow]")
        return

    # Resource changes table
    table = Table(title="Infrastructure Changes — Cost & Carbon Impact", show_lines=True)
    table.add_column("Resource", style="cyan")
    table.add_column("Action")
    table.add_column("Instance", justify="center")
    table.add_column("Region")
    table.add_column("Cost/mo", justify="right", style="yellow")
    table.add_column("Cost Delta", justify="right")
    table.add_column("Carbon/mo", justify="right", style="green")
    table.add_column("Carbon Delta", justify="right")

    action_colors: dict[str, str] = {
        "create": "green",
        "update": "yellow",
        "delete": "red",
        "no-op": "dim",
    }

    for r in estimate.resources:
        a_color = action_colors.get(r.action.value, "white")
        cost_delta_str = _format_delta(r.cost_delta_usd, "$", 2)
        carbon_delta_str = _format_delta(r.carbon_delta_kg, "", 1, " kg")

        table.add_row(
            r.address,
            f"[{a_color}]{r.action.value.upper()}[/{a_color}]",
            r.instance_type or "—",
            r.region or "—",
            f"${r.monthly_cost_usd:,.2f}",
            cost_delta_str,
            f"{r.monthly_carbon_kg_co2:,.1f} kg",
            carbon_delta_str,
        )

    console.print(table)

    # Summary line
    console.print()
    cost_delta = _format_delta(estimate.total_cost_delta_usd, "$", 2)
    carbon_delta = _format_delta(estimate.total_carbon_delta_kg, "", 1, " kg CO₂")
    console.print(
        f"[bold]Total monthly impact:[/bold] "
        f"[yellow]${estimate.total_monthly_cost_usd:,.2f}/mo[/yellow] ({cost_delta})"
        f" | [green]{estimate.total_monthly_carbon_kg:,.1f} kg CO₂/mo[/green] ({carbon_delta})"
    )

    # Policy violations
    if estimate.violations:
        console.print()
        viol_table = Table(title="Policy Violations", show_lines=True)
        viol_table.add_column("Severity")
        viol_table.add_column("Policy")
        viol_table.add_column("Resource", style="cyan")
        viol_table.add_column("Message")

        for v in estimate.violations:
            sev_color = SEVERITY_COLORS.get(v.severity.value, "white")
            viol_table.add_row(
                f"[{sev_color}]{v.severity.value.upper()}[/{sev_color}]",
                v.policy_name,
                v.resource_name or v.resource_id or "—",
                v.message,
            )

        console.print(viol_table)

        blocking = sum(1 for v in estimate.violations if v.severity.value == "block")
        if blocking:
            console.print(
                f"\n[bold red]{blocking} blocking violation(s)"
                f" — this plan should not be applied.[/bold red]"
            )
            raise typer.Exit(1)


def _format_delta(value: float, prefix: str, decimals: int, suffix: str = "") -> str:
    """Format a delta value with color and sign."""
    if abs(value) < 0.005:
        return "[dim]—[/dim]"
    if value > 0:
        return f"[red]+{prefix}{value:,.{decimals}f}{suffix}[/red]"
    return f"[green]-{prefix}{abs(value):,.{decimals}f}{suffix}[/green]"


@app.command()
def apply(
    auto_approve: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
) -> None:
    """Apply recommended optimizations."""
    console.print("[yellow]canopy apply is coming in v0.3[/yellow]")


@app.command()
def report(
    provider: Annotated[str, typer.Option(help="Cloud provider (aws, gcp)")] = "aws",
    region: Annotated[str | None, typer.Option(help="Filter by region")] = None,
    output: Annotated[str, typer.Option(help="Output format (json, csv)")] = "json",
    out: Annotated[str | None, typer.Option(help="Output file path")] = None,
    config: Annotated[str | None, typer.Option(help="Path to canopy.yaml config file")] = None,
) -> None:
    """Generate an emissions and cost report with recommendations."""
    from canopy.config import load_config
    from canopy.engine.audit import run_audit_with_recommendations
    from canopy.engine.report import format_csv, format_json

    cfg = load_config(Path(config) if config else None)
    results, summary = run_audit_with_recommendations(provider=provider, region=region, config=cfg)

    if output == "csv":
        content = format_csv(results, summary)
    else:
        content = format_json(results, summary)

    if out:
        Path(out).write_text(content, encoding="utf-8")
        console.print(f"[green]Report written to {out}[/green]")
    else:
        console.print(content)


@app.command()
def regions(
    provider: Annotated[str, typer.Option(help="Cloud provider (aws, gcp)")] = "all",
) -> None:
    """Show region efficiency tiers based on carbon intensity."""
    from canopy.engine.carbon.client import CarbonIntensityClient

    client = CarbonIntensityClient()
    all_regions = client.get_all_regions()

    if provider != "all":
        all_regions = [r for r in all_regions if r.provider == provider]

    table = Table(title="Region Efficiency Tiers", show_lines=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Region")
    table.add_column("Location")
    table.add_column("CFE%", justify="right")
    table.add_column("Grid Intensity", justify="right")
    table.add_column("Tier")

    tier_colors = {
        "platinum": "bold green",
        "gold": "yellow",
        "silver": "white",
        "bronze": "red",
    }

    for r in sorted(all_regions, key=lambda x: x.grid_intensity_gco2_kwh):
        tier = r.efficiency_tier
        color = tier_colors.get(tier.value, "white")
        table.add_row(
            r.provider,
            r.name,
            r.location,
            f"{r.cfe_percent:.0f}%",
            f"{r.grid_intensity_gco2_kwh:.0f} gCO₂/kWh",
            f"[{color}]{tier.value.upper()}[/{color}]",
        )

    console.print(table)


if __name__ == "__main__":
    app()
