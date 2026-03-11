"""Tests for CARL scheduler."""

from canopy.engine.carl.scheduler import carl_decide
from canopy.models.carl import CarlDecision, CarlStrategy, Urgency


class TestCarlDecide:
    """Test the deterministic CARL scheduling rules."""

    def test_critical_always_passes_through(self) -> None:
        """Rule 1: critical urgency → pass_through regardless of intensity."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=500,
            forecast=[("next-2h", 50)],
            urgency=Urgency.CRITICAL,
        )
        assert decision.strategy == CarlStrategy.PASS_THROUGH
        assert "Critical" in decision.reason

    def test_clean_grid_passes_through(self) -> None:
        """Rule 2: intensity ≤ 100 → pass_through."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=80,
            forecast=[],
            urgency=Urgency.NORMAL,
        )
        assert decision.strategy == CarlStrategy.PASS_THROUGH
        assert "clean" in decision.reason

    def test_intensity_exactly_100_passes_through(self) -> None:
        """Rule 2 boundary: intensity = 100 is still clean."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=100,
            forecast=[],
            urgency=Urgency.NORMAL,
        )
        assert decision.strategy == CarlStrategy.PASS_THROUGH

    def test_flexible_with_clean_window_defers(self) -> None:
        """Rule 3: flexible + dirty grid + clean window → defer."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=200,
            forecast=[("next-2h", 180), ("next-4h", 90), ("next-6h", 120)],
            urgency=Urgency.FLEXIBLE,
        )
        assert decision.strategy == CarlStrategy.DEFER
        assert decision.recommended_window == "next-4h"
        assert decision.defer_until == "next-4h"

    def test_flexible_no_clean_window_passes(self) -> None:
        """Rule 3 fallback: flexible but no clean window within forecast → default."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=200,
            forecast=[("next-2h", 180), ("next-4h", 150), ("next-6h", 200)],
            urgency=Urgency.FLEXIBLE,
        )
        # Falls to default (rule 5) since no clean window and intensity not > 300
        assert decision.strategy == CarlStrategy.PASS_THROUGH

    def test_flexible_empty_forecast_passes(self) -> None:
        """Flexible with no forecast data → pass through (default)."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=200,
            forecast=[],
            urgency=Urgency.FLEXIBLE,
        )
        assert decision.strategy == CarlStrategy.PASS_THROUGH

    def test_high_intensity_normal_throttles(self) -> None:
        """Rule 4: intensity > 300, normal urgency → throttle at 0.5x."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=400,
            forecast=[],
            urgency=Urgency.NORMAL,
        )
        assert decision.strategy == CarlStrategy.THROTTLE
        assert decision.throttle_factor == 0.5
        assert "high" in decision.reason

    def test_intensity_301_normal_throttles(self) -> None:
        """Rule 4 boundary: intensity = 301 triggers throttle."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=301,
            forecast=[],
            urgency=Urgency.NORMAL,
        )
        assert decision.strategy == CarlStrategy.THROTTLE

    def test_intensity_300_normal_passes(self) -> None:
        """Rule 4 boundary: intensity = 300 does NOT throttle (must be > 300)."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=300,
            forecast=[],
            urgency=Urgency.NORMAL,
        )
        assert decision.strategy == CarlStrategy.PASS_THROUGH

    def test_moderate_intensity_normal_passes(self) -> None:
        """Rule 5 default: moderate intensity, normal urgency → pass."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=150,
            forecast=[],
            urgency=Urgency.NORMAL,
        )
        assert decision.strategy == CarlStrategy.PASS_THROUGH

    def test_flexible_prefers_earliest_clean_window(self) -> None:
        """Defer picks the first clean window in the forecast list."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=200,
            forecast=[("next-2h", 90), ("next-4h", 50)],
            urgency=Urgency.FLEXIBLE,
        )
        assert decision.strategy == CarlStrategy.DEFER
        assert decision.recommended_window == "next-2h"

    def test_decision_has_current_intensity(self) -> None:
        """All decisions report the current intensity."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=123,
            forecast=[],
        )
        assert decision.current_intensity == 123

    def test_default_urgency_is_normal(self) -> None:
        """Default urgency parameter is normal."""
        decision = carl_decide(
            workload_id="w-1",
            current_intensity=50,
            forecast=[],
        )
        assert decision.strategy == CarlStrategy.PASS_THROUGH


class TestCarlModels:
    def test_carl_strategy_values(self) -> None:
        assert CarlStrategy.PASS_THROUGH.value == "pass_through"
        assert CarlStrategy.THROTTLE.value == "throttle"
        assert CarlStrategy.DEFER.value == "defer"

    def test_urgency_values(self) -> None:
        assert Urgency.CRITICAL.value == "critical"
        assert Urgency.NORMAL.value == "normal"
        assert Urgency.FLEXIBLE.value == "flexible"

    def test_carl_decision_model(self) -> None:
        d = CarlDecision(
            strategy=CarlStrategy.THROTTLE,
            reason="test",
            current_intensity=200,
            throttle_factor=0.5,
        )
        assert d.strategy == CarlStrategy.THROTTLE
        assert d.throttle_factor == 0.5

    def test_carl_decision_defaults(self) -> None:
        d = CarlDecision(
            strategy=CarlStrategy.PASS_THROUGH,
            reason="ok",
            current_intensity=50,
        )
        assert d.throttle_factor == 1.0
        assert d.defer_until is None
        assert d.recommended_window is None
