from django.core.management.base import BaseCommand

from data_worker.providers.yahoo import YahooFinanceProvider
from data_worker.services.normalizer import normalize_ohlcv
from data_worker.services.validator import validate_ohlcv
from data_worker.services.ingestion import ingest_ohlcv


class Command(BaseCommand):
    help = "Fetch and ingest daily OHLCV data for one symbol."

    def add_arguments(self, parser):
        parser.add_argument(
            "symbol",
            type=str,
        )

        parser.add_argument(
            "--period",
            type=str,
            default="2y",
        )

    def handle(self, *args, **options):
        symbol = options["symbol"].upper()
        period = options["period"]

        self.stdout.write(
            f"Fetching {symbol} daily data..."
        )

        provider = YahooFinanceProvider()

        raw_df = provider.get_daily_ohlcv(
            symbol,
            period=period,
        )

        normalized_df = normalize_ohlcv(
            raw_df,
            symbol=symbol,
            timeframe="D",
        )

        validated_df = validate_ohlcv(
            normalized_df
        )

        stats = ingest_ohlcv(
            validated_df
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{symbol} ingestion complete."
            )
        )

        self.stdout.write(
            f"Total:     {stats['total']}"
        )

        self.stdout.write(
            f"Created:   {stats['created']}"
        )

        self.stdout.write(
            f"Updated:   {stats['updated']}"
        )

        self.stdout.write(
            f"Unchanged: {stats['unchanged']}"
        )