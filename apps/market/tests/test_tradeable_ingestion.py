from django.test import TestCase

from apps.market.management.commands.ingest_tradeable import yahoo_symbol
from apps.market.models import Symbol


class ProviderSymbolTests(TestCase):
    def test_nse_symbol_gets_yahoo_suffix(self):
        symbol = Symbol(symbol="RELIANCE", market=Symbol.Market.INDIA, exchange="NSE")
        self.assertEqual(yahoo_symbol(symbol), "RELIANCE.NS")

    def test_nse_provider_symbol_normalizes_special_separators(self):
        underscore = Symbol(symbol="BAJAJ_AUTO", market=Symbol.Market.INDIA, exchange="NSE")
        reit = Symbol(symbol="EMBASSY.RR", market=Symbol.Market.INDIA, exchange="NSE")
        self.assertEqual(yahoo_symbol(underscore), "BAJAJ-AUTO.NS")
        self.assertEqual(yahoo_symbol(reit), "EMBASSY.NS")

    def test_us_class_share_uses_yahoo_separator(self):
        symbol = Symbol(symbol="BRK.B", market=Symbol.Market.US, exchange="NYSE")
        self.assertEqual(yahoo_symbol(symbol), "BRK-B")

    def test_us_preferred_share_uses_yahoo_separator(self):
        symbol = Symbol(symbol="C/PN", market=Symbol.Market.US, exchange="NYSE")
        self.assertEqual(yahoo_symbol(symbol), "C-PN")
