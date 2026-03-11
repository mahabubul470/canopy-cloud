"""AWS apply executor — real boto3 calls for applying recommendations."""

import logging

import boto3
from botocore.exceptions import ClientError

from canopy.engine.apply.executor import ApplyExecutor, ApplyResult, ApplyStatus
from canopy.models.core import RecommendationType

logger = logging.getLogger(__name__)


class AWSApplyExecutor(ApplyExecutor):
    """Executes recommendations against AWS using boto3."""

    def __init__(self, profile: str | None = None) -> None:
        self._session = boto3.Session(profile_name=profile)

    @property
    def provider_name(self) -> str:
        return "aws"

    def terminate_instance(self, workload_id: str, region: str) -> ApplyResult:
        """Terminate an idle EC2 instance."""
        try:
            ec2 = self._session.client("ec2", region_name=region)
            ec2.terminate_instances(InstanceIds=[workload_id])
            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.IDLE,
                status=ApplyStatus.SUCCESS,
                message=f"Terminated instance {workload_id} in {region}",
            )
        except ClientError as e:
            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.IDLE,
                status=ApplyStatus.FAILED,
                message=f"Failed to terminate {workload_id}: {e}",
            )

    def rightsize_instance(
        self,
        workload_id: str,
        region: str,
        current_type: str,
        target_type: str,
    ) -> ApplyResult:
        """Rightsize an EC2 instance: stop → modify instance type → start."""
        try:
            ec2 = self._session.client("ec2", region_name=region)

            # Stop the instance
            ec2.stop_instances(InstanceIds=[workload_id])
            waiter = ec2.get_waiter("instance_stopped")
            waiter.wait(InstanceIds=[workload_id])

            # Modify instance type
            ec2.modify_instance_attribute(
                InstanceId=workload_id,
                InstanceType={"Value": target_type},
            )

            # Start the instance
            ec2.start_instances(InstanceIds=[workload_id])

            return ApplyResult(
                workload_id=workload_id,
                workload_name=workload_id,
                recommendation_type=RecommendationType.RIGHTSIZE,
                status=ApplyStatus.SUCCESS,
                message=(
                    f"Rightsized {workload_id} from {current_type} to {target_type} in {region}"
                ),
                details={"previous_type": current_type, "new_type": target_type},
            )
        except ClientError as e:
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
        """Region move is not yet supported — too destructive for Phase 3."""
        return ApplyResult(
            workload_id=workload_id,
            workload_name=workload_id,
            recommendation_type=RecommendationType.REGION_MOVE,
            status=ApplyStatus.NOT_SUPPORTED,
            message=(
                f"Region move ({current_region} → {target_region}) is not yet automated. "
                "This requires AMI copy, re-launch, DNS update, and data migration. "
                "Consider using 'canopy apply --approval github' to create a tracking issue."
            ),
        )
