import time
from datetime import time as clock_time
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.models import Symbol
from apps.market.services_quotes import fetch_yahoo_intraday_quotes
from apps.trading.models import AlertWorkerState, PriceAlert
from apps.trading.services_alerts import process_quote


WORKER_NAME = "yahoo_us_delayed"


def us_market_is_open(moment=None):
    eastern = (moment or timezone.now()).astimezone(ZoneInfo("America/New_York"))
    return eastern.weekday() < 5 and clock_time(9, 30) <= eastern.time().replace(tzinfo=None) <= clock_time(16, 15)


class Command(BaseCommand):
    help = "Poll delayed Yahoo intraday quotes for active US price alerts."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true", help="Continue polling until stopped.")
        parser.add_argument("--once", action="store_true", help="Fetch one batch, including outside market hours.")
        parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds; minimum 30.")

    def handle(self, *args, **options):
        if options["interval"] < 30:
            raise CommandError("Yahoo polling interval must be at least 30 seconds.")
        symbols = self._active_symbols()
        self.stdout.write(f"Active US alert symbols: {', '.join(item.symbol for item in symbols) or 'none'}")
        if not options["live"] and not options["once"]:
            self.stdout.write("Configuration check only. Add --live to poll, or --once for one batch.")
            return
        if not symbols:
            raise CommandError("No active US price alerts exist.")
        try:
            if options["once"]:
                self._poll(symbols)
                return
            AlertWorkerState.objects.update_or_create(
                name=WORKER_NAME,
                defaults={"status": "CONNECTED_DELAYED", "connected_at": timezone.now(), "last_error": ""},
            )
            self.stdout.write(self.style.WARNING(f"Yahoo delayed worker started; polling every {options['interval']} seconds."))
            while True:
                if us_market_is_open():
                    symbols = self._active_symbols()
                    if symbols:
                        self._poll(symbols)
                else:
                    AlertWorkerState.objects.update_or_create(
                        name=WORKER_NAME,
                        defaults={"status": "WAITING_MARKET", "last_heartbeat_at": timezone.now()},
                    )
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Yahoo delayed worker stopped.")
        finally:
            if options["live"]:
                AlertWorkerState.objects.update_or_create(name=WORKER_NAME, defaults={"status": "STOPPED"})

    @staticmethod
    def _active_symbols():
        return list(Symbol.objects.filter(
            market=Symbol.Market.US,
            price_alerts__is_active=True,
            price_alerts__status=PriceAlert.Status.ACTIVE,
        ).distinct().order_by("symbol"))

    def _poll(self, symbols):
        try:
            quotes = fetch_yahoo_intraday_quotes(symbols)
            for symbol in symbols:
                quote = quotes.get(symbol.id)
                if quote is None:
                    self.stderr.write(f"No delayed Yahoo quote for {symbol.symbol}")
                    continue
                events = process_quote(symbol.symbol, quote["price"], quote["quote_time"], Symbol.Market.US)
                self.stdout.write(
                    f"{symbol.symbol} {quote['price']} @ {quote['quote_time'].isoformat()}"
                    + (f" · {len(events)} trigger(s)" if events else "")
                )
            latest = max((quote["quote_time"] for quote in quotes.values()), default=None)
            AlertWorkerState.objects.update_or_create(
                name=WORKER_NAME,
                defaults={
                    "status": "CONNECTED_DELAYED", "last_heartbeat_at": timezone.now(),
                    "last_quote_at": latest, "last_error": "",
                },
            )
        except Exception as error:
            AlertWorkerState.objects.update_or_create(
                name=WORKER_NAME,
                defaults={"status": "ERROR", "last_heartbeat_at": timezone.now(), "last_error": str(error)[:1000]},
            )
            self.stderr.write(f"Yahoo delayed quote batch failed: {error}")
