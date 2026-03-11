"""Pulumi preview JSON parser.

Parses the output of `pulumi preview --json` into Canopy's ResourceChange model.
"""

from __future__ import annotations

from typing import Any

from canopy.models.iac import ChangeAction, PlanSummary, ResourceChange

# Pulumi resource types we can analyze for cost/carbon
_COMPUTE_RESOURCE_TYPES = frozenset(
    {
        "aws:ec2/instance:Instance",
        "aws:ec2/spotInstanceRequest:SpotInstanceRequest",
        "gcp:compute/instance:Instance",
        "azure:compute/virtualMachine:VirtualMachine",
        "azure:compute/linuxVirtualMachine:LinuxVirtualMachine",
        "azure:compute/windowsVirtualMachine:WindowsVirtualMachine",
    }
)

# Pulumi op types to our ChangeAction
_OP_MAP: dict[str, ChangeAction] = {
    "create": ChangeAction.CREATE,
    "update": ChangeAction.UPDATE,
    "delete": ChangeAction.DELETE,
    "replace": ChangeAction.UPDATE,
    "same": ChangeAction.NO_OP,
    "read": ChangeAction.READ,
    "create-replacement": ChangeAction.CREATE,
    "delete-replaced": ChangeAction.DELETE,
}


def parse_preview_dict(data: dict[str, Any]) -> PlanSummary:
    """Parse a Pulumi preview JSON output from a dictionary."""
    changes: list[ResourceChange] = []

    # Pulumi preview JSON has a "steps" array
    steps = data.get("steps", [])
    for step in steps:
        change = _parse_step(step)
        if change is not None:
            changes.append(change)

    return PlanSummary(source="pulumi", changes=changes)


def _parse_step(step: dict[str, Any]) -> ResourceChange | None:
    """Parse a single Pulumi preview step."""
    resource_type = step.get("type", "")
    if resource_type not in _COMPUTE_RESOURCE_TYPES:
        return None

    op = step.get("op", "same")
    action = _OP_MAP.get(op, ChangeAction.NO_OP)

    urn = step.get("urn", "")
    name = urn.rsplit("::", 1)[-1] if "::" in urn else step.get("urn", "")

    old_state: dict[str, Any] = step.get("oldState", {}).get("inputs", {})
    new_state: dict[str, Any] = step.get("newState", {}).get("inputs", {})

    provider = _detect_provider(resource_type)

    before_instance_type = _extract_instance_type(old_state, provider)
    after_instance_type = _extract_instance_type(new_state, provider)
    instance_type = after_instance_type or before_instance_type

    before_region = _extract_region(old_state, provider)
    after_region = _extract_region(new_state, provider)
    region = after_region or before_region

    tags = _extract_tags(new_state) or _extract_tags(old_state)

    return ResourceChange(
        address=urn,
        resource_type=resource_type,
        name=name,
        provider=provider,
        action=action,
        region=region,
        instance_type=instance_type,
        count=1,
        tags=tags,
        before_instance_type=before_instance_type,
        before_region=before_region,
        after_instance_type=after_instance_type,
        after_region=after_region,
    )


def _detect_provider(resource_type: str) -> str:
    if resource_type.startswith("aws:"):
        return "aws"
    if resource_type.startswith("gcp:"):
        return "gcp"
    if resource_type.startswith("azure:"):
        return "azure"
    return "unknown"


def _extract_instance_type(inputs: dict[str, Any], provider: str) -> str | None:
    if provider == "aws":
        return inputs.get("instanceType")
    if provider == "gcp":
        return inputs.get("machineType")
    if provider == "azure":
        return inputs.get("size") or inputs.get("vmSize")
    return None


def _extract_region(inputs: dict[str, Any], provider: str) -> str | None:
    if provider == "aws":
        az = inputs.get("availabilityZone")
        if az and isinstance(az, str) and len(az) > 1:
            result: str = az[:-1]
            return result
        return None
    if provider == "gcp":
        zone = inputs.get("zone")
        if zone and isinstance(zone, str):
            parts = zone.rsplit("-", 1)
            region_name: str = parts[0] if len(parts) == 2 else zone
            return region_name
        return None
    if provider == "azure":
        loc = inputs.get("location")
        if isinstance(loc, str):
            return loc
        return None
    return None


def _extract_tags(inputs: dict[str, Any]) -> dict[str, str]:
    tags = inputs.get("tags")
    if isinstance(tags, dict):
        return {str(k): str(v) for k, v in tags.items()}
    labels = inputs.get("labels")
    if isinstance(labels, dict):
        return {str(k): str(v) for k, v in labels.items()}
    return {}
