"""Tests for MCP Slack server."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("mcp")

from canopy.mcp.slack import send_approval_request, send_notification  # noqa: E402


class TestSendNotification:
    @patch("canopy.mcp.slack.httpx.post")
    def test_success(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = send_notification("https://hooks.slack.com/test", "Hello!")
        assert result["success"] is True
        assert result["status_code"] == 200

    @patch("canopy.mcp.slack.httpx.post")
    def test_with_channel(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        send_notification("https://hooks.slack.com/test", "msg", channel="#ops")
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["channel"] == "#ops"

    @patch("canopy.mcp.slack.httpx.post")
    def test_failure(self, mock_post: MagicMock) -> None:
        import httpx

        mock_post.side_effect = httpx.HTTPError("fail")
        result = send_notification("https://hooks.slack.com/bad", "msg")
        assert result["success"] is False


class TestSendApprovalRequest:
    @patch("canopy.mcp.slack.httpx.post")
    def test_sends_blocks(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = send_approval_request(
            webhook_url="https://hooks.slack.com/test",
            workload_id="i-123",
            workload_name="web-server",
            recommendation_type="idle",
            reason="CPU < 2%",
            cost_savings_usd=50.0,
            carbon_savings_kg=10.0,
        )
        assert result["success"] is True

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "blocks" in payload
