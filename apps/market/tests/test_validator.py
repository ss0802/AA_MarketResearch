from django.test import SimpleTestCase
import pandas as pd

from data_worker.providers.yahoo import YahooFinanceProvider
from data_worker.services.normalizer import normalize_ohlcv
from data_worker.services.validator import validate_ohlcv


class OHLCVValidatorTests(SimpleTestCase):

    def test_valid_aaoi_daily_data(self):
        provider = YahooFinanceProvider()

        raw_df = provider.get_daily_ohlcv(
            "AAOI",
            period="1mo",
        )

        normalized_df = normalize_ohlcv(
            raw_df,
            symbol="AAOI",
            timeframe="D",
        )

        validated_df = validate_ohlcv(
            normalized_df
        )

        self.assertFalse(validated_df.empty)

        self.assertEqual(
            len(validated_df),
            len(normalized_df),
        )

    def test_invalid_high_rejected(self):
        df = make_valid_df()
        df.loc[0, "high"] = 90.0

        with self.assertRaises(ValueError):
            validate_ohlcv(df)


    def test_negative_volume_rejected(self):
        df = make_valid_df()
        df.loc[0, "volume"] = -1

        with self.assertRaises(ValueError):
            validate_ohlcv(df)


    def test_duplicate_candle_rejected(self):
        df = make_valid_df()
        df = pd.concat([df, df], ignore_index=True)

        with self.assertRaises(ValueError):
            validate_ohlcv(df)


    def test_invalid_timeframe_rejected(self):
        df = make_valid_df()
        df.loc[0, "timeframe"] = "X"

        with self.assertRaises(ValueError):
            validate_ohlcv(df)






def make_valid_df():
    return pd.DataFrame(
        {
            "symbol": ["AAOI"],
            "timeframe": ["D"],
            "date": [pd.Timestamp("2026-08-14").date()],
            "open": [100.0],
            "high": [110.0],
            "low": [95.0],
            "close": [105.0],
            "adj_close": [105.0],
            "volume": [1_000_000],
        }
    )