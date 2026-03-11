"""Tests for the plan estimation engine."""

from canopy.engine.plan import estimate_plan
from canopy.models.iac import ChangeAction, PlanSummary, ResourceChange
from canopy.models.policy import Policy, Severity


def _make_change(
    address: str = "aws_instance.web",
    action: ChangeAction = ChangeAction.CREATE,
    before_instance_type: str | None = None,
    after_instance_type: str | None = "m5.xlarge",
    before_region: str | None = None,
    after_region: str | None = "us-east-1",
    tags: dict[str, str] | None = None,
) -> ResourceChange:
    return ResourceChange(
        address=address,
        resource_type="aws_instance",
        name=address.split(".")[-1],
        provider="aws",
        action=action,
        instance_type=after_instance_type or before_instance_type,
        region=after_region or before_region,
        tags=tags or {},
        before_instance_type=before_instance_type,
        before_region=before_region,
        after_instance_type=after_instance_type,
        after_region=after_region,
    )


def test_create_has_positive_cost_delta() -> None:
    plan = PlanSummary(
        source="terraform",
        changes=[_make_change(action=ChangeAction.CREATE, after_instance_type="m5.xlarge")],
    )
    result = estimate_plan(plan)
    assert len(result.resources) == 1
    assert result.resources[0].monthly_cost_usd > 0
    assert result.resources[0].cost_delta_usd > 0
    assert result.total_monthly_cost_usd > 0


def test_delete_has_negative_cost_delta() -> None:
    plan = PlanSummary(
        source="terraform",
        changes=[
            _make_change(
                action=ChangeAction.DELETE,
                before_instance_type="m5.xlarge",
                after_instance_type=None,
                before_region="us-east-1",
                after_region=None,
            )
        ],
    )
    result = estimate_plan(plan)
    assert len(result.resources) == 1
    assert result.resources[0].monthly_cost_usd == 0.0
    assert result.resources[0].cost_delta_usd < 0
    assert result.total_cost_delta_usd < 0


def test_update_downsize_saves_cost() -> None:
    plan = PlanSummary(
        source="terraform",
        changes=[
            _make_change(
                action=ChangeAction.UPDATE,
                before_instance_type="m5.2xlarge",
                after_instance_type="m5.xlarge",
                before_region="us-east-1",
                after_region="us-east-1",
            )
        ],
    )
    result = estimate_plan(plan)
    assert result.resources[0].cost_delta_usd < 0


def test_update_upsize_adds_cost() -> None:
    plan = PlanSummary(
        source="terraform",
        changes=[
            _make_change(
                action=ChangeAction.UPDATE,
                before_instance_type="m5.xlarge",
                after_instance_type="m5.2xlarge",
                before_region="us-east-1",
                after_region="us-east-1",
            )
        ],
    )
    result = estimate_plan(plan)
    assert result.resources[0].cost_delta_usd > 0


def test_no_op_has_zero_delta() -> None:
    plan = PlanSummary(
        source="terraform",
        changes=[
            _make_change(
                action=ChangeAction.NO_OP,
                after_instance_type="t3.micro",
            )
        ],
    )
    result = estimate_plan(plan)
    assert result.resources[0].cost_delta_usd == 0.0
    assert result.resources[0].carbon_delta_kg == 0.0


def test_carbon_estimated_for_create() -> None:
    plan = PlanSummary(
        source="terraform",
        changes=[_make_change(action=ChangeAction.CREATE, after_instance_type="m5.xlarge")],
    )
    result = estimate_plan(plan)
    assert result.resources[0].monthly_carbon_kg_co2 > 0
    assert result.total_monthly_carbon_kg > 0


def test_policy_budget_violation() -> None:
    policy = Policy()
    policy.budget.monthly_cap_usd = 10.0  # Very low cap
    plan = PlanSummary(
        source="terraform",
        changes=[_make_change(action=ChangeAction.CREATE, after_instance_type="m5.4xlarge")],
    )
    result = estimate_plan(plan, policy=policy)
    budget_violations = [v for v in result.violations if "budget" in v.policy_name]
    assert len(budget_violations) > 0


def test_policy_region_violation() -> None:
    policy = Policy()
    policy.carbon.allowed_regions = ["eu-*"]
    plan = PlanSummary(
        source="terraform",
        changes=[
            _make_change(
                action=ChangeAction.CREATE,
                after_instance_type="t3.micro",
                after_region="us-east-1",
            )
        ],
    )
    result = estimate_plan(plan, policy=policy)
    region_violations = [v for v in result.violations if "allowed_regions" in v.policy_name]
    assert len(region_violations) > 0


def test_policy_tagging_violation() -> None:
    policy = Policy()
    policy.tagging.required_tags = ["team", "env"]
    policy.tagging.severity = Severity.WARN
    plan = PlanSummary(
        source="terraform",
        changes=[_make_change(action=ChangeAction.CREATE, tags={"team": "platform"})],
    )
    result = estimate_plan(plan, policy=policy)
    tag_violations = [v for v in result.violations if "tagging" in v.policy_name]
    assert len(tag_violations) == 1
    assert "env" in tag_violations[0].message


def test_multiple_resources() -> None:
    plan = PlanSummary(
        source="terraform",
        changes=[
            _make_change(
                address="aws_instance.web",
                action=ChangeAction.CREATE,
                after_instance_type="c5.xlarge",
            ),
            _make_change(
                address="aws_instance.api",
                action=ChangeAction.CREATE,
                after_instance_type="m5.large",
            ),
            _make_change(
                address="aws_instance.old",
                action=ChangeAction.DELETE,
                before_instance_type="t3.large",
                after_instance_type=None,
                before_region="us-east-1",
                after_region=None,
            ),
        ],
    )
    result = estimate_plan(plan)
    assert len(result.resources) == 3
    # Two creates + one delete = net positive cost
    creates_cost = sum(
        r.monthly_cost_usd for r in result.resources if r.action == ChangeAction.CREATE
    )
    assert creates_cost > 0


def test_empty_plan() -> None:
    plan = PlanSummary(source="terraform", changes=[])
    result = estimate_plan(plan)
    assert len(result.resources) == 0
    assert result.total_monthly_cost_usd == 0.0
    assert not result.has_blocking_violations
