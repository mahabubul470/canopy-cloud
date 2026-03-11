"""Terraform / OpenTofu plan JSON parser.

Parses the output of `terraform show -json <planfile>` or
`tofu show -json <planfile>` into Canopy's ResourceChange model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from canopy.models.iac import ChangeAction, PlanSummary, ResourceChange

# Terraform resource types we can analyze for cost/carbon
_COMPUTE_RESOURCE_TYPES = frozenset(
    {
        "aws_instance",
        "aws_spot_instance_request",
        "google_compute_instance",
        "azurerm_virtual_machine",
        "azurerm_linux_virtual_machine",
        "azurerm_windows_virtual_machine",
    }
)

# Map terraform actions to our ChangeAction
_ACTION_MAP: dict[str, ChangeAction] = {
    "create": ChangeAction.CREATE,
    "update": ChangeAction.UPDATE,
    "delete": ChangeAction.DELETE,
    "no-op": ChangeAction.NO_OP,
    "read": ChangeAction.READ,
}


def parse_plan_json(path: Path) -> PlanSummary:
    """Parse a Terraform/OpenTofu plan JSON file."""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    return parse_plan_dict(data)


def parse_plan_dict(data: dict[str, Any]) -> PlanSummary:
    """Parse a Terraform/OpenTofu plan from a dictionary."""
    changes: list[ResourceChange] = []
    resource_changes = data.get("resource_changes", [])

    for rc in resource_changes:
        change = _parse_resource_change(rc)
        if change is not None:
            changes.append(change)

    # Detect source (terraform vs opentofu) from format_version
    source = "terraform"
    if (
        data.get("terraform_version", "").startswith("1.")
        and "opentofu" in json.dumps(data.get("provider_schemas", {})).lower()
    ):
        source = "opentofu"

    return PlanSummary(source=source, changes=changes)


def _parse_resource_change(rc: dict[str, Any]) -> ResourceChange | None:
    """Parse a single resource_change entry."""
    resource_type = rc.get("type", "")
    if resource_type not in _COMPUTE_RESOURCE_TYPES:
        return None

    change = rc.get("change", {})
    actions: list[str] = change.get("actions", [])
    action = _resolve_action(actions)

    before: dict[str, Any] = change.get("before") or {}
    after: dict[str, Any] = change.get("after") or {}

    provider = _detect_provider(resource_type)
    region = _extract_region(after, before, provider)

    before_instance_type = _extract_instance_type(before, provider)
    after_instance_type = _extract_instance_type(after, provider)

    # Use after values for creates/updates, before for deletes
    instance_type = after_instance_type or before_instance_type

    tags = _extract_tags(after) or _extract_tags(before)

    return ResourceChange(
        address=rc.get("address", ""),
        resource_type=resource_type,
        name=rc.get("name", ""),
        provider=provider,
        action=action,
        region=region,
        instance_type=instance_type,
        count=1,
        tags=tags,
        before_instance_type=before_instance_type,
        before_region=_extract_region(before, {}, provider),
        after_instance_type=after_instance_type,
        after_region=_extract_region(after, {}, provider),
    )


def _resolve_action(actions: list[str]) -> ChangeAction:
    """Resolve Terraform's action list into a single ChangeAction.

    Terraform uses lists like ["create"], ["delete", "create"] (replace), etc.
    """
    if not actions:
        return ChangeAction.NO_OP
    if "delete" in actions and "create" in actions:
        return ChangeAction.UPDATE  # replace = update for our purposes
    for a in actions:
        mapped = _ACTION_MAP.get(a)
        if mapped is not None:
            return mapped
    return ChangeAction.NO_OP


def _detect_provider(resource_type: str) -> str:
    if resource_type.startswith("aws_"):
        return "aws"
    if resource_type.startswith("google_"):
        return "gcp"
    if resource_type.startswith("azurerm_"):
        return "azure"
    return "unknown"


def _extract_instance_type(values: dict[str, Any], provider: str) -> str | None:
    if provider == "aws":
        return values.get("instance_type")
    if provider == "gcp":
        return values.get("machine_type")
    if provider == "azure":
        return values.get("size") or values.get("vm_size")
    return None


def _extract_region(
    primary: dict[str, Any],
    fallback: dict[str, Any],
    provider: str,
) -> str | None:
    """Extract region from resource values."""
    if provider == "aws":
        # AWS instances don't have region directly — it comes from the provider config
        # Check availability_zone and strip the trailing letter
        az = primary.get("availability_zone") or fallback.get("availability_zone")
        if az and isinstance(az, str) and len(az) > 1:
            result: str = az[:-1]  # us-east-1a → us-east-1
            return result
        return None
    if provider == "gcp":
        zone = primary.get("zone") or fallback.get("zone")
        if zone and isinstance(zone, str):
            # zones look like us-central1-a, regions like us-central1
            parts = zone.rsplit("-", 1)
            region_name: str = parts[0] if len(parts) == 2 else zone
            return region_name
        return None
    if provider == "azure":
        return primary.get("location") or fallback.get("location")
    return None


def _extract_tags(values: dict[str, Any]) -> dict[str, str]:
    """Extract tags from resource values."""
    tags = values.get("tags")
    if isinstance(tags, dict):
        return {str(k): str(v) for k, v in tags.items()}
    # GCP uses labels instead of tags
    labels = values.get("labels")
    if isinstance(labels, dict):
        return {str(k): str(v) for k, v in labels.items()}
    return {}
