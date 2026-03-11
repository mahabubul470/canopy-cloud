"""MCP server registry for Canopy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def get_server(name: str) -> Any:
    """Get an MCP server instance by name."""
    servers: dict[str, str] = {
        "billing-aws": "canopy.mcp.billing_aws",
        "billing-gcp": "canopy.mcp.billing_gcp",
        "electricity": "canopy.mcp.electricity",
        "slack": "canopy.mcp.slack",
        "github": "canopy.mcp.github",
    }

    module_path = servers.get(name)
    if not module_path:
        raise ValueError(f"Unknown MCP server: {name}. Available: {', '.join(servers)}")

    import importlib

    module = importlib.import_module(module_path)
    return module.mcp
