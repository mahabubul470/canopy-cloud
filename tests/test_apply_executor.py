"""Tests for apply executor and dispatch."""

from unittest.mock import MagicMock, patch

from canopy.engine.apply.aws_executor import AWSApplyExecutor
from canopy.engine.apply.executor import (
    ApplyExecutor,
    ApplyResult,
    ApplyStatus,
    execute_recommendation,
)
from canopy.engine.apply.gcp_executor import GCPApplyExecutor
from canopy.models.core import Recommendation, RecommendationType


def _make_rec(
    rec_type: RecommendationType,
    workload_id: str = "i-123",
    workload_name: str = "web-server",
    **kwargs: object,
) -> Recommendation:
    return Recommendation(
        workload_id=workload_id,
        workload_name=workload_name,
        recommendation_type=rec_type,
        reason="Test recommendation",
        current_instance_type=str(kwargs.get("current_type", "m5.xlarge")),
        suggested_instance_type=str(kwargs.get("target_type", "m5.large")),
        current_region=str(kwargs.get("current_region", "us-east-1")),
        suggested_region=str(kwargs.get("target_region", "eu-north-1")),
    )


class TestApplyResult:
    def test_create_result(self) -> None:
        result = ApplyResult(
            workload_id="i-123",
            workload_name="test",
            recommendation_type=RecommendationType.IDLE,
            status=ApplyStatus.SUCCESS,
            message="Terminated",
        )
        assert result.status == ApplyStatus.SUCCESS

    def test_all_statuses(self) -> None:
        for status in ApplyStatus:
            r = ApplyResult(
                workload_id="w",
                workload_name="w",
                recommendation_type=RecommendationType.IDLE,
                status=status,
                message="test",
            )
            assert r.status == status


class TestExecuteRecommendation:
    def test_dry_run_returns_dry_run_status(self) -> None:
        rec = _make_rec(RecommendationType.IDLE)
        mock_executor = MagicMock(spec=ApplyExecutor)
        result = execute_recommendation(mock_executor, rec, dry_run=True)
        assert result.status == ApplyStatus.DRY_RUN
        assert "[dry-run]" in result.message
        mock_executor.terminate_instance.assert_not_called()

    def test_idle_dispatches_terminate(self) -> None:
        rec = _make_rec(RecommendationType.IDLE)
        mock_executor = MagicMock(spec=ApplyExecutor)
        mock_executor.terminate_instance.return_value = ApplyResult(
            workload_id="i-123",
            workload_name="web-server",
            recommendation_type=RecommendationType.IDLE,
            status=ApplyStatus.SUCCESS,
            message="Terminated",
        )
        result = execute_recommendation(mock_executor, rec)
        assert result.status == ApplyStatus.SUCCESS
        mock_executor.terminate_instance.assert_called_once()

    def test_rightsize_dispatches_rightsize(self) -> None:
        rec = _make_rec(RecommendationType.RIGHTSIZE)
        mock_executor = MagicMock(spec=ApplyExecutor)
        mock_executor.rightsize_instance.return_value = ApplyResult(
            workload_id="i-123",
            workload_name="web-server",
            recommendation_type=RecommendationType.RIGHTSIZE,
            status=ApplyStatus.SUCCESS,
            message="Rightsized",
        )
        result = execute_recommendation(mock_executor, rec)
        assert result.status == ApplyStatus.SUCCESS
        mock_executor.rightsize_instance.assert_called_once()

    def test_region_move_dispatches_move(self) -> None:
        rec = _make_rec(RecommendationType.REGION_MOVE)
        mock_executor = MagicMock(spec=ApplyExecutor)
        mock_executor.move_region.return_value = ApplyResult(
            workload_id="i-123",
            workload_name="web-server",
            recommendation_type=RecommendationType.REGION_MOVE,
            status=ApplyStatus.NOT_SUPPORTED,
            message="Not supported",
        )
        result = execute_recommendation(mock_executor, rec)
        assert result.status == ApplyStatus.NOT_SUPPORTED


class TestAWSApplyExecutor:
    @patch("canopy.engine.apply.aws_executor.boto3")
    def test_terminate_success(self, mock_boto3: MagicMock) -> None:
        mock_ec2 = MagicMock()
        mock_boto3.Session.return_value.client.return_value = mock_ec2

        executor = AWSApplyExecutor()
        result = executor.terminate_instance("i-123", "us-east-1")
        assert result.status == ApplyStatus.SUCCESS
        mock_ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-123"])

    @patch("canopy.engine.apply.aws_executor.boto3")
    def test_terminate_failure(self, mock_boto3: MagicMock) -> None:
        from botocore.exceptions import ClientError

        mock_ec2 = MagicMock()
        mock_ec2.terminate_instances.side_effect = ClientError(
            {"Error": {"Code": "InvalidInstanceID", "Message": "not found"}},
            "TerminateInstances",
        )
        mock_boto3.Session.return_value.client.return_value = mock_ec2

        executor = AWSApplyExecutor()
        result = executor.terminate_instance("i-bad", "us-east-1")
        assert result.status == ApplyStatus.FAILED

    @patch("canopy.engine.apply.aws_executor.boto3")
    def test_rightsize_success(self, mock_boto3: MagicMock) -> None:
        mock_ec2 = MagicMock()
        mock_waiter = MagicMock()
        mock_ec2.get_waiter.return_value = mock_waiter
        mock_boto3.Session.return_value.client.return_value = mock_ec2

        executor = AWSApplyExecutor()
        result = executor.rightsize_instance("i-123", "us-east-1", "m5.xlarge", "m5.large")
        assert result.status == ApplyStatus.SUCCESS
        mock_ec2.stop_instances.assert_called_once()
        mock_ec2.modify_instance_attribute.assert_called_once()
        mock_ec2.start_instances.assert_called_once()

    @patch("canopy.engine.apply.aws_executor.boto3")
    def test_region_move_not_supported(self, mock_boto3: MagicMock) -> None:
        executor = AWSApplyExecutor()
        result = executor.move_region("i-123", "us-east-1", "eu-north-1")
        assert result.status == ApplyStatus.NOT_SUPPORTED

    def test_provider_name(self) -> None:
        with patch("canopy.engine.apply.aws_executor.boto3"):
            executor = AWSApplyExecutor()
            assert executor.provider_name == "aws"


class TestGCPApplyExecutor:
    def test_provider_name(self) -> None:
        executor = GCPApplyExecutor(project="test-project")
        assert executor.provider_name == "gcp"

    def test_region_move_not_supported(self) -> None:
        executor = GCPApplyExecutor()
        result = executor.move_region("inst-1", "us-central1", "europe-north1")
        assert result.status == ApplyStatus.NOT_SUPPORTED

    def test_terminate_without_library(self) -> None:
        executor = GCPApplyExecutor()
        # Will fail with ImportError since google-cloud-compute isn't installed in tests
        result = executor.terminate_instance("inst-1", "us-central1")
        assert result.status == ApplyStatus.FAILED
        assert "not installed" in result.message

    def test_rightsize_without_library(self) -> None:
        executor = GCPApplyExecutor()
        result = executor.rightsize_instance(
            "inst-1", "us-central1", "n2-standard-4", "n2-standard-2"
        )
        assert result.status == ApplyStatus.FAILED
        assert "not installed" in result.message
