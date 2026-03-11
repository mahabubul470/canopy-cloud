"""Approval mechanisms for apply operations."""

from __future__ import annotations

import httpx
from rich.console import Console
from rich.prompt import Confirm

from canopy.models.core import Recommendation


def request_cli_approval(
    recommendations: list[Recommendation],
    console: Console | None = None,
) -> list[Recommendation]:
    """Interactively prompt the user to approve each recommendation via CLI.

    Returns the list of approved recommendations.
    """
    con = console or Console()
    approved: list[Recommendation] = []

    for rec in recommendations:
        con.print(
            f"\n[bold]{rec.recommendation_type.value.upper()}[/bold] — "
            f"[cyan]{rec.workload_name}[/cyan]"
        )
        con.print(f"  {rec.reason}")
        con.print(
            f"  Savings: [yellow]${rec.estimated_monthly_cost_savings_usd:,.2f}/mo[/yellow]"
            f" | [green]{rec.estimated_monthly_carbon_savings_kg:,.1f} kg CO₂/mo[/green]"
        )

        if Confirm.ask("  Apply this recommendation?", default=False):
            approved.append(rec)

    return approved


def request_slack_approval(
    recommendations: list[Recommendation],
    webhook_url: str,
    channel: str | None = None,
) -> bool:
    """Post an approval request to a Slack webhook.

    Returns True if the message was sent successfully.
    The actual approval is polled separately via `canopy apply --check`.
    """
    blocks: list[dict[str, object]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Canopy: {len(recommendations)} optimization(s) pending approval",
            },
        },
    ]

    for rec in recommendations:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{rec.recommendation_type.value.upper()}* — `{rec.workload_name}`\n"
                        f"{rec.reason}\n"
                        f"Savings: ${rec.estimated_monthly_cost_savings_usd:,.2f}/mo | "
                        f"{rec.estimated_monthly_carbon_savings_kg:,.1f} kg CO₂/mo"
                    ),
                },
            }
        )

    payload: dict[str, object] = {"blocks": blocks}
    if channel:
        payload["channel"] = channel

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def request_github_approval(
    recommendations: list[Recommendation],
    github_token: str,
    github_repo: str,
) -> str | None:
    """Create a GitHub issue requesting approval for recommendations.

    Returns the issue URL if created successfully, None otherwise.
    """
    body_lines: list[str] = [
        "## Canopy Optimization Approval Request\n",
        f"**{len(recommendations)} recommendation(s)** pending approval.\n",
        "| Type | Workload | Reason | Cost Savings | Carbon Savings |",
        "|------|----------|--------|-------------|----------------|",
    ]

    for rec in recommendations:
        body_lines.append(
            f"| {rec.recommendation_type.value} | `{rec.workload_name}` | "
            f"{rec.reason} | ${rec.estimated_monthly_cost_savings_usd:,.2f}/mo | "
            f"{rec.estimated_monthly_carbon_savings_kg:,.1f} kg CO₂/mo |"
        )

    body_lines.append("\n---\nApprove by commenting `/canopy approve` on this issue.")

    title = f"Canopy: {len(recommendations)} optimization(s) pending approval"
    body = "\n".join(body_lines)

    try:
        response = httpx.post(
            f"https://api.github.com/repos/{github_repo}/issues",
            json={"title": title, "body": body, "labels": ["canopy", "optimization"]},
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json().get("html_url", ""))
    except httpx.HTTPError:
        return None
