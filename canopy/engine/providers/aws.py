"""AWS cloud provider implementation."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

from canopy.engine.providers.base import CloudProvider
from canopy.models.core import CostSnapshot, Workload, WorkloadType

logger = logging.getLogger(__name__)

# Approximate on-demand hourly prices (USD) for common instance types.
# Used as fallback when the AWS Pricing API is unavailable.
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

# AWS region code to Pricing API region name mapping
_REGION_NAMES: dict[str, str] = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-north-1": "EU (Stockholm)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "sa-east-1": "South America (Sao Paulo)",
    "ca-central-1": "Canada (Central)",
}


class AWSProvider(CloudProvider):
    """AWS cloud provider using boto3."""

    def __init__(self, profile: str | None = None, default_region: str = "us-east-1") -> None:
        self._session = boto3.Session(
            profile_name=profile,
            region_name=default_region,
        )
        self._default_region = default_region
        self._price_cache: dict[str, float] = {}

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

    def _get_avg_cpu(self, cw_client: Any, instance_id: str) -> float:
        """Get average CPU utilization over the last 7 days."""
        try:
            end = datetime.now(UTC)
            start = end - timedelta(days=7)
            response = cw_client.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start,
                EndTime=end,
                Period=86400,
                Statistics=["Average"],
            )
            datapoints: list[dict[str, Any]] = response.get("Datapoints", [])
            if not datapoints:
                return 0.0
            return float(sum(d["Average"] for d in datapoints) / len(datapoints))
        except Exception:
            return 0.0

    def get_cost(self, workload: Workload) -> CostSnapshot:
        hourly = self._get_cached_price(workload.instance_type or "", workload.region)
        return CostSnapshot(
            workload_id=workload.id,
            hourly_cost_usd=hourly,
            monthly_cost_usd=hourly * 730,
        )

    def _get_cached_price(self, instance_type: str, region: str) -> float:
        """Get price with session cache → live API → static fallback."""
        cache_key = f"{region}:{instance_type}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        live_price = self._fetch_live_price(instance_type, region)
        if live_price is not None:
            self._price_cache[cache_key] = live_price
            return live_price

        static_price = INSTANCE_PRICING.get(instance_type, 0.0)
        self._price_cache[cache_key] = static_price
        return static_price

    def _fetch_live_price(self, instance_type: str, region: str) -> float | None:
        """Fetch on-demand Linux price from AWS Pricing API."""
        location = _REGION_NAMES.get(region)
        if not location:
            return None

        try:
            pricing = self._session.client("pricing", region_name="us-east-1")
            response = pricing.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                    {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                ],
                MaxResults=1,
            )
            price_list: list[str] = response.get("PriceList", [])
            if not price_list:
                return None

            product = json.loads(price_list[0])
            terms = product.get("terms", {}).get("OnDemand", {})
            for term in terms.values():
                for dimension in term.get("priceDimensions", {}).values():
                    price_str = dimension.get("pricePerUnit", {}).get("USD", "0")
                    price = float(price_str)
                    if price > 0:
                        return price
        except Exception:
            logger.debug("Pricing API call failed for %s in %s", instance_type, region)

        return None
