import asyncio
import json
import os

import websockets
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.trading.models import AlertWorkerState, PriceAlert
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
        symbols = list(PriceAlert.objects.filter(is_active=True, status=PriceAlert.Status.ACTIVE, symbol__market="US").values_list("symbol__symbol", flat=True).distinct())
        self.stdout.write(f"Active US alert symbols: {', '.join(symbols) or 'none'}")
        if not options["live"]:
            self.stdout.write("Configuration check only. Add --live to connect.")
            return
        if not symbols:
            raise CommandError("No active US price alerts exist.")
        if not os.getenv("TIINGO_API_KEY"):
            raise CommandError("TIINGO_API_KEY is not configured.")
        try:
            asyncio.run(self._stream(symbols))
        finally:
            AlertWorkerState.objects.update_or_create(
                name="tiingo_us", defaults={"status": "STOPPED"}
            )

    async def _stream(self, symbols):
        token = os.getenv("TIINGO_API_KEY")
        while True:
            try:
                async with websockets.connect("wss://api.tiingo.com/iex", ping_interval=20) as socket:
                    await socket.send(json.dumps({
                        "eventName": "subscribe",
                        "authorization": token,
                        "eventData": {
                            "authToken": token,
                            "thresholdLevel": 6,
                            "tickers": [symbol.lower() for symbol in symbols],
                        },
                    }))
                    self.stdout.write(self.style.SUCCESS("Connected to Tiingo live reference prices."))
                    await self._state(status="CONNECTED", connected_at=timezone.now(), last_error="")
                    async for raw in socket:
                        message = json.loads(raw)
                        if message.get("messageType") == "E":
                            await self._state(status="ERROR", last_error=str(message)[:1000])
                            self.stderr.write(f"Tiingo rejected the subscription: {message}")
                            return
                        if message.get("messageType") != "A":
                            if message.get("messageType") == "H":
                                await self._state(last_heartbeat_at=timezone.now())
                            self.stdout.write(f"Tiingo message: {message}")
                            continue
                        data = message.get("data") or []
                        if len(data) >= 3:
                            await sync_to_async(process_quote, thread_sensitive=True)(
                                str(data[1]), data[2], parse_datetime(data[0])
                            )
                            await self._state(last_quote_at=timezone.now())
                    self.stderr.write(
                        f"Tiingo closed the connection: code={socket.close_code} "
                        f"reason={socket.close_reason or 'not supplied'}"
                    )
            except KeyboardInterrupt:
                return
            except Exception as exc:
                await self._state(status="RECONNECTING", last_error=str(exc)[:1000])
                self.stderr.write(f"Connection lost: {exc}; retrying in 10 seconds")
                await asyncio.sleep(10)

    @staticmethod
    async def _state(**values):
        await sync_to_async(AlertWorkerState.objects.update_or_create, thread_sensitive=True)(
            name="tiingo_us", defaults=values
        )
