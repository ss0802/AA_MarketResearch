from datetime import datetime, timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from apps.market.models import OHLCV, Symbol, TechnicalSnapshot

from .models import AlertEvent, AlertWorkerState, PriceAlert, Trade, TradePositionMark
from .services_alerts import process_quote
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
        self.assertIn("market_regime", snapshot.screener_context)
        snapshot.screener_context = {}
        with self.assertRaises(ValidationError):
            snapshot.save()

    def test_journal_pages_open(self):
        self.assertEqual(self.client.get(reverse("trading:trade_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("trading:trade_create")).status_code, 200)

    def test_trade_book_marks_open_position(self):
        trade = Trade.objects.create(
            symbol=self.symbol, status=Trade.Status.OPEN,
            entry_at=datetime.now(timezone.utc), entry_price=100,
            quantity=10, stop_price=95, current_stop_price=102,
        )
        response = self.client.post(reverse("trading:trade_book"), {
            "trade_id": trade.pk, "current_stop": "103", "mark_price": "110",
        })
        self.assertEqual(response.status_code, 302)
        trade.refresh_from_db()
        self.assertEqual(trade.current_stop_price, Decimal("103"))
        self.assertEqual(TradePositionMark.objects.get(trade=trade).price, Decimal("110"))
        page = self.client.get(reverse("trading:trade_book"))
        self.assertContains(page, "Trade Book")
        self.assertContains(page, "100.00")
        self.assertContains(page, "110.00")

    def test_chart_planner_sizes_and_freezes_plan(self):
        response = self.client.post(
            reverse("trading:chart_trade_plan"),
            data={
                "symbol_id": self.symbol.pk, "side": "LONG", "entry_price": "110",
                "stop_price": "105", "maximum_risk": "1000", "target_r": "3",
                "timeframe": "W", "setup_name": "Weekly breakout", "thesis": "Retest held",
                "create_entry_alert": True, "create_stop_alert": True, "create_target_alert": True,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        trade = Trade.objects.get(pk=response.json()["trade_id"])
        self.assertEqual(trade.status, Trade.Status.PLANNED)
        self.assertEqual(trade.quantity, 200)
        self.assertEqual(trade.planned_risk, Decimal("1000"))
        self.assertEqual(trade.target_price, Decimal("125"))
        self.assertTrue(hasattr(trade, "setup_snapshot"))
        self.assertEqual(trade.price_alerts.count(), 3)
        entry = trade.price_alerts.get(alert_role=PriceAlert.Role.ENTRY)
        stop = trade.price_alerts.get(alert_role=PriceAlert.Role.STOP)
        target = trade.price_alerts.get(alert_role=PriceAlert.Role.TARGET)
        self.assertEqual((entry.direction, entry.status), (PriceAlert.Direction.ABOVE, PriceAlert.Status.ACTIVE))
        self.assertEqual((stop.direction, stop.status), (PriceAlert.Direction.BELOW, PriceAlert.Status.PAUSED))
        self.assertEqual((target.target_price, target.status), (Decimal("125"), PriceAlert.Status.PAUSED))
        trade.price_alerts.update(notify_telegram=False, notify_desktop=False, notify_sound=False)
        process_quote("TEST", 109, market="IND")
        process_quote("TEST", 111, market="IND")
        stop.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(stop.status, PriceAlert.Status.ACTIVE)
        self.assertEqual(target.status, PriceAlert.Status.ACTIVE)

    def test_indstocks_postback_is_safe_placeholder(self):
        status = self.client.get(reverse("indstocks_postback"))
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["order_processing"], "disabled")
        postback = self.client.post(
            reverse("indstocks_postback"), data={"order_id": "ignored"},
            content_type="application/json",
        )
        self.assertEqual(postback.status_code, 202)
        self.assertEqual(postback.json()["order_processing"], "disabled")

    def test_existing_plan_can_create_staged_alerts(self):
        trade = Trade.objects.create(
            symbol=self.symbol, side=Trade.Side.LONG, status=Trade.Status.PLANNED,
            entry_at=datetime.now(timezone.utc), entry_price=110, quantity=10,
            stop_price=105, target_price=125,
        )
        response = self.client.post(
            reverse("trading:trade_detail", args=[trade.pk]),
            {"action": "create_plan_alerts"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(trade.price_alerts.count(), 3)
        self.assertEqual(
            trade.price_alerts.get(alert_role=PriceAlert.Role.ENTRY).status,
            PriceAlert.Status.ACTIVE,
        )
        self.assertEqual(
            trade.price_alerts.get(alert_role=PriceAlert.Role.STOP).status,
            PriceAlert.Status.PAUSED,
        )

    @patch("apps.trading.management.commands.run_yahoo_alerts.fetch_yahoo_intraday_quotes")
    def test_yahoo_delayed_worker_processes_one_batch(self, fetch_quotes):
        self.symbol.market = Symbol.Market.US
        self.symbol.save(update_fields=["market"])
        alert = PriceAlert.objects.create(
            symbol=self.symbol, direction=PriceAlert.Direction.ABOVE, target_price=110,
            notify_telegram=False, notify_desktop=False, notify_sound=False,
        )
        quote_time = datetime.now(timezone.utc)
        fetch_quotes.return_value = {self.symbol.id: {"price": Decimal("109"), "quote_time": quote_time}}
        call_command("run_yahoo_alerts", "--once")
        alert.refresh_from_db()
        self.assertEqual(alert.last_price, Decimal("109"))
        self.assertEqual(AlertWorkerState.objects.get(name="yahoo_us_delayed").status, "CONNECTED_DELAYED")

    def test_price_alert_crosses_once(self):
        alert = PriceAlert.objects.create(symbol=self.symbol, direction="ABOVE", target_price=110, notify_telegram=False)
        process_quote("TEST", 109)
        self.assertEqual(process_quote("TEST", 111), [])  # Default provider market is US.
        process_quote("TEST", 109, market="IND")
        self.assertEqual(len(process_quote("TEST", 111, market="IND")), 1)
        alert.rearm()
        alert.symbol.market = "US"
        alert.symbol.save(update_fields=["market"])
        process_quote("TEST", 109)
        self.assertEqual(len(process_quote("TEST", 111)), 1)
        self.assertEqual(AlertEvent.objects.count(), 2)
        alert.refresh_from_db()
        self.assertFalse(alert.is_active)
        self.assertEqual(alert.status, PriceAlert.Status.TRIGGERED)
        alert.rearm()
        alert.refresh_from_db()
        self.assertTrue(alert.is_active)
        self.assertEqual(alert.status, PriceAlert.Status.ACTIVE)
        self.assertIsNone(alert.last_price)
