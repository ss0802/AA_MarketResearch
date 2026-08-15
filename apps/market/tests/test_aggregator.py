import pandas as pd
from django.test import SimpleTestCase

from data_worker.services.aggregator import aggregate_ohlcv


class OHLCVAggregatorTests(SimpleTestCase):

    def make_daily_df(self):
        return pd.DataFrame(
            {
                "symbol": ["TEST"] * 5,
                "timeframe": ["D"] * 5,
                "date": pd.to_datetime(
                    [
                        "2026-08-10",
                        "2026-08-11",
                        "2026-08-12",
                        "2026-08-13",
                        "2026-08-14",
                    ]
                ).date,
                "open": [
                    100.0,
                    102.0,
                    101.0,
                    106.0,
                    107.0,
                ],
                "high": [
                    105.0,
                    106.0,
                    107.0,
                    109.0,
                    112.0,
                ],
                "low": [
                    98.0,
                    99.0,
                    100.0,
                    104.0,
                    105.0,
                ],
                "close": [
                    102.0,
                    101.0,
                    106.0,
                    107.0,
                    110.0,
                ],
                "adj_close": [
                    102.0,
                    101.0,
                    106.0,
                    107.0,
                    110.0,
                ],
                "volume": [
                    1000,
                    2000,
                    3000,
                    4000,
                    5000,
                ],
            }
        )

    def test_weekly_aggregation(self):
        df = self.make_daily_df()

        result = aggregate_ohlcv(
            df,
            timeframe="W",
        )

        self.assertEqual(len(result), 1)

        candle = result.iloc[0]

        self.assertEqual(candle["symbol"], "TEST")
        self.assertEqual(candle["timeframe"], "W")

        self.assertEqual(candle["open"], 100.0)
        self.assertEqual(candle["high"], 112.0)
        self.assertEqual(candle["low"], 98.0)
        self.assertEqual(candle["close"], 110.0)
        self.assertEqual(candle["adj_close"], 110.0)

        self.assertEqual(
            candle["volume"],
            15000,
        )

    def test_monthly_aggregation(self):
        df = self.make_daily_df()

        result = aggregate_ohlcv(
            df,
            timeframe="M",
        )

        self.assertEqual(len(result), 1)

        candle = result.iloc[0]

        self.assertEqual(candle["timeframe"], "M")
        self.assertEqual(candle["open"], 100.0)
        self.assertEqual(candle["high"], 112.0)
        self.assertEqual(candle["low"], 98.0)
        self.assertEqual(candle["close"], 110.0)

        self.assertEqual(
            candle["volume"],
            15000,
        )

    def test_weekly_aggregation_across_two_weeks(self):
        df = pd.DataFrame(
            {
                "symbol": ["TEST"] * 4,
                "timeframe": ["D"] * 4,
                "date": pd.to_datetime(
                    [
                        "2026-08-13",  # Thursday
                        "2026-08-14",  # Friday
                        "2026-08-17",  # Monday
                        "2026-08-18",  # Tuesday
                    ]
                ).date,
                "open": [
                    100.0,
                    105.0,
                    110.0,
                    115.0,
                ],
                "high": [
                    108.0,
                    112.0,
                    118.0,
                    122.0,
                ],
                "low": [
                    98.0,
                    103.0,
                    108.0,
                    113.0,
                ],
                "close": [
                    105.0,
                    110.0,
                    115.0,
                    120.0,
                ],
                "adj_close": [
                    105.0,
                    110.0,
                    115.0,
                    120.0,
                ],
                "volume": [
                    1000,
                    2000,
                    3000,
                    4000,
                ],
            }
        )

        result = aggregate_ohlcv(
            df,
            timeframe="W",
        )

        self.assertEqual(len(result), 2)

        first_week = result.iloc[0]
        second_week = result.iloc[1]

        # Week ending Friday 14 August
        self.assertEqual(
            first_week["date"],
            pd.Timestamp("2026-08-14").date(),
        )
        self.assertEqual(first_week["open"], 100.0)
        self.assertEqual(first_week["high"], 112.0)
        self.assertEqual(first_week["low"], 98.0)
        self.assertEqual(first_week["close"], 110.0)
        self.assertEqual(first_week["volume"], 3000)

        # Following week
        self.assertEqual(
            second_week["date"],
            pd.Timestamp("2026-08-18").date(),
        )
        self.assertEqual(second_week["open"], 110.0)
        self.assertEqual(second_week["high"], 122.0)
        self.assertEqual(second_week["low"], 108.0)
        self.assertEqual(second_week["close"], 120.0)
        self.assertEqual(second_week["volume"], 7000)


    def test_monthly_aggregation_across_two_months(self):
        df = pd.DataFrame(
            {
                "symbol": ["TEST"] * 4,
                "timeframe": ["D"] * 4,
                "date": pd.to_datetime(
                    [
                        "2026-07-30",
                        "2026-07-31",
                        "2026-08-03",
                        "2026-08-04",
                    ]
                ).date,
                "open": [
                    100.0,
                    105.0,
                    110.0,
                    115.0,
                ],
                "high": [
                    108.0,
                    112.0,
                    118.0,
                    122.0,
                ],
                "low": [
                    98.0,
                    103.0,
                    108.0,
                    113.0,
                ],
                "close": [
                    105.0,
                    110.0,
                    115.0,
                    120.0,
                ],
                "adj_close": [
                    105.0,
                    110.0,
                    115.0,
                    120.0,
                ],
                "volume": [
                    1000,
                    2000,
                    3000,
                    4000,
                ],
            }
        )

        result = aggregate_ohlcv(
            df,
            timeframe="M",
        )

        self.assertEqual(len(result), 2)

        july = result.iloc[0]
        august = result.iloc[1]

        # July candle
        self.assertEqual(
            july["date"],
            pd.Timestamp("2026-07-31").date(),
        )
        self.assertEqual(july["open"], 100.0)
        self.assertEqual(july["high"], 112.0)
        self.assertEqual(july["low"], 98.0)
        self.assertEqual(july["close"], 110.0)
        self.assertEqual(july["volume"], 3000)

        # August candle
        self.assertEqual(
            august["date"],
            pd.Timestamp("2026-08-04").date(),
        )
        self.assertEqual(august["open"], 110.0)
        self.assertEqual(august["high"], 122.0)
        self.assertEqual(august["low"], 108.0)
        self.assertEqual(august["close"], 120.0)
        self.assertEqual(august["volume"], 7000)