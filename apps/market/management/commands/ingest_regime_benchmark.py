from django.core.management.base import BaseCommand

from apps.market.models import OHLCV, Symbol
from data_worker.providers.yahoo import YahooFinanceProvider
from data_worker.services.ingestion import ingest_ohlcv
from data_worker.services.normalizer import normalize_ohlcv
from data_worker.services.validator import validate_ohlcv


BENCHMARKS = {
    Symbol.Market.INDIA: {"symbol": "^NSEI", "name": "Nifty 50", "currency": "INR"},
    Symbol.Market.US: {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "currency": "USD"},
}


class Command(BaseCommand):
    help = "Ensure and refresh the benchmark used by the market-regime engine."

    def add_arguments(self, parser):
        parser.add_argument("--market", required=True, choices=Symbol.Market.values)

    def handle(self, *args, **options):
        market = options["market"]
        definition = BENCHMARKS[market]
        benchmark, _ = Symbol.objects.get_or_create(
            market=market, exchange="INDEX" if market == Symbol.Market.INDIA else "NYSEARCA",
            symbol=definition["symbol"],
            defaults={
                "name": definition["name"], "currency": definition["currency"],
                "country": "India" if market == Symbol.Market.INDIA else "United States",
            },
        )
        count = benchmark.ohlcv.filter(timeframe=OHLCV.Timeframe.DAILY).count()
        if market == Symbol.Market.US and count >= 200:
            self.stdout.write(f"US benchmark {benchmark.symbol} already has {count} daily bars; tradeable EOD ingestion refreshes it.")
            return
        period = "10y" if count < 200 else "1mo"
        raw = YahooFinanceProvider().get_daily_ohlcv(definition["symbol"], period=period)
        normalized = normalize_ohlcv(raw, symbol=benchmark.symbol, timeframe=OHLCV.Timeframe.DAILY)
        validated = validate_ohlcv(normalized)
        stats = ingest_ohlcv(validated, symbol_instance=benchmark)
        self.stdout.write(self.style.SUCCESS(
            f"{market} benchmark {benchmark.symbol}: {stats['created']} created, "
            f"{stats['updated']} updated, {stats['unchanged']} unchanged"
        ))
