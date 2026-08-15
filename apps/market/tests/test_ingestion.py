from decimal import Decimal

import pandas as pd
from django.test import TestCase

from apps.market.models import OHLCV, Symbol
from data_worker.services.ingestion import ingest_ohlcv


class OHLCVIngestionTests(TestCase):

    def make_df(self):
        return pd.DataFrame(
            {
                "symbol": ["AAOI"],
                "timeframe": ["D"],
                "date": [
                    pd.Timestamp(
                        "2026-08-14"
                    ).date()
                ],
                "open": [100.0],
                "high": [110.0],
                "low": [95.0],
                "close": [105.0],
                "adj_close": [105.0],
                "volume": [1_000_000],
            }
        )

    def test_create_ohlcv(self):
        df = self.make_df()

        stats = ingest_ohlcv(df)

        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["updated"], 0)
        self.assertEqual(stats["unchanged"], 0)

        self.assertEqual(
            Symbol.objects.count(),
            1,
        )

        self.assertEqual(
            OHLCV.objects.count(),
            1,
        )

    def test_second_ingestion_is_unchanged(self):
        df = self.make_df()

        ingest_ohlcv(df)
        stats = ingest_ohlcv(df)

        self.assertEqual(stats["created"], 0)
        self.assertEqual(stats["updated"], 0)
        self.assertEqual(stats["unchanged"], 1)

        self.assertEqual(
            OHLCV.objects.count(),
            1,
        )

    def test_existing_candle_is_updated(self):
        df = self.make_df()

        ingest_ohlcv(df)

        df.loc[0, "close"] = 107.0
        df.loc[0, "adj_close"] = 107.0

        stats = ingest_ohlcv(df)

        self.assertEqual(stats["created"], 0)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["unchanged"], 0)

        candle = OHLCV.objects.get()

        self.assertEqual(
            candle.close,
            Decimal("107.0"),
        )