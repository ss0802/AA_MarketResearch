from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from data_worker.providers.tiingo import TiingoEODProvider


class TiingoEODProviderTests(SimpleTestCase):
    @patch("data_worker.providers.tiingo.requests.get")
    def test_returns_yahoo_compatible_ohlcv_frame(self, get):
        response = Mock()
        response.json.return_value = [
            {
                "date": "2026-08-17T00:00:00.000Z",
                "open": 152.64,
                "high": 160.99,
                "low": 147.3492,
                "close": 154.89,
                "volume": 12904145,
                "adjClose": 154.89,
            }
        ]
        get.return_value = response

        frame = TiingoEODProvider(api_key="test-token").get_daily_ohlcv(
            "AAOI", start_date="2026-08-17", end_date="2026-08-17"
        )

        self.assertEqual(
            list(frame.columns),
            ["Open", "High", "Low", "Close", "Volume", "Adj Close"],
        )
        self.assertEqual(frame.iloc[0]["Close"], 154.89)
        response.raise_for_status.assert_called_once()
        self.assertNotIn("test-token", get.call_args.args[0])

    @patch("data_worker.providers.tiingo.requests.get")
    def test_rejects_empty_response(self, get):
        response = Mock()
        response.json.return_value = []
        get.return_value = response

        with self.assertRaisesRegex(ValueError, "No daily market data"):
            TiingoEODProvider(api_key="test-token").get_daily_ohlcv("AAOI")
