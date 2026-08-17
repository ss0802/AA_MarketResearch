import pandas as pd
from django.test import SimpleTestCase

from data_worker.providers.yahoo import YahooFinanceProvider
from data_worker.services.normalizer import normalize_ohlcv


class OHLCVNormalizerTests(SimpleTestCase):

    def test_repairs_high_low_envelope_without_changing_open_close(self):
        raw_df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [105.0],
                "Low": [102.0],
                "Close": [105.0],
                "Adj Close": [105.0],
                "Volume": [10],
            },
            index=pd.DatetimeIndex(["2026-01-02"], name="Date"),
        )
        result = normalize_ohlcv(raw_df, symbol="TEST")
        self.assertEqual(result.iloc[0]["open"], 100.0)
        self.assertEqual(result.iloc[0]["low"], 100.0)
        self.assertEqual(result.iloc[0]["high"], 105.0)
        self.assertEqual(result.iloc[0]["close"], 105.0)

    def test_drops_empty_provider_placeholder_session(self):
        raw_df = pd.DataFrame(
            {
                "Open": [100.0, float("nan")],
                "High": [105.0, float("nan")],
                "Low": [99.0, float("nan")],
                "Close": [104.0, float("nan")],
                "Adj Close": [104.0, float("nan")],
                "Volume": [1000, 0],
            },
            index=pd.DatetimeIndex(["2026-01-02", "2026-01-03"], name="Date"),
        )
        result = normalize_ohlcv(raw_df, symbol="TEST")
        self.assertEqual(len(result), 1)

    def test_replaces_invalid_adjusted_close_with_raw_close(self):
        raw_df = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [105.0, 106.0],
                "Low": [99.0, 100.0],
                "Close": [104.0, 105.0],
                "Adj Close": [-10.0, 0.0],
                "Volume": [1000, 1200],
            },
            index=pd.DatetimeIndex(["2026-01-02", "2026-01-03"], name="Date"),
        )
        result = normalize_ohlcv(raw_df, symbol="TEST")
        self.assertEqual(list(result["adj_close"]), [104.0, 105.0])

    def test_normalize_aaoi_daily_data(self):
        provider = YahooFinanceProvider()

        raw_df = provider.get_daily_ohlcv(
            "AAOI",
            period="1mo",
        )

        df = normalize_ohlcv(
            raw_df,
            symbol="AAOI",
            timeframe="D",
        )

        expected_columns = [
            "symbol",
            "timeframe",
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
        ]

        self.assertEqual(
            list(df.columns),
            expected_columns,
        )

        self.assertFalse(df.empty)

        self.assertTrue(
            (df["symbol"] == "AAOI").all()
        )

        self.assertTrue(
            (df["timeframe"] == "D").all()
        )

        self.assertFalse(
            df["date"].isna().any()
        )

        self.assertFalse(
            df["close"].isna().any()
        )
