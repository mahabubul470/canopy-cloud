"""GCP cloud provider implementation.

Uses the google-cloud-compute library for instance discovery
and falls back to static pricing when the Billing API is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

from canopy.engine.providers.base import CloudProvider
from canopy.models.core import CostSnapshot, Workload, WorkloadType

logger = logging.getLogger(__name__)

# Approximate on-demand hourly prices (USD) for common GCP machine types.
INSTANCE_PRICING: dict[str, float] = {
    "e2-micro": 0.0084,
    "e2-small": 0.0168,
    "e2-medium": 0.0336,
    "e2-standard-2": 0.0671,
    "e2-standard-4": 0.1342,
    "e2-standard-8": 0.2684,
    "n2-standard-2": 0.0971,
    "n2-standard-4": 0.1942,
    "n2-standard-8": 0.3884,
    "n2-standard-16": 0.7769,
    "n2-standard-32": 1.5537,
    "c2-standard-4": 0.2088,
    "c2-standard-8": 0.4176,
    "c2-standard-16": 0.8352,
    "n2d-standard-2": 0.0845,
    "n2d-standard-4": 0.1690,
    "n2d-standard-8": 0.3380,
    "a2-highgpu-1g": 3.6733,
    "a2-highgpu-2g": 7.3466,
    "g2-standard-4": 0.7211,
    "g2-standard-8": 0.9422,
}

# vCPU and memory for common GCP machine types
INSTANCE_SPECS: dict[str, tuple[int, float]] = {
    "e2-micro": (2, 1.0),
    "e2-small": (2, 2.0),
    "e2-medium": (2, 4.0),
    "e2-standard-2": (2, 8.0),
    "e2-standard-4": (4, 16.0),
    "e2-standard-8": (8, 32.0),
    "n2-standard-2": (2, 8.0),
    "n2-standard-4": (4, 16.0),
    "n2-standard-8": (8, 32.0),
    "n2-standard-16": (16, 64.0),
    "n2-standard-32": (32, 128.0),
    "c2-standard-4": (4, 16.0),
    "c2-standard-8": (8, 32.0),
    "c2-standard-16": (16, 64.0),
    "n2d-standard-2": (2, 8.0),
    "n2d-standard-4": (4, 16.0),
    "n2d-standard-8": (8, 32.0),
    "a2-highgpu-1g": (12, 85.0),
    "a2-highgpu-2g": (24, 170.0),
    "g2-standard-4": (4, 16.0),
    "g2-standard-8": (8, 32.0),
}


class GCPProvider(CloudProvider):
    """GCP cloud provider.

    Uses google-cloud-compute for instance discovery when available,
    otherwise returns an empty workload list (useful for plan-only workflows).
    """

    def __init__(
        self,
        project: str | None = None,
        default_zone: str = "us-central1-a",
    ) -> None:
        self._project = project
        self._default_zone = default_zone

    @property
    def name(self) -> str:
        return "gcp"

    def get_regions(self) -> list[str]:
        """List available GCP regions.

        Falls back to static list when google-cloud-compute is not installed.
        """
        try:
            return self._list_regions_live()
        except Exception:
            return list(self._static_regions())

    def list_workloads(self, region: str | None = None) -> list[Workload]:
        """List running GCE instances."""
        try:
            return self._list_instances_live(region)
        except Exception:
            logger.debug("GCP instance listing unavailable, returning empty list")
            return []

    def get_cost(self, workload: Workload) -> CostSnapshot:
        """Estimate cost from static pricing table."""
        hourly = INSTANCE_PRICING.get(workload.instance_type or "", 0.0)
        return CostSnapshot(
            workload_id=workload.id,
            hourly_cost_usd=hourly,
            monthly_cost_usd=hourly * 730,
        )

    def _list_regions_live(self) -> list[str]:
        """List regions using google-cloud-compute."""
        from google.cloud import compute_v1  # type: ignore[import-not-found]

        client = compute_v1.RegionsClient()
        request = compute_v1.ListRegionsRequest(project=self._project or "")
        regions: list[str] = []
        for region in client.list(request=request):
            regions.append(str(region.name))
        return regions

    def _list_instances_live(self, region: str | None = None) -> list[Workload]:
        """List instances using google-cloud-compute."""
        from google.cloud import compute_v1

        client = compute_v1.InstancesClient()
        workloads: list[Workload] = []

        if region:
            zones = [f"{region}-a", f"{region}-b", f"{region}-c"]
        else:
            zone = self._default_zone
            zones = [zone]

        for zone in zones:
            try:
                request = compute_v1.ListInstancesRequest(
                    project=self._project or "",
                    zone=zone,
                    filter='status="RUNNING"',
                )
                for instance in client.list(request=request):
                    workload = self._instance_to_workload(instance, zone)
                    workloads.append(workload)
            except Exception:
                continue

        return workloads

    def _instance_to_workload(self, instance: Any, zone: str) -> Workload:
        """Convert a GCE instance to a Canopy Workload."""
        machine_type: str = str(instance.machine_type).rsplit("/", 1)[-1]
        vcpus, memory_gb = INSTANCE_SPECS.get(machine_type, (0, 0.0))

        # Extract region from zone (us-central1-a → us-central1)
        parts = zone.rsplit("-", 1)
        region = parts[0] if len(parts) == 2 else zone

        labels: dict[str, str] = dict(instance.labels) if instance.labels else {}
        name = labels.get("name", str(instance.name))

        gpu_count = 0
        gpu_type = None
        if machine_type.startswith(("a2", "g2")):
            gpu_count = 1
            gpu_type = "NVIDIA"

        return Workload(
            id=str(instance.id),
            name=name,
            provider="gcp",
            region=region,
            workload_type=WorkloadType.COMPUTE,
            instance_type=machine_type,
            vcpus=vcpus,
            memory_gb=memory_gb,
            gpu_count=gpu_count,
            gpu_type=gpu_type,
            avg_cpu_percent=0.0,
            tags=labels,
        )

    @staticmethod
    def _static_regions() -> list[str]:
        return [
            "us-central1",
            "us-east1",
            "us-east4",
            "us-west1",
            "us-west4",
            "europe-north1",
            "europe-west1",
            "europe-west4",
            "asia-east1",
            "asia-northeast1",
            "asia-south1",
            "asia-southeast1",
        ]
