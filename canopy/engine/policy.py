"""Policy engine for evaluating resources against organizational constraints."""

from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

from canopy.models.core import CarbonSnapshot, CostSnapshot, EcoWeight, Workload
from canopy.models.policy import (
    Policy,
    PolicyResult,
    Severity,
    Violation,
)

# Tier ordering for min_region_tier enforcement
_TIER_RANK: dict[str, int] = {
    "platinum": 4,
    "gold": 3,
    "silver": 2,
    "bronze": 1,
}


def load_policy(path: Path | None = None) -> Policy:
    """Load a policy file from YAML.

    Search order:
    1. Explicit path (if provided)
    2. ./canopy-policy.yaml
    3. Defaults
    """
    candidates = [path] if path else [Path("canopy-policy.yaml")]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return Policy(**data)
    return Policy()


def evaluate_ecoweight(
    ecoweight: EcoWeight,
    policy: Policy,
) -> list[Violation]:
    """Check a scored workload against EcoWeight thresholds."""
    violations: list[Violation] = []
    score = ecoweight.score

    if score > policy.ecoweight.max_score:
        violations.append(
            Violation(
                severity=Severity.BLOCK,
                policy_name="ecoweight.max_score",
                message=(f"EcoWeight {score:.2f} exceeds maximum {policy.ecoweight.max_score}"),
                resource_id=ecoweight.workload_id,
                resource_name=ecoweight.workload_name,
            )
        )
    elif score > policy.ecoweight.alert_threshold:
        violations.append(
            Violation(
                severity=Severity.WARN,
                policy_name="ecoweight.alert_threshold",
                message=(
                    f"EcoWeight {score:.2f} exceeds alert threshold "
                    f"{policy.ecoweight.alert_threshold}"
                ),
                resource_id=ecoweight.workload_id,
                resource_name=ecoweight.workload_name,
            )
        )

    return violations


def evaluate_budget(
    cost: CostSnapshot,
    policy: Policy,
    resource_id: str | None = None,
    resource_name: str | None = None,
) -> list[Violation]:
    """Check cost against budget cap."""
    violations: list[Violation] = []

    if policy.budget.monthly_cap_usd is not None:
        if cost.monthly_cost_usd > policy.budget.monthly_cap_usd:
            violations.append(
                Violation(
                    severity=Severity.BLOCK,
                    policy_name="budget.monthly_cap_usd",
                    message=(
                        f"Monthly cost ${cost.monthly_cost_usd:,.2f} exceeds "
                        f"cap ${policy.budget.monthly_cap_usd:,.2f}"
                    ),
                    resource_id=resource_id,
                    resource_name=resource_name,
                )
            )
        elif cost.monthly_cost_usd > policy.budget.monthly_cap_usd * policy.budget.alert_threshold:
            violations.append(
                Violation(
                    severity=Severity.WARN,
                    policy_name="budget.alert_threshold",
                    message=(
                        f"Monthly cost ${cost.monthly_cost_usd:,.2f} exceeds "
                        f"{policy.budget.alert_threshold:.0%} of cap "
                        f"${policy.budget.monthly_cap_usd:,.2f}"
                    ),
                    resource_id=resource_id,
                    resource_name=resource_name,
                )
            )

    return violations


def evaluate_carbon(
    carbon: CarbonSnapshot,
    policy: Policy,
    resource_id: str | None = None,
    resource_name: str | None = None,
) -> list[Violation]:
    """Check carbon against cap."""
    violations: list[Violation] = []

    if policy.carbon.monthly_cap_kg_co2 is not None:
        if carbon.monthly_carbon_kg_co2 > policy.carbon.monthly_cap_kg_co2:
            violations.append(
                Violation(
                    severity=Severity.BLOCK,
                    policy_name="carbon.monthly_cap_kg_co2",
                    message=(
                        f"Monthly carbon {carbon.monthly_carbon_kg_co2:,.1f} kg CO₂ exceeds "
                        f"cap {policy.carbon.monthly_cap_kg_co2:,.1f} kg CO₂"
                    ),
                    resource_id=resource_id,
                    resource_name=resource_name,
                )
            )

    return violations


def evaluate_region(
    region: str,
    region_tier: str,
    policy: Policy,
    resource_id: str | None = None,
    resource_name: str | None = None,
) -> list[Violation]:
    """Check region against allowed regions and minimum tier."""
    violations: list[Violation] = []

    # Check allowed regions (glob patterns)
    if policy.carbon.allowed_regions:
        matched = any(fnmatch.fnmatch(region, pattern) for pattern in policy.carbon.allowed_regions)
        if not matched:
            violations.append(
                Violation(
                    severity=Severity.BLOCK,
                    policy_name="carbon.allowed_regions",
                    message=(
                        f"Region {region} is not in allowed regions: "
                        f"{', '.join(policy.carbon.allowed_regions)}"
                    ),
                    resource_id=resource_id,
                    resource_name=resource_name,
                )
            )

    # Check minimum tier
    min_rank = _TIER_RANK.get(policy.carbon.min_region_tier, 1)
    actual_rank = _TIER_RANK.get(region_tier, 0)
    if actual_rank < min_rank:
        violations.append(
            Violation(
                severity=Severity.BLOCK,
                policy_name="carbon.min_region_tier",
                message=(
                    f"Region {region} is {region_tier.upper()} tier, "
                    f"policy requires {policy.carbon.min_region_tier.upper()}+"
                ),
                resource_id=resource_id,
                resource_name=resource_name,
            )
        )

    return violations


def evaluate_tags(
    workload: Workload,
    policy: Policy,
) -> list[Violation]:
    """Check resource tagging against requirements."""
    violations: list[Violation] = []

    if not policy.tagging.required_tags:
        return violations

    missing = [tag for tag in policy.tagging.required_tags if tag not in workload.tags]
    if missing:
        violations.append(
            Violation(
                severity=policy.tagging.severity,
                policy_name="tagging.required_tags",
                message=f"Missing required tags: {', '.join(missing)}",
                resource_id=workload.id,
                resource_name=workload.name,
            )
        )

    return violations


def evaluate_all(
    workloads: list[Workload],
    ecoweights: list[EcoWeight],
    policy: Policy,
    region_tiers: dict[str, str] | None = None,
) -> PolicyResult:
    """Evaluate all workloads against all policy rules."""
    violations: list[Violation] = []
    tiers = region_tiers or {}

    for ew in ecoweights:
        violations.extend(evaluate_ecoweight(ew, policy))
        violations.extend(evaluate_budget(ew.cost, policy, ew.workload_id, ew.workload_name))
        violations.extend(evaluate_carbon(ew.carbon, policy, ew.workload_id, ew.workload_name))

        tier = tiers.get(ew.carbon.region, "bronze")
        violations.extend(
            evaluate_region(ew.carbon.region, tier, policy, ew.workload_id, ew.workload_name)
        )

    for workload in workloads:
        violations.extend(evaluate_tags(workload, policy))

    return PolicyResult(violations=violations, resource_count=len(workloads))
