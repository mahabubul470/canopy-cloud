"""Grid carbon intensity client with static fallback data."""

import httpx

from canopy.models.core import Region

# Static fallback data based on publicly available sources.
# Used when no API key is configured or when offline.
# Sources: Google Cloud CFE%, Electricity Maps, WattTime
STATIC_REGIONS: list[dict[str, object]] = [
    # GCP
    {"provider": "gcp", "name": "europe-north1", "location": "Finland", "cfe": 94, "intensity": 8},
    {"provider": "gcp", "name": "europe-north2", "location": "Stockholm, SE", "cfe": 100, "intensity": 3},
    {"provider": "gcp", "name": "europe-west9", "location": "Paris, FR", "cfe": 96, "intensity": 16},
    {"provider": "gcp", "name": "northamerica-northeast1", "location": "Montréal, CA", "cfe": 99, "intensity": 5},
    {"provider": "gcp", "name": "us-west1", "location": "Oregon, US", "cfe": 87, "intensity": 79},
    {"provider": "gcp", "name": "us-central1", "location": "Iowa, US", "cfe": 97, "intensity": 39},
    {"provider": "gcp", "name": "us-east1", "location": "South Carolina, US", "cfe": 31, "intensity": 576},
    {"provider": "gcp", "name": "us-east4", "location": "Virginia, US", "cfe": 28, "intensity": 312},
    {"provider": "gcp", "name": "asia-south1", "location": "Mumbai, IN", "cfe": 9, "intensity": 679},
    {"provider": "gcp", "name": "asia-east1", "location": "Taiwan", "cfe": 10, "intensity": 541},
    {"provider": "gcp", "name": "asia-northeast1", "location": "Tokyo, JP", "cfe": 19, "intensity": 463},
    {"provider": "gcp", "name": "europe-west1", "location": "Belgium", "cfe": 74, "intensity": 110},
    # AWS (estimated from grid data — AWS does not publish per-region CFE%)
    {"provider": "aws", "name": "eu-north-1", "location": "Stockholm, SE", "cfe": 98, "intensity": 8},
    {"provider": "aws", "name": "ca-central-1", "location": "Montréal, CA", "cfe": 95, "intensity": 12},
    {"provider": "aws", "name": "eu-west-1", "location": "Ireland", "cfe": 75, "intensity": 98},
    {"provider": "aws", "name": "eu-west-3", "location": "Paris, FR", "cfe": 93, "intensity": 22},
    {"provider": "aws", "name": "eu-central-1", "location": "Frankfurt, DE", "cfe": 55, "intensity": 252},
    {"provider": "aws", "name": "us-west-2", "location": "Oregon, US", "cfe": 85, "intensity": 79},
    {"provider": "aws", "name": "us-east-1", "location": "N. Virginia, US", "cfe": 30, "intensity": 312},
    {"provider": "aws", "name": "us-east-2", "location": "Ohio, US", "cfe": 25, "intensity": 410},
    {"provider": "aws", "name": "ap-south-1", "location": "Mumbai, IN", "cfe": 9, "intensity": 679},
    {"provider": "aws", "name": "ap-southeast-1", "location": "Singapore", "cfe": 3, "intensity": 408},
    {"provider": "aws", "name": "ap-northeast-1", "location": "Tokyo, JP", "cfe": 19, "intensity": 463},
    {"provider": "aws", "name": "sa-east-1", "location": "São Paulo, BR", "cfe": 80, "intensity": 61},
]


class CarbonIntensityClient:
    """Fetches grid carbon intensity data.

    Uses the Electricity Maps API when an API key is provided,
    otherwise falls back to static regional data.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = "https://api.electricitymap.org/v3"
        self._static_regions = self._build_static_regions()

    def _build_static_regions(self) -> list[Region]:
        return [
            Region(
                provider=str(r["provider"]),
                name=str(r["name"]),
                location=str(r["location"]),
                cfe_percent=float(r["cfe"]),  # type: ignore[arg-type]
                grid_intensity_gco2_kwh=float(r["intensity"]),  # type: ignore[arg-type]
            )
            for r in STATIC_REGIONS
        ]

    def get_all_regions(self) -> list[Region]:
        """Return all known regions with their carbon data."""
        return list(self._static_regions)

    def get_region(self, provider: str, region_name: str) -> Region | None:
        """Get carbon data for a specific region."""
        for r in self._static_regions:
            if r.provider == provider and r.name == region_name:
                return r
        return None

    def get_intensity(self, provider: str, region_name: str) -> float:
        """Get grid carbon intensity for a region in gCO2eq/kWh.

        Returns a high default (500) for unknown regions as a conservative estimate.
        """
        region = self.get_region(provider, region_name)
        if region:
            return region.grid_intensity_gco2_kwh
        return 500.0

    def fetch_live_intensity(self, latitude: float, longitude: float) -> float | None:
        """Fetch live carbon intensity from Electricity Maps API.

        Returns None if no API key is configured or the request fails.
        """
        if not self._api_key:
            return None

        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{self._base_url}/carbon-intensity/latest",
                    params={"lat": latitude, "lon": longitude},
                    headers={"auth-token": self._api_key},
                )
                response.raise_for_status()
                data = response.json()
                return float(data.get("carbonIntensity", 0))
        except (httpx.HTTPError, KeyError, ValueError):
            return None
