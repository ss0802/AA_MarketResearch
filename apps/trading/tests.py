from datetime import datetime, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.market.models import OHLCV, Symbol, TechnicalSnapshot

from .models import Trade
from .services import capture_trade_setup


class TradeJournalTests(TestCase):
    def setUp(self):
        self.symbol = Symbol.objects.create(symbol="TEST", market="IND", exchange="NSE")
        OHLCV.objects.create(
            symbol=self.symbol, timeframe="D", date="2026-08-14", open=100, high=105,
            low=99, close=104, adj_close=104, volume=1000,
        )
        OHLCV.objects.create(
            symbol=self.symbol, timeframe="D", date="2026-08-17", open=104, high=110,
            low=102, close=108, adj_close=108, volume=1200,
        )
        TechnicalSnapshot.objects.create(
            symbol=self.symbol, timeframe="D", as_of_date="2026-08-17", price=108,
            sma20=100, sma50=95, sma100=90, sma150=85, sma250=80,
            atr14=5, atr_pct=4.6, adr20=5, adr_pct=4.6,
        )

    def test_trade_risk_pnl_and_r_multiple(self):
        trade = Trade.objects.create(
            symbol=self.symbol, side="LONG", status="STOPPED",
            entry_at=datetime(2026, 8, 17, 6, 0, tzinfo=timezone.utc), entry_price=355,
            quantity=50, stop_price=Decimal("349.25"), exit_at=datetime(2026, 8, 17, 7, 0, tzinfo=timezone.utc),
            exit_price=Decimal("349.25"), charges=0,
        )
        self.assertEqual(trade.planned_risk, Decimal("287.50"))
        self.assertEqual(trade.net_pnl, Decimal("-287.50"))
        self.assertEqual(trade.r_multiple, Decimal("-1"))

    def test_snapshot_is_hashed_and_immutable(self):
        trade = Trade.objects.create(
            symbol=self.symbol, entry_at=datetime.now(timezone.utc), entry_price=109,
            quantity=10, stop_price=104,
        )
        snapshot = capture_trade_setup(trade, "Momentum: Bullish")
        self.assertEqual(len(snapshot.payload_hash), 64)
        self.assertEqual(snapshot.entry_quality["stop_atr_units"], "1")
        snapshot.screener_context = {}
        with self.assertRaises(ValidationError):
            snapshot.save()

    def test_journal_pages_open(self):
        self.assertEqual(self.client.get(reverse("trading:trade_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("trading:trade_create")).status_code, 200)
