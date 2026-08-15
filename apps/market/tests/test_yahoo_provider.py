from django.test import SimpleTestCase

from data_worker.providers.yahoo import YahooFinanceProvider


class YahooFinanceProviderTests(SimpleTestCase):

    def test_aaoi_daily_data(self):
        provider = YahooFinanceProvider()

        df = provider.get_daily_ohlcv("AAOI", period="2y")

        self.assertIsNotNone(df)
        self.assertFalse(df.empty)
        self.assertGreater(len(df), 200)

        expected_columns = {
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        }

        self.assertTrue(
            expected_columns.issubset(set(df.columns))
        )