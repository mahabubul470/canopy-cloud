"""Tests for the policy engine."""

from canopy.engine.policy import (
    evaluate_all,
    evaluate_budget,
    evaluate_carbon,
    evaluate_ecoweight,
    evaluate_region,
    evaluate_tags,
)
from canopy.models.core import (
    CarbonSnapshot,
    CostSnapshot,
    EcoWeight,
    Workload,
    WorkloadType,
)
from canopy.models.policy import Policy, Severity


def _make_cost(workload_id: str = "w1", monthly: float = 100.0) -> CostSnapshot:
    return CostSnapshot(
        workload_id=workload_id,
        hourly_cost_usd=monthly / 730,
        monthly_cost_usd=monthly,
    )


def _make_carbon(
    workload_id: str = "w1", monthly_kg: float = 10.0, region: str = "us-east-1"
) -> CarbonSnapshot:
    return CarbonSnapshot(
        workload_id=workload_id,
        region=region,
        grid_intensity_gco2_kwh=400,
        estimated_power_kw=0.05,
        hourly_carbon_gco2=monthly_kg * 1000 / 730,
        monthly_carbon_kg_co2=monthly_kg,
    )


def _make_ecoweight(
    workload_id: str = "w1",
    name: str = "test",
    monthly_cost: float = 100.0,
    monthly_carbon_kg: float = 10.0,
) -> EcoWeight:
    return EcoWeight(
        workload_id=workload_id,
        workload_name=name,
        cost=_make_cost(workload_id, monthly_cost),
        carbon=_make_carbon(workload_id, monthly_carbon_kg),
        alpha=0.5,
        beta=0.5,
        budget_hourly_usd=1.0,
        carbon_hourly_gco2=100.0,
    )


def _make_workload(
    workload_id: str = "w1",
    name: str = "test",
    tags: dict[str, str] | None = None,
) -> Workload:
    return Workload(
        id=workload_id,
        name=name,
        provider="aws",
        region="us-east-1",
        workload_type=WorkloadType.COMPUTE,
        tags=tags or {},
    )


# --- EcoWeight policy tests ---


def test_ecoweight_under_threshold() -> None:
    policy = Policy()
    ew = _make_ecoweight(monthly_cost=50.0, monthly_carbon_kg=5.0)
    violations = evaluate_ecoweight(ew, policy)
    assert len(violations) == 0


def test_ecoweight_exceeds_alert() -> None:
    policy = Policy()
    policy.ecoweight.alert_threshold = 0.5
    ew = _make_ecoweight(monthly_cost=500.0, monthly_carbon_kg=50.0)
    violations = evaluate_ecoweight(ew, policy)
    # Score should be above alert but depends on exact calculation
    assert len(violations) >= 1


def test_ecoweight_exceeds_max() -> None:
    policy = Policy()
    policy.ecoweight.max_score = 0.1
    ew = _make_ecoweight(monthly_cost=500.0, monthly_carbon_kg=50.0)
    violations = evaluate_ecoweight(ew, policy)
    assert any(v.severity == Severity.BLOCK for v in violations)


# --- Budget policy tests ---


def test_budget_under_cap() -> None:
    policy = Policy()
    policy.budget.monthly_cap_usd = 200.0
    cost = _make_cost(monthly=100.0)
    violations = evaluate_budget(cost, policy)
    assert len(violations) == 0


def test_budget_exceeds_cap() -> None:
    policy = Policy()
    policy.budget.monthly_cap_usd = 50.0
    cost = _make_cost(monthly=100.0)
    violations = evaluate_budget(cost, policy)
    assert len(violations) == 1
    assert violations[0].severity == Severity.BLOCK


def test_budget_exceeds_alert_threshold() -> None:
    policy = Policy()
    policy.budget.monthly_cap_usd = 120.0
    policy.budget.alert_threshold = 0.8
    cost = _make_cost(monthly=100.0)
    violations = evaluate_budget(cost, policy)
    assert len(violations) == 1
    assert violations[0].severity == Severity.WARN


def test_budget_no_cap() -> None:
    policy = Policy()
    cost = _make_cost(monthly=999999.0)
    violations = evaluate_budget(cost, policy)
    assert len(violations) == 0


# --- Carbon policy tests ---


def test_carbon_under_cap() -> None:
    policy = Policy()
    policy.carbon.monthly_cap_kg_co2 = 100.0
    carbon = _make_carbon(monthly_kg=10.0)
    violations = evaluate_carbon(carbon, policy)
    assert len(violations) == 0


def test_carbon_exceeds_cap() -> None:
    policy = Policy()
    policy.carbon.monthly_cap_kg_co2 = 5.0
    carbon = _make_carbon(monthly_kg=10.0)
    violations = evaluate_carbon(carbon, policy)
    assert len(violations) == 1
    assert violations[0].severity == Severity.BLOCK


# --- Region policy tests ---


def test_region_allowed() -> None:
    policy = Policy()
    policy.carbon.allowed_regions = ["us-*", "eu-*"]
    violations = evaluate_region("us-east-1", "silver", policy)
    assert len(violations) == 0


def test_region_not_allowed() -> None:
    policy = Policy()
    policy.carbon.allowed_regions = ["eu-*"]
    violations = evaluate_region("us-east-1", "silver", policy)
    assert any(v.policy_name == "carbon.allowed_regions" for v in violations)


def test_region_tier_too_low() -> None:
    policy = Policy()
    policy.carbon.min_region_tier = "gold"
    violations = evaluate_region("us-east-1", "bronze", policy)
    assert any(v.policy_name == "carbon.min_region_tier" for v in violations)


def test_region_tier_sufficient() -> None:
    policy = Policy()
    policy.carbon.min_region_tier = "silver"
    violations = evaluate_region("eu-north-1", "platinum", policy)
    assert len(violations) == 0


# --- Tagging policy tests ---


def test_tags_all_present() -> None:
    policy = Policy()
    policy.tagging.required_tags = ["team", "env"]
    workload = _make_workload(tags={"team": "platform", "env": "prod"})
    violations = evaluate_tags(workload, policy)
    assert len(violations) == 0


def test_tags_missing() -> None:
    policy = Policy()
    policy.tagging.required_tags = ["team", "env"]
    policy.tagging.severity = Severity.WARN
    workload = _make_workload(tags={"team": "platform"})
    violations = evaluate_tags(workload, policy)
    assert len(violations) == 1
    assert "env" in violations[0].message
    assert violations[0].severity == Severity.WARN


def test_tags_no_requirements() -> None:
    policy = Policy()
    workload = _make_workload(tags={})
    violations = evaluate_tags(workload, policy)
    assert len(violations) == 0


# --- evaluate_all integration test ---


def test_evaluate_all() -> None:
    policy = Policy()
    policy.budget.monthly_cap_usd = 50.0
    policy.tagging.required_tags = ["team"]

    workload = _make_workload(tags={})
    ew = _make_ecoweight(monthly_cost=100.0)

    result = evaluate_all([workload], [ew], policy, {"us-east-1": "bronze"})
    assert result.resource_count == 1
    # Should have budget violation + tagging violation at minimum
    assert len(result.violations) >= 2
    assert result.has_blocking_violations
