"""Tests for approval mechanisms."""

from unittest.mock import MagicMock, patch

from canopy.engine.apply.approval import (
    request_github_approval,
    request_slack_approval,
)
from canopy.models.core import Recommendation, RecommendationType


def _make_recs(count: int = 2) -> list[Recommendation]:
    recs: list[Recommendation] = []
    for i in range(count):
        recs.append(
            Recommendation(
                workload_id=f"i-{i}",
                workload_name=f"workload-{i}",
                recommendation_type=(
                    RecommendationType.IDLE if i % 2 == 0 else RecommendationType.RIGHTSIZE
                ),
                reason=f"Test reason {i}",
                estimated_monthly_cost_savings_usd=50.0 * (i + 1),
                estimated_monthly_carbon_savings_kg=10.0 * (i + 1),
            )
        )
    return recs


class TestSlackApproval:
    @patch("canopy.engine.apply.approval.httpx.post")
    def test_sends_webhook(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        recs = _make_recs(2)
        result = request_slack_approval(recs, "https://hooks.slack.com/test")
        assert result is True
        mock_post.assert_called_once()

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "blocks" in payload

    @patch("canopy.engine.apply.approval.httpx.post")
    def test_sends_to_channel(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        recs = _make_recs(1)
        request_slack_approval(recs, "https://hooks.slack.com/test", channel="#ops")

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload.get("channel") == "#ops"

    @patch("canopy.engine.apply.approval.httpx.post")
    def test_returns_false_on_failure(self, mock_post: MagicMock) -> None:
        import httpx

        mock_post.side_effect = httpx.HTTPError("Connection refused")

        recs = _make_recs(1)
        result = request_slack_approval(recs, "https://hooks.slack.com/bad")
        assert result is False


class TestGitHubApproval:
    @patch("canopy.engine.apply.approval.httpx.post")
    def test_creates_issue(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"html_url": "https://github.com/org/repo/issues/42"}
        mock_post.return_value = mock_response

        recs = _make_recs(2)
        url = request_github_approval(recs, "ghp_test", "org/repo")
        assert url == "https://github.com/org/repo/issues/42"

        call_kwargs = mock_post.call_args
        assert "repos/org/repo/issues" in call_kwargs.args[0]
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "optimization" in str(payload.get("labels", []))

    @patch("canopy.engine.apply.approval.httpx.post")
    def test_returns_none_on_failure(self, mock_post: MagicMock) -> None:
        import httpx

        mock_post.side_effect = httpx.HTTPError("Unauthorized")

        recs = _make_recs(1)
        url = request_github_approval(recs, "bad_token", "org/repo")
        assert url is None

    @patch("canopy.engine.apply.approval.httpx.post")
    def test_issue_body_contains_recommendations(self, mock_post: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"html_url": "https://github.com/x/y/issues/1"}
        mock_post.return_value = mock_response

        recs = _make_recs(3)
        request_github_approval(recs, "ghp_test", "org/repo")

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        body = payload["body"]
        assert "workload-0" in body
        assert "workload-1" in body
        assert "workload-2" in body
