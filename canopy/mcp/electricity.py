"""MCP server for carbon intensity data."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from canopy.engine.carbon.client import CarbonIntensityClient

mcp = FastMCP("canopy-electricity")


@mcp.tool()  # type: ignore[misc,untyped-decorator]
def get_carbon_intensity(provider: str, region: str) -> dict[str, object]:
    """Get carbon intensity for a specific cloud region.

    Args:
        provider: Cloud provider (aws, gcp).
        region: Region identifier (e.g., us-east-1, europe-north1).
    """
    client = CarbonIntensityClient()
    region_data = client.get_region(provider, region)

    if region_data is None:
        intensity = client.get_intensity(provider, region)
        return {
            "provider": provider,
            "region": region,
            "grid_intensity_gco2_kwh": intensity,
            "source": "default_estimate",
        }

    return {
        "provider": region_data.provider,
        "region": region_data.name,
        "location": region_data.location,
        "cfe_percent": region_data.cfe_percent,
        "grid_intensity_gco2_kwh": region_data.grid_intensity_gco2_kwh,
        "efficiency_tier": region_data.efficiency_tier.value,
        "source": "static_data",
    }


@mcp.tool()  # type: ignore[misc,untyped-decorator]
def get_all_region_intensities(provider: str | None = None) -> list[dict[str, object]]:
    """Get carbon intensity data for all known regions.

    Args:
        provider: Optional filter by cloud provider (aws, gcp).
    """
    client = CarbonIntensityClient()
    regions = client.get_all_regions()

    if provider:
        regions = [r for r in regions if r.provider == provider]

    return [
        {
            "provider": r.provider,
            "region": r.name,
            "location": r.location,
            "cfe_percent": r.cfe_percent,
            "grid_intensity_gco2_kwh": r.grid_intensity_gco2_kwh,
            "efficiency_tier": r.efficiency_tier.value,
        }
        for r in sorted(regions, key=lambda x: x.grid_intensity_gco2_kwh)
    ]
