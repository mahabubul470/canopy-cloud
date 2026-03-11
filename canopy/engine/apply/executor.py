"""Apply executor — abstract base and result model for applying recommendations."""

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel, Field

from canopy.models.core import Recommendation, RecommendationType


class ApplyStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"
    NOT_SUPPORTED = "not_supported"


class ApplyResult(BaseModel):
    """Result of applying a single recommendation."""

    workload_id: str
    workload_name: str
    recommendation_type: RecommendationType
    status: ApplyStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class ApplyExecutor(ABC):
    """Abstract base class for recommendation executors."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider this executor handles."""

    @abstractmethod
    def terminate_instance(self, workload_id: str, region: str) -> ApplyResult:
        """Terminate an idle instance."""

    @abstractmethod
    def rightsize_instance(
        self,
        workload_id: str,
        region: str,
        current_type: str,
        target_type: str,
    ) -> ApplyResult:
        """Rightsize an instance (stop → modify → start)."""

    @abstractmethod
    def move_region(
        self,
        workload_id: str,
        current_region: str,
        target_region: str,
    ) -> ApplyResult:
        """Move a workload to a different region."""


def execute_recommendation(
    executor: ApplyExecutor,
    rec: Recommendation,
    *,
    dry_run: bool = False,
) -> ApplyResult:
    """Dispatch a recommendation to the appropriate executor method."""
    if dry_run:
        return ApplyResult(
            workload_id=rec.workload_id,
            workload_name=rec.workload_name,
            recommendation_type=rec.recommendation_type,
            status=ApplyStatus.DRY_RUN,
            message=f"[dry-run] Would {rec.recommendation_type.value}: {rec.reason}",
        )

    if rec.recommendation_type == RecommendationType.IDLE:
        return executor.terminate_instance(
            workload_id=rec.workload_id,
            region=rec.current_region or "",
        )

    if rec.recommendation_type == RecommendationType.RIGHTSIZE:
        return executor.rightsize_instance(
            workload_id=rec.workload_id,
            region=rec.current_region or "",
            current_type=rec.current_instance_type or "",
            target_type=rec.suggested_instance_type or "",
        )

    if rec.recommendation_type == RecommendationType.REGION_MOVE:
        return executor.move_region(
            workload_id=rec.workload_id,
            current_region=rec.current_region or "",
            target_region=rec.suggested_region or "",
        )

    return ApplyResult(
        workload_id=rec.workload_id,
        workload_name=rec.workload_name,
        recommendation_type=rec.recommendation_type,
        status=ApplyStatus.NOT_SUPPORTED,
        message=f"Unknown recommendation type: {rec.recommendation_type}",
    )
