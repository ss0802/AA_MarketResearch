from django.test import TestCase
from django.urls import reverse

from apps.market.models import ChartDrawing, OHLCV, Symbol


class SymbolChartTests(TestCase):
    def setUp(self):
        self.symbol = Symbol.objects.create(symbol="CHART", market="US", exchange="NASDAQ")
        OHLCV.objects.create(
            symbol=self.symbol, timeframe="D", date="2026-08-14",
            open=100, high=105, low=99, close=104, adj_close=104, volume=1000,
        )

    def test_chart_includes_drawing_and_macd_controls(self):
        response = self.client.get(
            reverse("market:symbol_detail", args=[self.symbol.symbol]),
            {"market": "US"},
        )
        self.assertContains(response, "Clear temporary lines")
        self.assertContains(response, "MACD (12, 26, 9)")
        self.assertContains(response, 'modeBarButtonsToAdd: ["drawline", "eraseshape"]')
        self.assertContains(response, "function macdSeries")
        self.assertContains(response, 'const higherTimeframe = {D: "W", W: "M", M: null}[timeframe]')
        self.assertContains(response, 'drawMacdPanel("macd-mtf-" + timeframe, timeframe, true)')
        self.assertContains(response, "mtf-macd", count=4)
        self.assertContains(response, 'minallowed: 0', count=2)
        self.assertContains(response, 'hovermode: "x unified"', count=2)
        self.assertContains(response, "function candleVolumeRange")

    def test_saved_drawing_api_uses_symbol_level_coordinates(self):
        response = self.client.post(
            reverse("market:chart_drawings", args=[self.symbol.id]),
            data={
                "drawing_type": "PARALLEL_CHANNEL",
                "source_timeframe": "W",
                "points": [
                    {"date": "2026-01-02", "price": "100"},
                    {"date": "2026-03-06", "price": "120"},
                    {"date": "2026-02-06", "price": "90"},
                ],
                "label": "Weekly base",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        drawing = ChartDrawing.objects.get()
        self.assertEqual(drawing.symbol, self.symbol)
        self.assertEqual(drawing.source_timeframe, "W")
        self.assertEqual(len(drawing.points), 3)

        listing = self.client.get(reverse("market:chart_drawings", args=[self.symbol.id]))
        self.assertEqual(listing.json()["drawings"][0]["label"], "Weekly base")

    def test_dashboard_renders_and_symbol_search_redirects(self):
        response = self.client.get(reverse("market:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inspect Data Health")
        self.assertContains(response, "Market condition")
        self.assertContains(response, "Technical Screener")
        health = self.client.get(reverse("market:data_health"))
        self.assertEqual(health.status_code, 200)
        self.assertContains(health, "Provider, coverage, technical-snapshot")
        self.assertContains(health, "Automatic update schedule")
        self.assertContains(health, "India · 6:00 PM IST")
        self.assertContains(health, "United States · 6:00 AM IST")
        self.assertContains(health, "technical snapshots are recomputed automatically")
        guide = self.client.get(reverse("market:guide"))
        self.assertEqual(guide.status_code, 200)
        self.assertContains(guide, "Using AA MarketResearch")
        search = self.client.get(reverse("market:dashboard"), {"market": "US", "symbol": "chart"})
        self.assertEqual(search.status_code, 302)
        self.assertEqual(search.url, "/stocks/CHART/?market=US")
