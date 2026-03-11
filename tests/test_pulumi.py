"""Tests for the Pulumi preview parser."""

from canopy.engine.iac.pulumi import parse_preview_dict
from canopy.models.iac import ChangeAction


def _make_preview(steps: list[dict]) -> dict:  # type: ignore[type-arg]
    return {"steps": steps}


def _make_step(
    urn: str = "urn:pulumi:dev::mystack::aws:ec2/instance:Instance::web",
    resource_type: str = "aws:ec2/instance:Instance",
    op: str = "create",
    old_inputs: dict | None = None,  # type: ignore[type-arg]
    new_inputs: dict | None = None,  # type: ignore[type-arg]
) -> dict:  # type: ignore[type-arg]
    step: dict[str, object] = {
        "urn": urn,
        "type": resource_type,
        "op": op,
    }
    if old_inputs is not None:
        step["oldState"] = {"inputs": old_inputs}
    if new_inputs is not None:
        step["newState"] = {"inputs": new_inputs}
    else:
        step["newState"] = {"inputs": {}}
    return step


def test_parse_create() -> None:
    data = _make_preview(
        [
            _make_step(
                op="create",
                new_inputs={
                    "instanceType": "m5.xlarge",
                    "availabilityZone": "us-east-1a",
                    "tags": {"Name": "web", "team": "platform"},
                },
            )
        ]
    )
    result = parse_preview_dict(data)
    assert result.source == "pulumi"
    assert len(result.changes) == 1
    assert result.changes[0].action == ChangeAction.CREATE
    assert result.changes[0].after_instance_type == "m5.xlarge"
    assert result.changes[0].region == "us-east-1"
    assert result.changes[0].tags == {"Name": "web", "team": "platform"}
    assert result.changes[0].name == "web"


def test_parse_delete() -> None:
    data = _make_preview(
        [
            _make_step(
                op="delete",
                old_inputs={
                    "instanceType": "t3.large",
                    "availabilityZone": "us-west-2b",
                },
                new_inputs=None,
            )
        ]
    )
    result = parse_preview_dict(data)
    assert len(result.changes) == 1
    assert result.changes[0].action == ChangeAction.DELETE
    assert result.changes[0].before_instance_type == "t3.large"


def test_parse_update() -> None:
    data = _make_preview(
        [
            _make_step(
                op="update",
                old_inputs={
                    "instanceType": "m5.2xlarge",
                    "availabilityZone": "us-east-1a",
                },
                new_inputs={
                    "instanceType": "m5.xlarge",
                    "availabilityZone": "us-east-1a",
                },
            )
        ]
    )
    result = parse_preview_dict(data)
    assert result.changes[0].action == ChangeAction.UPDATE
    assert result.changes[0].before_instance_type == "m5.2xlarge"
    assert result.changes[0].after_instance_type == "m5.xlarge"


def test_replace_maps_to_update() -> None:
    data = _make_preview(
        [
            _make_step(
                op="replace",
                old_inputs={"instanceType": "t3.micro"},
                new_inputs={"instanceType": "t3.large"},
            )
        ]
    )
    result = parse_preview_dict(data)
    assert result.changes[0].action == ChangeAction.UPDATE


def test_ignores_non_compute() -> None:
    data = _make_preview(
        [
            _make_step(
                urn="urn:pulumi:dev::mystack::aws:s3/bucket:Bucket::mybucket",
                resource_type="aws:s3/bucket:Bucket",
                op="create",
            ),
            _make_step(op="create", new_inputs={"instanceType": "t3.micro"}),
        ]
    )
    result = parse_preview_dict(data)
    assert len(result.changes) == 1


def test_empty_preview() -> None:
    result = parse_preview_dict(_make_preview([]))
    assert len(result.changes) == 0
    assert not result.has_changes


def test_same_is_no_op() -> None:
    data = _make_preview(
        [
            _make_step(
                op="same",
                old_inputs={"instanceType": "t3.micro"},
                new_inputs={"instanceType": "t3.micro"},
            )
        ]
    )
    result = parse_preview_dict(data)
    assert result.changes[0].action == ChangeAction.NO_OP


def test_gcp_instance() -> None:
    data = _make_preview(
        [
            _make_step(
                urn="urn:pulumi:dev::mystack::gcp:compute/instance:Instance::app",
                resource_type="gcp:compute/instance:Instance",
                op="create",
                new_inputs={
                    "machineType": "n2-standard-4",
                    "zone": "us-central1-a",
                    "labels": {"env": "prod"},
                },
            )
        ]
    )
    result = parse_preview_dict(data)
    assert len(result.changes) == 1
    change = result.changes[0]
    assert change.provider == "gcp"
    assert change.after_instance_type == "n2-standard-4"
    assert change.tags == {"env": "prod"}
