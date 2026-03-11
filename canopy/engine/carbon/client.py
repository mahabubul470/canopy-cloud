"""Grid carbon intensity client with static fallback data."""

import httpx

from canopy.models.core import Region


# Static fallback data based on publicly available sources.
# Used when no API key is configured or when offline.
# Sources: Google Cloud CFE%, Electricity Maps, WattTime
def _r(provider: str, name: str, location: str, cfe: int, intensity: int) -> dict[str, object]:
    return {
        "provider": provider,
        "name": name,
        "location": location,
        "cfe": cfe,
        "intensity": intensity,
    }


STATIC_REGIONS: list[dict[str, object]] = [
    # GCP
    _r("gcp", "europe-north1", "Finland", 94, 8),
    _r("gcp", "europe-north2", "Stockholm, SE", 100, 3),
    _r("gcp", "europe-west9", "Paris, FR", 96, 16),
    _r("gcp", "northamerica-northeast1", "Montréal, CA", 99, 5),
    _r("gcp", "us-west1", "Oregon, US", 87, 79),
    _r("gcp", "us-central1", "Iowa, US", 97, 39),
    _r("gcp", "us-east1", "S. Carolina, US", 31, 576),
    _r("gcp", "us-east4", "Virginia, US", 28, 312),
    _r("gcp", "asia-south1", "Mumbai, IN", 9, 679),
    _r("gcp", "asia-east1", "Taiwan", 10, 541),
    _r("gcp", "asia-northeast1", "Tokyo, JP", 19, 463),
    _r("gcp", "europe-west1", "Belgium", 74, 110),
    # AWS (estimated — AWS does not publish per-region CFE%)
    _r("aws", "eu-north-1", "Stockholm, SE", 98, 8),
    _r("aws", "ca-central-1", "Montréal, CA", 95, 12),
    _r("aws", "eu-west-1", "Ireland", 75, 98),
    _r("aws", "eu-west-3", "Paris, FR", 93, 22),
    _r("aws", "eu-central-1", "Frankfurt, DE", 55, 252),
    _r("aws", "us-west-2", "Oregon, US", 85, 79),
    _r("aws", "us-east-1", "N. Virginia, US", 30, 312),
    _r("aws", "us-east-2", "Ohio, US", 25, 410),
    _r("aws", "ap-south-1", "Mumbai, IN", 9, 679),
    _r("aws", "ap-southeast-1", "Singapore", 3, 408),
    _r("aws", "ap-northeast-1", "Tokyo, JP", 19, 463),
    _r("aws", "sa-east-1", "São Paulo, BR", 80, 61),
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
