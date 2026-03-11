"""AWS cloud provider implementation."""

from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from canopy.engine.providers.base import CloudProvider
from canopy.models.core import CostSnapshot, Workload, WorkloadType

# Approximate on-demand hourly prices (USD) for common instance types.
# In production this would come from the AWS Pricing API.
INSTANCE_PRICING: dict[str, float] = {
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768,
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "c5.2xlarge": 0.34,
    "c5.4xlarge": 0.68,
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "p4d.24xlarge": 32.77,
    "p5.48xlarge": 98.32,
    "g5.xlarge": 1.006,
    "g5.2xlarge": 1.212,
}

# vCPU and memory for common instance types
INSTANCE_SPECS: dict[str, tuple[int, float]] = {
    "t3.micro": (2, 1.0),
    "t3.small": (2, 2.0),
    "t3.medium": (2, 4.0),
    "t3.large": (2, 8.0),
    "t3.xlarge": (4, 16.0),
    "m5.large": (2, 8.0),
    "m5.xlarge": (4, 16.0),
    "m5.2xlarge": (8, 32.0),
    "m5.4xlarge": (16, 64.0),
    "c5.large": (2, 4.0),
    "c5.xlarge": (4, 8.0),
    "c5.2xlarge": (8, 16.0),
    "c5.4xlarge": (16, 32.0),
    "r5.large": (2, 16.0),
    "r5.xlarge": (4, 32.0),
    "r5.2xlarge": (8, 64.0),
    "p4d.24xlarge": (96, 1152.0),
    "p5.48xlarge": (192, 2048.0),
    "g5.xlarge": (4, 16.0),
    "g5.2xlarge": (8, 32.0),
}


class AWSProvider(CloudProvider):
    """AWS cloud provider using boto3."""

    def __init__(self, profile: str | None = None, default_region: str = "us-east-1") -> None:
        session_kwargs: dict[str, str] = {}
        if profile:
            session_kwargs["profile_name"] = profile
        session_kwargs["region_name"] = default_region
        self._session = boto3.Session(**session_kwargs)
        self._default_region = default_region

    @property
    def name(self) -> str:
        return "aws"

    def get_regions(self) -> list[str]:
        ec2 = self._session.client("ec2", region_name=self._default_region)
        response = ec2.describe_regions(
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
        )
        return [r["RegionName"] for r in response["Regions"]]

    def list_workloads(self, region: str | None = None) -> list[Workload]:
        regions = [region] if region else [self._default_region]
        workloads: list[Workload] = []

        for r in regions:
            try:
                workloads.extend(self._list_ec2_instances(r))
            except ClientError:
                continue

        return workloads

    def _list_ec2_instances(self, region: str) -> list[Workload]:
        ec2 = self._session.client("ec2", region_name=region)
        cw = self._session.client("cloudwatch", region_name=region)

        paginator = ec2.get_paginator("describe_instances")
        workloads: list[Workload] = []

        for page in paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        ):
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_id = instance["InstanceId"]
                    instance_type = instance.get("InstanceType", "unknown")
                    vcpus, memory_gb = INSTANCE_SPECS.get(instance_type, (0, 0.0))

                    tags = {}
                    name = instance_id
                    for tag in instance.get("Tags", []):
                        tags[tag["Key"]] = tag["Value"]
                        if tag["Key"] == "Name":
                            name = tag["Value"]

                    gpu_count = 0
                    gpu_type = None
                    if instance_type.startswith(("p", "g")):
                        gpu_count = 1
                        gpu_type = "NVIDIA"

                    avg_cpu = self._get_avg_cpu(cw, instance_id)

                    workloads.append(
                        Workload(
                            id=instance_id,
                            name=name,
                            provider="aws",
                            region=region,
                            workload_type=WorkloadType.COMPUTE,
                            instance_type=instance_type,
                            vcpus=vcpus,
                            memory_gb=memory_gb,
                            gpu_count=gpu_count,
                            gpu_type=gpu_type,
                            avg_cpu_percent=avg_cpu,
                            tags=tags,
                            launched_at=instance.get("LaunchTime"),
                        )
                    )

        return workloads

    def _get_avg_cpu(self, cw_client: object, instance_id: str) -> float:
        """Get average CPU utilization over the last 7 days."""
        try:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=7)
            response = cw_client.get_metric_statistics(  # type: ignore[union-attr]
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start,
                EndTime=end,
                Period=86400,
                Statistics=["Average"],
            )
            datapoints = response.get("Datapoints", [])
            if not datapoints:
                return 0.0
            return sum(d["Average"] for d in datapoints) / len(datapoints)
        except Exception:
            return 0.0

    def get_cost(self, workload: Workload) -> CostSnapshot:
        hourly = INSTANCE_PRICING.get(workload.instance_type or "", 0.0)
        return CostSnapshot(
            workload_id=workload.id,
            hourly_cost_usd=hourly,
            monthly_cost_usd=hourly * 730,
        )
