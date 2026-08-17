from datetime import date

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.models import OHLCV, Symbol, TechnicalSnapshot
from data_worker.services.technicals import calculate_technical_snapshot


class Command(BaseCommand):
    help = "Compute current D/W/M technical snapshots for Tradeable instruments."

    def add_arguments(self, parser):
        parser.add_argument("--market", choices=["US", "IND"])
        parser.add_argument("--symbol")
        parser.add_argument("--timeframe", choices=["D", "W", "M"])
        parser.add_argument("--as-of", type=date.fromisoformat)
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        queryset = Symbol.objects.filter(
            is_active=True,
            universe_memberships__universe__is_ohlcv_enabled=True,
            universe_memberships__effective_to__isnull=True,
        ).distinct().order_by("market", "symbol")
        if options["market"]:
            queryset = queryset.filter(market=options["market"])
        if options["symbol"]:
            queryset = queryset.filter(symbol=options["symbol"].upper())
        if options["limit"]:
            if options["limit"] < 1:
                raise CommandError("--limit must be positive")
            queryset = queryset[: options["limit"]]

        symbols = list(queryset)
        if not symbols:
            raise CommandError("No eligible Tradeable instruments matched the filters.")
        timeframes = [options["timeframe"]] if options["timeframe"] else ["D", "W", "M"]
        snapshots = []
        failures = []
        calculated_at = timezone.now()

        for position, symbol in enumerate(symbols, start=1):
            for timeframe in timeframes:
                bars = OHLCV.objects.filter(symbol=symbol, timeframe=timeframe)
                if options["as_of"]:
                    bars = bars.filter(date__lte=options["as_of"])
                rows = list(
                    bars.order_by("-date").values(
                        "date", "open", "high", "low", "close", "volume"
                    )[:600]
                )
                if not rows:
                    failures.append(f"{symbol.market}:{symbol.symbol}:{timeframe} has no OHLCV")
                    continue
                try:
                    values = calculate_technical_snapshot(pd.DataFrame.from_records(reversed(rows)))
                    snapshots.append(
                        TechnicalSnapshot(
                            symbol=symbol,
                            timeframe=timeframe,
                            updated_at=calculated_at,
                            **values,
                        )
                    )
                except Exception as exc:
                    failures.append(f"{symbol.market}:{symbol.symbol}:{timeframe}: {exc}")
            if position % 100 == 0 or position == len(symbols):
                self.stdout.write(f"Processed {position}/{len(symbols)} instruments")

        update_fields = [
            field.name
            for field in TechnicalSnapshot._meta.fields
            if field.name not in {"id", "symbol", "timeframe"}
        ]
        TechnicalSnapshot.objects.bulk_create(
            snapshots,
            batch_size=1000,
            update_conflicts=True,
            update_fields=update_fields,
            unique_fields=["symbol", "timeframe"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Stored {len(snapshots)} snapshots; {len(failures)} failures."
            )
        )
        for failure in failures[:50]:
            self.stderr.write(failure)
        if len(failures) > 50:
            self.stderr.write(f"...and {len(failures) - 50} more failures")
