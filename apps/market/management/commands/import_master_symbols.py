import hashlib
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.market.models import (
    ImportBatch,
    Symbol,
    Universe,
    UniverseMembership,
    UnresolvedUniverseSymbol,
)


UNIVERSES = {
    "US_RESEARCH": (Symbol.Market.US, "US Research", "NYSE + NASDAQ", False),
    "US_TRADEABLE": (
        Symbol.Market.US,
        "US Tradeable",
        "Market cap > $300M and 30-day average dollar volume > $5M",
        True,
    ),
    "US_LEADERS": (
        Symbol.Market.US,
        "US Leaders",
        "Market cap > $2B and 30-day average dollar volume > $20M",
        False,
    ),
    "IND_RESEARCH": (Symbol.Market.INDIA, "India Research", "NSE", False),
    "IND_TRADEABLE": (
        Symbol.Market.INDIA,
        "India Tradeable",
        "Close > INR 50 and 30-day average turnover > INR 50M",
        True,
    ),
    "IND_LEADERS": (
        Symbol.Market.INDIA,
        "India Leaders",
        "Market cap > INR 50B and 30-day average turnover > INR 200M",
        False,
    ),
}

RESEARCH_SHEETS = {
    "us_research": (Symbol.Market.US, "US_RESEARCH"),
    "ind_research": (Symbol.Market.INDIA, "IND_RESEARCH"),
}

MEMBERSHIP_SHEETS = {
    "us_tradeable": "US_TRADEABLE",
    "us_leaders": "US_LEADERS",
    "ind_tradeable": "IND_TRADEABLE",
    "ind_leaders": "IND_LEADERS",
}

MARKET_CAP_MULTIPLIERS = {
    "K": Decimal("1000"),
    "M": Decimal("1000000"),
    "B": Decimal("1000000000"),
    "T": Decimal("1000000000000"),
}


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_market_cap(row):
    number = clean_text(row.get("market_cap_num"))
    suffix = clean_text(row.get("market_cap_alph")).upper()
    if not number or suffix not in MARKET_CAP_MULTIPLIERS:
        return None
    try:
        return Decimal(number.replace(",", "")) * MARKET_CAP_MULTIPLIERS[suffix]
    except InvalidOperation:
        return None


def parse_ipo_date(value):
    if pd.isna(value) or clean_text(value) == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


class Command(BaseCommand):
    help = "Import master instruments and universe memberships from MasterSymbolList.xlsx."

    def add_arguments(self, parser):
        parser.add_argument("workbook", type=Path)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Validate without writing to the database.")
        mode.add_argument("--commit", action="store_true", help="Write the validated import to the database.")
        parser.add_argument(
            "--effective-date",
            type=lambda value: pd.Timestamp(value).date(),
            default=timezone.localdate(),
        )

    def handle(self, *args, **options):
        path = options["workbook"].expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"Workbook not found: {path}")
        if path.suffix.lower() != ".xlsx":
            raise CommandError("The master-symbol import requires an .xlsx workbook.")

        commit = options["commit"]
        effective_date = options["effective_date"]
        frames = self._read_and_validate(path)
        stats = self._build_stats(frames)

        self._print_stats(stats, commit)
        if not commit:
            self.stdout.write(self.style.WARNING("Dry run only; no database changes were made."))
            return

        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        with transaction.atomic():
            batch = ImportBatch.objects.create(filename=path.name, checksum=checksum)
            try:
                symbols = self._upsert_symbols(frames)
                self._upsert_universes()
                unresolved = self._sync_memberships(
                    frames, symbols, batch, effective_date
                )
                stats["unresolved_memberships"] = unresolved
                batch.status = ImportBatch.Status.COMPLETED
                batch.stats = stats
                batch.save(update_fields=["status", "stats"])
            except Exception as exc:
                batch.status = ImportBatch.Status.FAILED
                batch.error = str(exc)
                batch.save(update_fields=["status", "error"])
                raise

        self.stdout.write(self.style.SUCCESS(f"Import batch {batch.pk} completed."))
        if unresolved:
            self.stdout.write(self.style.WARNING(f"Quarantined {unresolved} unresolved memberships."))

    def _read_and_validate(self, path):
        required = set(RESEARCH_SHEETS) | set(MEMBERSHIP_SHEETS)
        try:
            book = pd.ExcelFile(path)
        except Exception as exc:
            raise CommandError(f"Could not open workbook: {exc}") from exc
        missing = sorted(required - set(book.sheet_names))
        if missing:
            raise CommandError(f"Missing required sheets: {', '.join(missing)}")

        frames = {}
        required_columns = {
            "symbol", "company_name", "exchange", "country", "currency",
            "sector", "industry", "ipo_date", "market_cap_num",
            "market_cap_alph", "market_cap_category", "index_membership",
        }
        for sheet in RESEARCH_SHEETS:
            frame = pd.read_excel(path, sheet_name=sheet, dtype=object)
            missing_columns = sorted(required_columns - set(frame.columns))
            if missing_columns:
                raise CommandError(
                    f"{sheet} is missing columns: {', '.join(missing_columns)}"
                )
            frames[sheet] = frame
        for sheet in MEMBERSHIP_SHEETS:
            frame = pd.read_excel(path, sheet_name=sheet, dtype=object)
            if "Symbol" not in frame.columns:
                raise CommandError(f"{sheet} is missing the Symbol column")
            frames[sheet] = frame
        return frames

    def _build_stats(self, frames):
        stats = {"research": {}, "memberships": {}}
        for sheet in RESEARCH_SHEETS:
            frame = frames[sheet]
            symbols = frame["symbol"].map(clean_text)
            valid = frame[symbols != ""]
            stats["research"][sheet] = {
                "source_rows": len(frame),
                "valid_symbols": len(valid),
                "blank_symbols": int((symbols == "").sum()),
                "duplicate_symbols": int(symbols[symbols != ""].duplicated().sum()),
            }
        for sheet in MEMBERSHIP_SHEETS:
            symbols = frames[sheet]["Symbol"].map(clean_text)
            stats["memberships"][sheet] = {
                "source_rows": len(frames[sheet]),
                "valid_symbols": int((symbols != "").sum()),
                "duplicate_symbols": int(symbols[symbols != ""].duplicated().sum()),
            }
        return stats

    def _print_stats(self, stats, commit):
        self.stdout.write(f"Mode: {'COMMIT' if commit else 'DRY RUN'}")
        for section in ("research", "memberships"):
            for sheet, values in stats[section].items():
                self.stdout.write(
                    f"{sheet}: {values['valid_symbols']} valid, "
                    f"{values.get('blank_symbols', 0)} blank, "
                    f"{values['duplicate_symbols']} duplicates"
                )

    def _upsert_symbols(self, frames):
        resolved = {}
        for sheet, (market, _) in RESEARCH_SHEETS.items():
            for _, row in frames[sheet].iterrows():
                ticker = clean_text(row.get("symbol")).upper()
                exchange = clean_text(row.get("exchange")).upper()
                if not ticker or not exchange:
                    continue
                defaults = {
                    "name": clean_text(row.get("company_name")),
                    "country": clean_text(row.get("country")),
                    "currency": clean_text(row.get("currency")) or ("USD" if market == Symbol.Market.US else "INR"),
                    "sector": clean_text(row.get("sector")),
                    "industry": clean_text(row.get("industry")),
                    "ipo_date": parse_ipo_date(row.get("ipo_date")),
                    "market_cap": parse_market_cap(row),
                    "market_cap_category": clean_text(row.get("market_cap_category")),
                    "index_membership": clean_text(row.get("index_membership")),
                    "is_active": True,
                }
                obj = Symbol.objects.filter(
                    market=market, exchange=exchange, symbol=ticker
                ).first()
                if obj is None:
                    # Preserve OHLCV links created before exchange-aware master data
                    # existed by promoting the one legacy blank-exchange record.
                    legacy = Symbol.objects.filter(
                        market=market, exchange="", symbol=ticker
                    )
                    obj = legacy.first() if legacy.count() == 1 else None
                if obj is None:
                    obj = Symbol(market=market, exchange=exchange, symbol=ticker)
                else:
                    obj.exchange = exchange
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save()
                resolved[(market, ticker)] = obj
        return resolved

    def _upsert_universes(self):
        for code, (market, name, definition, ohlcv_enabled) in UNIVERSES.items():
            Universe.objects.update_or_create(
                code=code,
                defaults={
                    "market": market,
                    "name": name,
                    "definition": definition,
                    "is_ohlcv_enabled": ohlcv_enabled,
                },
            )

    def _sync_memberships(self, frames, symbols, batch, effective_date):
        requested = {}
        for sheet, (market, universe_code) in RESEARCH_SHEETS.items():
            requested[universe_code] = {
                (market, clean_text(value).upper())
                for value in frames[sheet]["symbol"]
                if clean_text(value)
            }
        for sheet, universe_code in MEMBERSHIP_SHEETS.items():
            market = UNIVERSES[universe_code][0]
            requested[universe_code] = {
                (market, clean_text(value).upper())
                for value in frames[sheet]["Symbol"]
                if clean_text(value)
            }

        unresolved_count = 0
        for universe_code, keys in requested.items():
            universe = Universe.objects.get(code=universe_code)
            member_ids = set()
            for key in keys:
                obj = symbols.get(key)
                if obj is None:
                    obj = Symbol.objects.filter(market=key[0], symbol=key[1]).first()
                if obj is None:
                    UnresolvedUniverseSymbol.objects.get_or_create(
                        import_batch=batch,
                        universe_code=universe_code,
                        symbol=key[1],
                        defaults={"reason": "Symbol is absent from the matching research sheet"},
                    )
                    unresolved_count += 1
                    continue
                member_ids.add(obj.pk)
                UniverseMembership.objects.update_or_create(
                    universe=universe,
                    symbol=obj,
                    effective_from=effective_date,
                    defaults={"effective_to": None, "import_batch": batch},
                )

            prior = UniverseMembership.objects.filter(
                universe=universe, effective_to__isnull=True
            ).exclude(symbol_id__in=member_ids).exclude(effective_from=effective_date)
            prior.update(effective_to=effective_date - timedelta(days=1))
        return unresolved_count
