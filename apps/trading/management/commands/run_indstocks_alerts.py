import asyncio
import json
import os
from datetime import datetime, timezone as datetime_timezone

import websockets
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.market.models import ProviderInstrument, Symbol
from apps.trading.models import AlertWorkerState, PriceAlert
from apps.trading.services_alerts import process_quote
from data_worker.providers.indstocks import INDstocksProvider


class Command(BaseCommand):
    help = "Run the read-only INDstocks live-price worker for active Indian alerts."

    def add_arguments(self, parser):
        parser.add_argument("--live", action="store_true")
        parser.add_argument("--sync-instruments", action="store_true")

    def handle(self, *args, **options):
        token = os.getenv("INDSTOCKS_ACCESS_TOKEN")
        if not token:
            raise CommandError("INDSTOCKS_ACCESS_TOKEN is not configured.")
        symbols = list(
            Symbol.objects.filter(
                market=Symbol.Market.INDIA,
                price_alerts__is_active=True,
                price_alerts__status=PriceAlert.Status.ACTIVE,
            ).distinct().order_by("symbol")
        )
        self.stdout.write(f"Active India alert symbols: {', '.join(s.symbol for s in symbols) or 'none'}")
        if not symbols:
            raise CommandError("No active Indian price alerts exist.")
        if options["sync_instruments"]:
            self._sync(token, symbols)
        mappings = list(
            ProviderInstrument.objects.filter(provider="indstocks", symbol__in=symbols)
            .select_related("symbol")
        )
        missing = sorted({s.symbol for s in symbols} - {m.symbol.symbol for m in mappings})
        if missing:
            raise CommandError(
                "Missing INDstocks mappings for: " + ", ".join(missing)
                + ". Run again with --sync-instruments."
            )
        self.stdout.write("Mapped: " + ", ".join(f"{m.symbol.symbol}=NSE:{m.instrument_id}" for m in mappings))
        if not options["live"]:
            self.stdout.write("Configuration check only. Add --live to connect.")
            return
        try:
            asyncio.run(self._stream(token, mappings))
        finally:
            AlertWorkerState.objects.update_or_create(name="indstocks_ind", defaults={"status": "STOPPED"})

    def _sync(self, token, symbols):
        wanted = {symbol.symbol: symbol for symbol in symbols}
        rows = INDstocksProvider(token).equity_instruments()
        found = 0
        for row in rows:
            code = (row.get("TRADING_SYMBOL") or "").upper()
            if row.get("EXCH") != "NSE" or row.get("SERIES") != "EQ" or code not in wanted:
                continue
            ProviderInstrument.objects.update_or_create(
                symbol=wanted[code], provider="indstocks",
                defaults={
                    "instrument_id": row["SECURITY_ID"], "exchange_code": "NSE",
                    "segment": "EQUITY", "metadata": {"series": row.get("SERIES", "")},
                },
            )
            found += 1
        self.stdout.write(self.style.SUCCESS(f"Synchronized {found}/{len(symbols)} INDstocks mappings."))

    async def _stream(self, token, mappings):
        token_to_symbol = {mapping.instrument_id: mapping.symbol.symbol for mapping in mappings}
        instruments = [f"NSE:{token}" for token in token_to_symbol]
        while True:
            try:
                async with websockets.connect(
                    "wss://ws-prices.indstocks.com/api/v1/ws/prices",
                    additional_headers={"Authorization": token}, ping_interval=20, open_timeout=15,
                ) as socket:
                    await socket.send(json.dumps({
                        "action": "subscribe", "mode": "ltp", "instruments": instruments,
                    }))
                    self.stdout.write(self.style.SUCCESS("Connected to INDstocks live prices."))
                    await self._state(status="CONNECTED", connected_at=timezone.now(), last_error="")
                    async for raw in socket:
                        message = json.loads(raw)
                        token_id = str(message.get("instrument", ""))
                        price = (message.get("data") or {}).get("ltp")
                        if token_id not in token_to_symbol or price is None:
                            await self._state(last_heartbeat_at=timezone.now())
                            continue
                        timestamp = message.get("timestamp")
                        quote_at = (
                            datetime.fromtimestamp(timestamp / 1000, tz=datetime_timezone.utc)
                            if timestamp else timezone.now()
                        )
                        await sync_to_async(process_quote, thread_sensitive=True)(
                            token_to_symbol[token_id], price, quote_at, "IND"
                        )
                        await self._state(last_quote_at=quote_at, last_heartbeat_at=timezone.now())
            except KeyboardInterrupt:
                return
            except Exception as exc:
                await self._state(status="RECONNECTING", last_error=str(exc)[:1000])
                self.stderr.write(f"INDstocks connection lost: {exc}; retrying in 10 seconds")
                await asyncio.sleep(10)

    @staticmethod
    async def _state(**values):
        await sync_to_async(AlertWorkerState.objects.update_or_create, thread_sensitive=True)(
            name="indstocks_ind", defaults=values
        )
