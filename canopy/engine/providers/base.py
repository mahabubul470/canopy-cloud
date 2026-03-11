"""Abstract base class for cloud providers."""

from abc import ABC, abstractmethod

from canopy.models.core import CostSnapshot, Workload


class CloudProvider(ABC):
    """Interface that all cloud providers must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'aws', 'gcp')."""

    @abstractmethod
    def list_workloads(self, region: str | None = None) -> list[Workload]:
        """List all running workloads, optionally filtered by region."""

    @abstractmethod
    def get_cost(self, workload: Workload) -> CostSnapshot:
        """Get current cost data for a workload."""

    @abstractmethod
    def get_regions(self) -> list[str]:
        """List available regions for this provider."""
