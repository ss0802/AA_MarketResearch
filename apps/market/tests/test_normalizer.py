from django.test import SimpleTestCase

from data_worker.providers.yahoo import YahooFinanceProvider
from data_worker.services.normalizer import normalize_ohlcv


class OHLCVNormalizerTests(SimpleTestCase):

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