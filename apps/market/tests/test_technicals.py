import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from data_worker.services.technicals import calculate_technical_snapshot


class TechnicalCalculationTests(SimpleTestCase):
    def make_frame(self):
        size = 300
        close = np.linspace(100, 160, size)
        return pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=size, freq="D"),
                "open": close - 0.5,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "volume": np.arange(size) + 1000,
            }
        )

    def test_calculates_filterable_snapshot(self):
        result = calculate_technical_snapshot(self.make_frame())

        self.assertEqual(result["momentum"], "Bullish")
        self.assertEqual(result["vwap_status"], "Bearish")
        self.assertEqual(result["dmi_status"], "Bullish")
        self.assertEqual(result["rsi_status"], "Overbought")
        self.assertTrue(result["trending"])
        self.assertIsNotNone(result["sma250"])
        self.assertIsNotNone(result["bb20_upper"])
        self.assertIsNotNone(result["kc20_upper"])

    def test_vwap_matches_workbook_candle_typical_price(self):
        frame = self.make_frame()
        result = calculate_technical_snapshot(frame)
        latest = frame.iloc[-1]
        expected = (latest.high + latest.low + latest.close) / 3

        self.assertAlmostEqual(float(result["vwap"]), expected, places=6)

    def test_sma_100_and_150_are_distinct(self):
        result = calculate_technical_snapshot(self.make_frame())

        self.assertNotEqual(result["sma100"], result["sma150"])
