import time
from datetime import timedelta

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.models import OHLCV, OHLCVIngestionState, Symbol
from data_worker.providers.yahoo import YahooFinanceProvider
from data_worker.providers.tiingo import TiingoEODProvider
from data_worker.services.aggregator import aggregate_ohlcv
from data_worker.services.ingestion import ingest_ohlcv
from data_worker.services.normalizer import normalize_ohlcv
from data_worker.services.validator import validate_ohlcv


def yahoo_symbol(symbol):
    ticker = symbol.symbol
    if symbol.market == Symbol.Market.INDIA:
        ticker = ticker.removesuffix(".RR").replace("_", "-")
        return f"{ticker}.NS"
    return ticker.replace(".", "-").replace("/", "-")


class Command(BaseCommand):
    help = "Backfill or update OHLCV for current Tradeable-universe instruments."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=["backfill", "eod"], default="eod")
        parser.add_argument("--provider", choices=["yahoo", "tiingo"], default="yahoo")
        parser.add_argument("--market", choices=["US", "IND"])
        parser.add_argument("--symbol", help="Process one canonical symbol for a pilot or retry.")
        parser.add_argument("--limit", type=int, help="Maximum instruments to process.")
        parser.add_argument(
            "--failed-only",
            action="store_true",
            help="Retry only instruments whose selected-provider daily ingestion failed.",
        )
        parser.add_argument("--sleep", type=float, default=0.25, help="Seconds between provider calls.")
        parser.add_argument("--retries", type=int, default=0, help="Retries after a provider/validation failure.")
        parser.add_argument("--retry-wait", type=float, default=2.0, help="Initial retry delay in seconds.")
        parser.add_argument("--fail-fast", action="store_true")

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
        if options["failed_only"]:
            queryset = queryset.filter(
                ingestion_states__provider=options["provider"],
                ingestion_states__timeframe="D",
                ingestion_states__status=OHLCVIngestionState.Status.FAILED,
            )
        if options["limit"]:
            if options["limit"] < 1:
                raise CommandError("--limit must be positive")
            queryset = queryset[: options["limit"]]
        if options["retries"] < 0 or options["retry_wait"] < 0:
            raise CommandError("--retries and --retry-wait cannot be negative")

        instruments = list(queryset)
        if not instruments:
            raise CommandError("No eligible Tradeable instruments matched the filters.")

        mode = options["mode"]
        period = "10y" if mode == "backfill" else "1mo"
        provider_name = options["provider"]
        provider = TiingoEODProvider() if provider_name == "tiingo" else YahooFinanceProvider()
        totals = {"success": 0, "failed": 0, "created": 0, "updated": 0}
        self.stdout.write(
            f"{mode.upper()}: {len(instruments)} Tradeable instruments "
            f"using {provider_name.upper()}"
        )

        for position, instrument in enumerate(instruments, start=1):
            provider_code = (
                instrument.symbol.replace(".", "-").replace("/", "-")
                if provider_name == "tiingo"
                else yahoo_symbol(instrument)
            )
            state, _ = OHLCVIngestionState.objects.get_or_create(
                symbol=instrument,
                provider=provider_name,
                timeframe="D",
            )
            state.status = OHLCVIngestionState.Status.RUNNING
            state.last_attempt_at = timezone.now()
            state.last_error = ""
            state.save(update_fields=["status", "last_attempt_at", "last_error"])
            try:
                daily = self._fetch_daily(
                    provider=provider,
                    provider_name=provider_name,
                    provider_code=provider_code,
                    instrument=instrument,
                    mode=mode,
                    period=period,
                    retries=options["retries"],
                    retry_wait=options["retry_wait"],
                )
                daily_stats = ingest_ohlcv(daily, symbol_instance=instrument)
                aggregate_stats = self._aggregate(instrument, mode)
                state.status = OHLCVIngestionState.Status.SUCCESS
                state.last_success_at = timezone.now()
                state.last_bar_date = daily["date"].max()
                state.failure_count = 0
                state.save(
                    update_fields=["status", "last_success_at", "last_bar_date", "failure_count"]
                )
                totals["success"] += 1
                totals["created"] += daily_stats["created"] + aggregate_stats["created"]
                totals["updated"] += daily_stats["updated"] + aggregate_stats["updated"]
                self.stdout.write(
                    f"[{position}/{len(instruments)}] {instrument.market}:{instrument.symbol} "
                    f"D={daily_stats['total']} created={daily_stats['created']} updated={daily_stats['updated']}"
                )
            except Exception as exc:
                state.status = OHLCVIngestionState.Status.FAILED
                state.failure_count += 1
                state.last_error = str(exc)[:4000]
                state.save(update_fields=["status", "failure_count", "last_error"])
                totals["failed"] += 1
                self.stderr.write(f"[{position}/{len(instruments)}] {provider_code}: {exc}")
                if options["fail_fast"]:
                    raise
            if options["sleep"]:
                time.sleep(options["sleep"])

        self.stdout.write(self.style.SUCCESS(f"Completed: {totals}"))

    def _fetch_daily(self, provider, provider_name, provider_code, instrument, mode, period, retries, retry_wait):
        for attempt in range(retries + 1):
            try:
                if provider_name == "tiingo":
                    end_date = timezone.localdate()
                    start_date = end_date - timedelta(days=3653 if mode == "backfill" else 35)
                    raw = provider.get_daily_ohlcv(provider_code, start_date=start_date, end_date=end_date)
                else:
                    raw = provider.get_daily_ohlcv(provider_code, period=period)
                daily = normalize_ohlcv(raw, symbol=instrument.symbol, timeframe="D")
                validate_ohlcv(daily)
                return daily
            except Exception as exc:
                if attempt >= retries:
                    raise
                delay = retry_wait * (2 ** attempt)
                self.stderr.write(
                    f"{provider_code}: attempt {attempt + 1} failed ({exc}); retrying in {delay:g}s"
                )
                if delay:
                    time.sleep(delay)

    def _aggregate(self, instrument, mode):
        rows = OHLCV.objects.filter(symbol=instrument, timeframe="D")
        if mode == "eod":
            rows = rows.filter(date__gte=timezone.localdate() - timedelta(days=62))
        rows = rows.order_by("date").values(
            "date", "open", "high", "low", "close", "adj_close", "volume"
        )
        frame = pd.DataFrame.from_records(rows)
        if frame.empty:
            return {"created": 0, "updated": 0}
        frame["symbol"] = instrument.symbol
        frame["timeframe"] = "D"
        totals = {"created": 0, "updated": 0}
        for timeframe in ("W", "M"):
            aggregated = aggregate_ohlcv(frame, timeframe=timeframe)
            stats = ingest_ohlcv(aggregated, symbol_instance=instrument)
            totals["created"] += stats["created"]
            totals["updated"] += stats["updated"]
        return totals
