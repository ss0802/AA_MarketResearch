from decimal import Decimal

import pandas as pd
from django.test import SimpleTestCase

from apps.market.management.commands.import_master_symbols import (
    clean_text,
    parse_ipo_date,
    parse_market_cap,
)


class MasterSymbolParsingTests(SimpleTestCase):
    def test_market_cap_uses_decimal_suffix_multiplier(self):
        row = pd.Series({"market_cap_num": "268.84", "market_cap_alph": "B"})

        self.assertEqual(parse_market_cap(row), Decimal("268840000000.00"))

    def test_market_cap_rejects_unknown_suffix(self):
        row = pd.Series({"market_cap_num": "12.5", "market_cap_alph": "X"})

        self.assertIsNone(parse_market_cap(row))

    def test_excel_values_are_normalized(self):
        self.assertEqual(clean_text("  aaoi  "), "aaoi")
        self.assertEqual(clean_text(float("nan")), "")
        self.assertEqual(str(parse_ipo_date("2024-05-15")), "2024-05-15")
