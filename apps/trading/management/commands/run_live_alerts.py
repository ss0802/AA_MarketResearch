import asyncio
import json
import os

import websockets
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from apps.trading.models import PriceAlert
from apps.trading.services_alerts import process_quote


class Command(BaseCommand):
    help = "Run the laptop US price-alert worker using Tiingo reference prices."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true", help="Connect to Tiingo; omitted means configuration check only.")
        parser.add_argument("--simulate-symbol")
        parser.add_argument("--simulate-prices", help="Comma-separated prices for safe testing.")

    def handle(self, *args, **options):
        if options["simulate_symbol"] and options["simulate_prices"]:
            for price in options["simulate_prices"].split(","):
                events = process_quote(options["simulate_symbol"], price.strip())
                self.stdout.write(f"{options['simulate_symbol']} {price.strip()}: {len(events)} trigger(s)")
            return
        symbols = list(PriceAlert.objects.filter(is_active=True, symbol__market="US").values_list("symbol__symbol", flat=True).distinct())
        self.stdout.write(f"Active US alert symbols: {', '.join(symbols) or 'none'}")
        if not options["live"]:
            self.stdout.write("Configuration check only. Add --live to connect.")
            return
        if not symbols:
            raise CommandError("No active US price alerts exist.")
        if not os.getenv("TIINGO_API_KEY"):
            raise CommandError("TIINGO_API_KEY is not configured.")
        asyncio.run(self._stream(symbols))

    async def _stream(self, symbols):
        token = os.getenv("TIINGO_API_KEY")
        while True:
            try:
                async with websockets.connect("wss://api.tiingo.com/iex", ping_interval=20) as socket:
                    await socket.send(json.dumps({"eventName":"subscribe","authorization":token,"eventData":{"thresholdLevel":6,"tickers":symbols}}))
                    self.stdout.write(self.style.SUCCESS("Connected to Tiingo live reference prices."))
                    async for raw in socket:
                        message = json.loads(raw)
                        if message.get("messageType") != "A":
                            continue
                        data = message.get("data") or []
                        if len(data) >= 3:
                            process_quote(str(data[1]), data[2], parse_datetime(data[0]))
            except KeyboardInterrupt:
                return
            except Exception as exc:
                self.stderr.write(f"Connection lost: {exc}; retrying in 10 seconds")
                await asyncio.sleep(10)
