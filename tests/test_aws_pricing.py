"""Tests for AWS Pricing API integration."""

import json
from unittest.mock import MagicMock, patch

from canopy.engine.providers.aws import INSTANCE_PRICING, AWSProvider


class TestAWSPricing:
    def _make_pricing_response(self, price_usd: str) -> dict[str, list[str]]:
        product = {
            "terms": {
                "OnDemand": {
                    "term1": {
                        "priceDimensions": {
                            "dim1": {
                                "pricePerUnit": {"USD": price_usd},
                            }
                        }
                    }
                }
            }
        }
        return {"PriceList": [json.dumps(product)]}

    @patch("canopy.engine.providers.aws.boto3.Session")
    def test_live_price_success(self, mock_session_cls: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_pricing = MagicMock()
        mock_pricing.get_products.return_value = self._make_pricing_response("0.192")

        def client_factory(service: str, region_name: str = "") -> MagicMock:
            if service == "pricing":
                return mock_pricing
            return MagicMock()

        mock_session.client.side_effect = client_factory

        provider = AWSProvider()
        price = provider._get_cached_price("m5.xlarge", "us-east-1")
        assert price == 0.192
        mock_pricing.get_products.assert_called_once()

    @patch("canopy.engine.providers.aws.boto3.Session")
    def test_cache_hit_skips_api(self, mock_session_cls: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        provider = AWSProvider()
        provider._price_cache["us-east-1:m5.xlarge"] = 0.192

        price = provider._get_cached_price("m5.xlarge", "us-east-1")
        assert price == 0.192
        # No pricing client should have been created
        mock_session.client.assert_not_called()

    @patch("canopy.engine.providers.aws.boto3.Session")
    def test_api_failure_falls_back_to_static(self, mock_session_cls: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_pricing = MagicMock()
        mock_pricing.get_products.side_effect = Exception("API error")
        mock_session.client.return_value = mock_pricing

        provider = AWSProvider()
        price = provider._get_cached_price("m5.xlarge", "us-east-1")
        assert price == INSTANCE_PRICING["m5.xlarge"]

    @patch("canopy.engine.providers.aws.boto3.Session")
    def test_unknown_region_falls_back(self, mock_session_cls: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        provider = AWSProvider()
        price = provider._get_cached_price("m5.xlarge", "unknown-region-99")
        # Unknown region has no location mapping, so falls back to static
        assert price == INSTANCE_PRICING["m5.xlarge"]

    @patch("canopy.engine.providers.aws.boto3.Session")
    def test_unknown_instance_type_returns_zero(self, mock_session_cls: MagicMock) -> None:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        mock_pricing = MagicMock()
        mock_pricing.get_products.return_value = {"PriceList": []}
        mock_session.client.return_value = mock_pricing

        provider = AWSProvider()
        price = provider._get_cached_price("x99.mega", "us-east-1")
        assert price == 0.0
