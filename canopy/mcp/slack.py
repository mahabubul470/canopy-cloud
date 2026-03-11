"""MCP server for Slack notifications."""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

mcp = FastMCP("canopy-slack")


@mcp.tool()  # type: ignore[misc,untyped-decorator]
def send_notification(
    webhook_url: str,
    message: str,
    channel: str | None = None,
) -> dict[str, object]:
    """Send a notification message to a Slack channel via webhook.

    Args:
        webhook_url: Slack incoming webhook URL.
        message: Message text to send.
        channel: Optional channel override.
    """
    payload: dict[str, object] = {"text": message}
    if channel:
        payload["channel"] = channel

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return {"success": True, "status_code": response.status_code}
    except httpx.HTTPError as e:
        return {"success": False, "error": str(e)}


@mcp.tool()  # type: ignore[misc,untyped-decorator]
def send_approval_request(
    webhook_url: str,
    workload_id: str,
    workload_name: str,
    recommendation_type: str,
    reason: str,
    cost_savings_usd: float,
    carbon_savings_kg: float,
    channel: str | None = None,
) -> dict[str, object]:
    """Send an optimization approval request to Slack.

    Args:
        webhook_url: Slack incoming webhook URL.
        workload_id: ID of the workload.
        workload_name: Name of the workload.
        recommendation_type: Type of recommendation (idle, rightsize, region_move).
        reason: Why this optimization is recommended.
        cost_savings_usd: Estimated monthly cost savings in USD.
        carbon_savings_kg: Estimated monthly carbon savings in kg CO2.
        channel: Optional channel override.
    """
    blocks: list[dict[str, object]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Canopy: Optimization approval for {workload_name}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{recommendation_type.upper()}* — `{workload_name}` (`{workload_id}`)\n"
                    f"{reason}\n"
                    f"Savings: ${cost_savings_usd:,.2f}/mo | "
                    f"{carbon_savings_kg:,.1f} kg CO₂/mo"
                ),
            },
        },
    ]

    payload: dict[str, object] = {"blocks": blocks}
    if channel:
        payload["channel"] = channel

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        return {"success": True, "status_code": response.status_code}
    except httpx.HTTPError as e:
        return {"success": False, "error": str(e)}
