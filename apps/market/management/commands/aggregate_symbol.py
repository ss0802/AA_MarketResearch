import pandas as pd
from django.core.management.base import BaseCommand

from apps.market.models import OHLCV, Symbol
from data_worker.services.aggregator import aggregate_ohlcv
from data_worker.services.ingestion import ingest_ohlcv
from data_worker.services.validator import validate_ohlcv


class Command(BaseCommand):
    help = "Aggregate stored daily OHLCV into weekly and monthly candles."

    def add_arguments(self, parser):
        parser.add_argument(
            "symbol",
            type=str,
        )

    def handle(self, *args, **options):
        symbol_code = options["symbol"].upper()

        try:
            symbol = Symbol.objects.get(
                symbol=symbol_code
            )
        except Symbol.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    f"Symbol {symbol_code} not found."
                )
            )
            return

        daily_rows = (
            OHLCV.objects.filter(
                symbol=symbol,
                timeframe="D",
            )
            .order_by("date")
            .values(
                "date",
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume",
            )
        )

        if not daily_rows.exists():
            self.stderr.write(
                self.style.ERROR(
                    f"No daily OHLCV found for {symbol_code}."
                )
            )
            return

        df = pd.DataFrame.from_records(
            daily_rows
        )

        df["symbol"] = symbol_code
        df["timeframe"] = "D"

        df = df[
            [
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
        ]

        self.stdout.write(
            f"{symbol_code} daily candles: {len(df)}"
        )

        # --------------------------------------------------
        # Weekly
        # --------------------------------------------------

        weekly_df = aggregate_ohlcv(
            df,
            timeframe="W",
        )

        validate_ohlcv(weekly_df)

        weekly_stats = ingest_ohlcv(
            weekly_df
        )

        # --------------------------------------------------
        # Monthly
        # --------------------------------------------------

        monthly_df = aggregate_ohlcv(
            df,
            timeframe="M",
        )

        validate_ohlcv(monthly_df)

        monthly_stats = ingest_ohlcv(
            monthly_df
        )

        # --------------------------------------------------
        # Report
        # --------------------------------------------------

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"{symbol_code} aggregation complete."
            )
        )

        self.stdout.write("")
        self.stdout.write("Weekly")
        self.stdout.write(
            f"Total:     {weekly_stats['total']}"
        )
        self.stdout.write(
            f"Created:   {weekly_stats['created']}"
        )
        self.stdout.write(
            f"Updated:   {weekly_stats['updated']}"
        )
        self.stdout.write(
            f"Unchanged: {weekly_stats['unchanged']}"
        )

        self.stdout.write("")
        self.stdout.write("Monthly")
        self.stdout.write(
            f"Total:     {monthly_stats['total']}"
        )
        self.stdout.write(
            f"Created:   {monthly_stats['created']}"
        )
        self.stdout.write(
            f"Updated:   {monthly_stats['updated']}"
        )
        self.stdout.write(
            f"Unchanged: {monthly_stats['unchanged']}"
        )