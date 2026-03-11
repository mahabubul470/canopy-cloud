"""CARL scheduler — Carbon-Aware Resource Launcher.

Deterministic decision function that decides whether to run, throttle, or defer
a workload based on current carbon intensity and urgency.
"""

from canopy.models.carl import CarlDecision, CarlStrategy, Urgency


def carl_decide(
    workload_id: str,
    current_intensity: float,
    forecast: list[tuple[str, float]],
    urgency: Urgency = Urgency.NORMAL,
) -> CarlDecision:
    """Make a CARL scheduling decision.

    Args:
        workload_id: Identifier for the workload.
        current_intensity: Current grid carbon intensity (gCO2/kWh).
        forecast: List of (window_label, intensity) tuples for upcoming windows.
            E.g. [("next-2h", 80), ("next-4h", 60), ("next-6h", 120)].
        urgency: How urgent the workload is.

    Returns:
        CarlDecision with strategy, reason, and parameters.

    Rules (deterministic):
        1. critical urgency → always pass_through
        2. intensity ≤ 100 → pass_through (grid is clean)
        3. intensity > 100, flexible urgency, clean window (≤100) within 6h → defer
        4. intensity > 300, normal urgency → throttle at 0.5x
        5. default → pass_through
    """
    # Rule 1: critical always runs immediately
    if urgency == Urgency.CRITICAL:
        return CarlDecision(
            strategy=CarlStrategy.PASS_THROUGH,
            reason="Critical urgency — running immediately",
            current_intensity=current_intensity,
        )

    # Rule 2: grid is clean
    if current_intensity <= 100:
        return CarlDecision(
            strategy=CarlStrategy.PASS_THROUGH,
            reason=f"Grid intensity {current_intensity:.0f} gCO2/kWh is clean (≤100)",
            current_intensity=current_intensity,
        )

    # Rule 3: flexible workload can be deferred to a cleaner window
    if urgency == Urgency.FLEXIBLE and forecast:
        clean_window = _find_clean_window(forecast)
        if clean_window is not None:
            label, intensity = clean_window
            return CarlDecision(
                strategy=CarlStrategy.DEFER,
                reason=(
                    f"Grid dirty ({current_intensity:.0f} gCO2/kWh), "
                    f"deferring to {label} ({intensity:.0f} gCO2/kWh)"
                ),
                current_intensity=current_intensity,
                recommended_window=label,
                defer_until=label,
            )

    # Rule 4: high intensity, normal urgency → throttle
    if current_intensity > 300 and urgency == Urgency.NORMAL:
        return CarlDecision(
            strategy=CarlStrategy.THROTTLE,
            reason=(
                f"Grid intensity {current_intensity:.0f} gCO2/kWh is high (>300), "
                "throttling to 0.5x"
            ),
            current_intensity=current_intensity,
            throttle_factor=0.5,
        )

    # Rule 5: default — pass through
    return CarlDecision(
        strategy=CarlStrategy.PASS_THROUGH,
        reason=f"Grid intensity {current_intensity:.0f} gCO2/kWh — proceeding normally",
        current_intensity=current_intensity,
    )


def _find_clean_window(
    forecast: list[tuple[str, float]],
    threshold: float = 100,
) -> tuple[str, float] | None:
    """Find the first forecast window with intensity at or below threshold."""
    for label, intensity in forecast:
        if intensity <= threshold:
            return (label, intensity)
    return None
