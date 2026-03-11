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
    provider: Annotated[str, typer.Option(help="Cloud provider (aws, gcp)")] = "aws",
    region: Annotated[str | None, typer.Option(help="Filter by region")] = None,
    config: Annotated[str | None, typer.Option(help="Path to canopy.yaml config file")] = None,
    auto_approve: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
    approval: Annotated[str, typer.Option(help="Approval method (cli, slack, github)")] = "cli",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be done")] = False,
) -> None:
    """Apply recommended optimizations to running infrastructure."""
    from canopy.config import load_config
    from canopy.engine.apply.aws_executor import AWSApplyExecutor
    from canopy.engine.apply.executor import ApplyStatus, execute_recommendation
    from canopy.engine.apply.gcp_executor import GCPApplyExecutor
    from canopy.engine.audit import run_audit_with_recommendations
    from canopy.engine.audit_log.writer import AuditLogWriter
    from canopy.models.audit_log import ActionType

    cfg = load_config(Path(config) if config else None)
    results, summary = run_audit_with_recommendations(provider=provider, region=region, config=cfg)

    if not summary.recommendations:
        console.print("[green]No optimizations to apply — infrastructure looks good![/green]")
        return

    # Select recommendations to apply
    recs = summary.recommendations
    if not auto_approve and not dry_run:
        if approval == "slack" and cfg.slack_webhook_url:
            from canopy.engine.apply.approval import request_slack_approval

            ok = request_slack_approval(recs, cfg.slack_webhook_url, cfg.approval_channel)
            if ok:
                console.print("[green]Approval request sent to Slack.[/green]")
            else:
                console.print("[red]Failed to send Slack approval request.[/red]")
            return
        if approval == "github" and cfg.github_token and cfg.github_repo:
            from canopy.engine.apply.approval import request_github_approval

            url = request_github_approval(recs, cfg.github_token, cfg.github_repo)
            if url:
                console.print(f"[green]GitHub issue created: {url}[/green]")
            else:
                console.print("[red]Failed to create GitHub issue.[/red]")
            return
        # Default: CLI interactive approval
        from canopy.engine.apply.approval import request_cli_approval

        recs = request_cli_approval(recs, console)
        if not recs:
            console.print("[yellow]No recommendations approved.[/yellow]")
            return

    # Create executor
    executor: AWSApplyExecutor | GCPApplyExecutor
    if provider == "gcp":
        executor = GCPApplyExecutor()
    else:
        executor = AWSApplyExecutor()

    log_dir = Path(cfg.audit_log_dir) if cfg.audit_log_dir else None
    audit_writer = AuditLogWriter(base_dir=log_dir) if log_dir else AuditLogWriter()

    # Execute
    table = Table(title="Apply Results", show_lines=True)
    table.add_column("Workload", style="cyan")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Message")

    for rec in recs:
        audit_writer.log_action(
            ActionType.APPLY_STARTED,
            workload_id=rec.workload_id,
            workload_name=rec.workload_name,
            provider=provider,
            dry_run=dry_run,
        )

        result = execute_recommendation(executor, rec, dry_run=dry_run)

        status_color = "green" if result.status == ApplyStatus.SUCCESS else "yellow"
        if result.status == ApplyStatus.FAILED:
            status_color = "red"

        table.add_row(
            rec.workload_name,
            rec.recommendation_type.value.upper(),
            f"[{status_color}]{result.status.value.upper()}[/{status_color}]",
            result.message,
        )

        log_action = (
            ActionType.APPLY_COMPLETED
            if result.status in (ApplyStatus.SUCCESS, ApplyStatus.DRY_RUN)
            else ActionType.APPLY_FAILED
        )
        audit_writer.log_action(
            log_action,
            workload_id=rec.workload_id,
            workload_name=rec.workload_name,
            provider=provider,
            details={"status": result.status.value, "message": result.message},
            dry_run=dry_run,
        )

    console.print(table)


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


# --- MCP subcommand group ---

mcp_app = typer.Typer(name="mcp", help="MCP server management", no_args_is_help=True)
app.add_typer(mcp_app, name="mcp")

_MCP_SERVERS = ["billing-aws", "billing-gcp", "electricity", "slack", "github"]


@mcp_app.command("list")
def mcp_list() -> None:
    """List available MCP servers."""
    table = Table(title="Available MCP Servers", show_lines=True)
    table.add_column("Server", style="cyan")
    table.add_column("Description")

    descriptions: dict[str, str] = {
        "billing-aws": "AWS cost and billing data",
        "billing-gcp": "GCP cost and billing data",
        "electricity": "Carbon intensity data via Electricity Maps",
        "slack": "Slack notifications and approval requests",
        "github": "GitHub issue creation for optimizations",
    }

    for name in _MCP_SERVERS:
        table.add_row(name, descriptions.get(name, ""))

    console.print(table)


@mcp_app.command("serve")
def mcp_serve(
    server_name: Annotated[str, typer.Argument(help="MCP server to start")],
) -> None:
    """Start an MCP server (communicates over stdio)."""
    try:
        from canopy.mcp import get_server
    except ImportError:
        console.print(
            "[red]MCP dependencies not installed. Install with: pip install canopy-cloud[mcp][/red]"
        )
        raise typer.Exit(1)

    if server_name not in _MCP_SERVERS:
        console.print(
            f"[red]Unknown server: {server_name}. Available: {', '.join(_MCP_SERVERS)}[/red]"
        )
        raise typer.Exit(1)

    server = get_server(server_name)
    server.run()


# --- Dashboard command ---


@app.command()
def dashboard(
    port: Annotated[int, typer.Option(help="Port to serve on")] = 8080,
    host: Annotated[str, typer.Option(help="Host to bind to")] = "127.0.0.1",
) -> None:
    """Launch the Canopy web dashboard."""
    try:
        import uvicorn  # type: ignore[import-not-found,unused-ignore]

        from canopy.dashboard.app import create_app
    except ImportError:
        console.print(
            "[red]Dashboard dependencies not installed. "
            "Install with: pip install canopy-cloud[dashboard][/red]"
        )
        raise typer.Exit(1)

    console.print(f"[green]Starting Canopy dashboard at http://{host}:{port}[/green]")
    app_instance = create_app()
    uvicorn.run(app_instance, host=host, port=port)


if __name__ == "__main__":
    app()
