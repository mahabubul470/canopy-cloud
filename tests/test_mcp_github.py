"""Tests for MCP GitHub server."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("mcp")

from canopy.mcp.github import create_issue, create_optimization_issue  # noqa: E402


class TestCreateIssue:
    @patch("canopy.mcp.github.httpx.post")
    def test_success(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "number": 42,
            "html_url": "https://github.com/org/repo/issues/42",
        }
        mock_post.return_value = mock_resp

        result = create_issue("ghp_token", "org/repo", "Test", "Body text")
        assert result["success"] is True
        assert result["issue_number"] == 42
        assert result["html_url"] == "https://github.com/org/repo/issues/42"

    @patch("canopy.mcp.github.httpx.post")
    def test_with_labels(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"number": 1, "html_url": ""}
        mock_post.return_value = mock_resp

        create_issue("ghp_token", "org/repo", "Test", "Body", labels=["bug", "canopy"])
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["labels"] == ["bug", "canopy"]

    @patch("canopy.mcp.github.httpx.post")
    def test_failure(self, mock_post: MagicMock) -> None:
        import httpx

        mock_post.side_effect = httpx.HTTPError("Unauthorized")
        result = create_issue("bad", "org/repo", "Test", "Body")
        assert result["success"] is False


class TestCreateOptimizationIssue:
    @patch("canopy.mcp.github.httpx.post")
    def test_creates_formatted_issue(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "number": 7,
            "html_url": "https://github.com/org/repo/issues/7",
        }
        mock_post.return_value = mock_resp

        result = create_optimization_issue(
            github_token="ghp_token",
            github_repo="org/repo",
            workload_id="i-123",
            workload_name="web-server",
            recommendation_type="idle",
            reason="CPU < 2% for 7 days",
            cost_savings_usd=150.0,
            carbon_savings_kg=25.0,
        )
        assert result["success"] is True

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "idle" in payload["title"]
        assert "web-server" in payload["body"]
        assert "$150.00" in payload["body"]
        assert payload["labels"] == ["canopy", "optimization"]
