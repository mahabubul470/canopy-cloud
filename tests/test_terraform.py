"""Tests for the Terraform/OpenTofu plan parser."""

from canopy.engine.iac.terraform import parse_plan_dict
from canopy.models.iac import ChangeAction


def _make_plan(resource_changes: list[dict]) -> dict:  # type: ignore[type-arg]
    return {
        "format_version": "1.2",
        "terraform_version": "1.9.0",
        "resource_changes": resource_changes,
    }


def _make_rc(
    address: str = "aws_instance.web",
    resource_type: str = "aws_instance",
    name: str = "web",
    actions: list[str] | None = None,
    before: dict | None = None,  # type: ignore[type-arg]
    after: dict | None = None,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    return {
        "address": address,
        "type": resource_type,
        "name": name,
        "change": {
            "actions": actions or ["create"],
            "before": before,
            "after": after or {},
        },
    }


def test_parse_create() -> None:
    plan_data = _make_plan(
        [
            _make_rc(
                actions=["create"],
                after={
                    "instance_type": "m5.xlarge",
                    "availability_zone": "us-east-1a",
                    "tags": {"Name": "web-server", "team": "platform"},
                },
            )
        ]
    )
    result = parse_plan_dict(plan_data)
    assert len(result.changes) == 1
    assert result.changes[0].action == ChangeAction.CREATE
    assert result.changes[0].after_instance_type == "m5.xlarge"
    assert result.changes[0].region == "us-east-1"
    assert result.changes[0].tags == {"Name": "web-server", "team": "platform"}
    assert result.has_changes


def test_parse_delete() -> None:
    plan_data = _make_plan(
        [
            _make_rc(
                actions=["delete"],
                before={
                    "instance_type": "t3.large",
                    "availability_zone": "us-west-2b",
                },
                after=None,
            )
        ]
    )
    result = parse_plan_dict(plan_data)
    assert len(result.changes) == 1
    assert result.changes[0].action == ChangeAction.DELETE
    assert result.changes[0].before_instance_type == "t3.large"
    assert result.changes[0].before_region == "us-west-2"


def test_parse_update() -> None:
    plan_data = _make_plan(
        [
            _make_rc(
                actions=["update"],
                before={
                    "instance_type": "m5.2xlarge",
                    "availability_zone": "us-east-1a",
                },
                after={
                    "instance_type": "m5.xlarge",
                    "availability_zone": "us-east-1a",
                },
            )
        ]
    )
    result = parse_plan_dict(plan_data)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.action == ChangeAction.UPDATE
    assert change.before_instance_type == "m5.2xlarge"
    assert change.after_instance_type == "m5.xlarge"


def test_parse_replace_is_update() -> None:
    """Terraform replace (delete + create) should map to UPDATE."""
    plan_data = _make_plan(
        [
            _make_rc(
                actions=["delete", "create"],
                before={"instance_type": "t3.large", "availability_zone": "us-east-1a"},
                after={"instance_type": "t3.xlarge", "availability_zone": "us-east-1a"},
            )
        ]
    )
    result = parse_plan_dict(plan_data)
    assert result.changes[0].action == ChangeAction.UPDATE


def test_ignores_non_compute_resources() -> None:
    plan_data = _make_plan(
        [
            _make_rc(resource_type="aws_s3_bucket", actions=["create"]),
            _make_rc(
                resource_type="aws_instance",
                actions=["create"],
                after={"instance_type": "t3.micro"},
            ),
        ]
    )
    result = parse_plan_dict(plan_data)
    assert len(result.changes) == 1
    assert result.changes[0].resource_type == "aws_instance"


def test_empty_plan() -> None:
    result = parse_plan_dict(_make_plan([]))
    assert len(result.changes) == 0
    assert not result.has_changes


def test_multiple_changes() -> None:
    plan_data = _make_plan(
        [
            _make_rc(
                address="aws_instance.web",
                actions=["create"],
                after={"instance_type": "c5.xlarge", "availability_zone": "eu-west-1a"},
            ),
            _make_rc(
                address="aws_instance.api",
                actions=["create"],
                after={"instance_type": "m5.large", "availability_zone": "eu-west-1b"},
            ),
            _make_rc(
                address="aws_instance.old",
                actions=["delete"],
                before={"instance_type": "t3.large", "availability_zone": "us-east-1c"},
            ),
        ]
    )
    result = parse_plan_dict(plan_data)
    assert len(result.changes) == 3
    assert len(result.creates) == 2
    assert len(result.deletes) == 1


def test_gcp_compute_instance() -> None:
    plan_data = _make_plan(
        [
            _make_rc(
                address="google_compute_instance.app",
                resource_type="google_compute_instance",
                name="app",
                actions=["create"],
                after={
                    "machine_type": "n2-standard-4",
                    "zone": "us-central1-a",
                    "labels": {"team": "data"},
                },
            )
        ]
    )
    result = parse_plan_dict(plan_data)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.provider == "gcp"
    assert change.after_instance_type == "n2-standard-4"
    assert change.tags == {"team": "data"}


def test_no_op_action() -> None:
    plan_data = _make_plan(
        [
            _make_rc(
                actions=["no-op"],
                before={"instance_type": "t3.micro"},
                after={"instance_type": "t3.micro"},
            )
        ]
    )
    result = parse_plan_dict(plan_data)
    assert len(result.changes) == 1
    assert result.changes[0].action == ChangeAction.NO_OP
    assert not result.has_changes
