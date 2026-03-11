"""GCP apply executor — applies recommendations against GCP."""

from __future__ import annotations

import logging

from canopy.engine.apply.executor import ApplyExecutor, ApplyResult, ApplyStatus
from canopy.models.core import RecommendationType

logger = logging.getLogger(__name__)


class GCPApplyExecutor(ApplyExecutor):
    """Executes recommendations against GCP using google-cloud-compute."""

    def __init__(self, project: str | None = None) -> None:
        self._project = project

    @property
    def provider_name(self) -> str:
        return "gcp"

    def terminate_instance(self, workload_id: str, region: str) -> ApplyResult:
        """Terminate (delete) a GCE instance."""
        try:
            from google.cloud import compute_v1  # type: ignore[import-not-found]

            client = compute_v1.InstancesClient()
            # region is actually zone for GCE
            zone = f"{region}-a"
            operation = client.delete(
                project=self._project or "",
                zone=zone,
                instance=workload_id,
            )
            operation.result()
            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.IDLE,
                status=ApplyStatus.SUCCESS,
                message=f"Deleted instance {workload_id} in {zone}",
            )
        except ImportError:
            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.IDLE,
                status=ApplyStatus.FAILED,
                message="google-cloud-compute is not installed",
            )
        except Exception as e:
            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.IDLE,
                status=ApplyStatus.FAILED,
                message=f"Failed to delete {workload_id}: {e}",
            )

    def rightsize_instance(
        self,
        workload_id: str,
        region: str,
        current_type: str,
        target_type: str,
    ) -> ApplyResult:
        """Rightsize a GCE instance: stop → update machine type → start."""
        try:
            from google.cloud import compute_v1

            client = compute_v1.InstancesClient()
            zone = f"{region}-a"
            project = self._project or ""

            # Stop the instance
            stop_op = client.stop(project=project, zone=zone, instance=workload_id)
            stop_op.result()

            # Update machine type
            machine_type_url = f"zones/{zone}/machineTypes/{target_type}"
            body = compute_v1.InstancesSetMachineTypeRequest(
                machine_type=machine_type_url,
            )
            modify_op = client.set_machine_type(
                project=project,
                zone=zone,
                instance=workload_id,
                instances_set_machine_type_request_resource=body,
            )
            modify_op.result()

            # Start the instance
            start_op = client.start(project=project, zone=zone, instance=workload_id)
            start_op.result()

            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.RIGHTSIZE,
                status=ApplyStatus.SUCCESS,
                message=f"Rightsized {workload_id} from {current_type} to {target_type}",
                details={"previous_type": current_type, "new_type": target_type},
            )
        except ImportError:
            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.RIGHTSIZE,
                status=ApplyStatus.FAILED,
                message="google-cloud-compute is not installed",
            )
        except Exception as e:
            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.RIGHTSIZE,
                status=ApplyStatus.FAILED,
                message=f"Failed to rightsize {workload_id}: {e}",
            )

    def move_region(
        self,
        workload_id: str,
        current_region: str,
        target_region: str,
    ) -> ApplyResult:
        """Region move is not yet supported for GCP."""
        return ApplyResult(
            workload_id=workload_id,
            workload_name=workload_id,
            recommendation_type=RecommendationType.REGION_MOVE,
            status=ApplyStatus.NOT_SUPPORTED,
            message=(
                f"Region move ({current_region} → {target_region}) is not yet automated. "
                "This requires snapshot, image creation, re-launch, and DNS update."
            ),
        )
