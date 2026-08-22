from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.market.models import Symbol, TechnicalSnapshot


class TechnicalScreenerTests(TestCase):
    def setUp(self):
        self.symbol = Symbol.objects.create(
            symbol="TEST",
            market=Symbol.Market.INDIA,
            exchange="NSE",
            market_cap_category="Mid",
        )
        TechnicalSnapshot.objects.create(
            symbol=self.symbol,
            timeframe="D",
            as_of_date=date(2026, 8, 14),
            price=Decimal("120"),
            sma20=Decimal("110"),
            momentum="Bullish",
            vwap_status="Bullish",
            trending=True,
            dmi_status="Bullish",
            rsi14=Decimal("60"),
            rsi_status="Upper Zone",
            is_squeeze=True,
        )

    def test_displays_matching_snapshot(self):
        response = self.client.get(reverse("market:technical_screener"))
        self.assertContains(response, "TEST")
        self.assertContains(response, "Upper Zone")
        self.assertContains(response, "Planned direction")
        self.assertContains(response, "Regime relationship")
        self.assertContains(response, "Choose side")

    def test_applies_sma_and_momentum_filters(self):
        response = self.client.get(
            reverse("market:technical_screener"),
            {"market": "IND", "timeframe": "D", "sma20": "above", "momentum": "Bullish"},
        )
        self.assertContains(response, "TEST")

        response = self.client.get(
            reverse("market:technical_screener"),
            {"market": "IND", "timeframe": "D", "sma20": "below"},
        )
        self.assertNotContains(response, ">TEST</a>")
