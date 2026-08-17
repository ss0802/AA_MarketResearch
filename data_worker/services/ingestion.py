from decimal import Decimal

import pandas as pd
from django.db import transaction

from apps.market.models import OHLCV, Symbol
from data_worker.services.validator import validate_ohlcv


def _to_decimal(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _resolve_symbol(df: pd.DataFrame, symbol_instance: Symbol | None) -> Symbol:
    codes = {str(value).upper() for value in df["symbol"].unique()}
    if len(codes) != 1:
        raise ValueError("One OHLCV ingestion call must contain exactly one symbol")
    code = codes.pop()
    if symbol_instance is not None:
        if symbol_instance.symbol.upper() != code:
            raise ValueError("The supplied Symbol does not match the OHLCV data")
        return symbol_instance

    matches = Symbol.objects.filter(symbol=code)
    if matches.count() > 1:
        raise ValueError(
            f"Symbol {code} exists in multiple markets; pass symbol_instance explicitly"
        )
    return matches.first() or Symbol.objects.create(
        symbol=code, market=Symbol.Market.US, currency="USD"
    )


@transaction.atomic
def ingest_ohlcv(df: pd.DataFrame, symbol_instance: Symbol | None = None) -> dict:
    """Validate and bulk-upsert canonical OHLCV for one exact instrument."""
    validate_ohlcv(df)
    symbol = _resolve_symbol(df, symbol_instance)
    keys = [(row.timeframe, row.date) for row in df.itertuples(index=False)]
    existing = {
        (bar.timeframe, bar.date): bar
        for bar in OHLCV.objects.filter(
            symbol=symbol,
            timeframe__in={key[0] for key in keys},
            date__in={key[1] for key in keys},
        )
    }
    to_create, to_update = [], []
    unchanged = 0
    fields = ["open", "high", "low", "close", "adj_close", "volume"]

    for row in df.itertuples(index=False):
        values = {
            "open": _to_decimal(row.open),
            "high": _to_decimal(row.high),
            "low": _to_decimal(row.low),
            "close": _to_decimal(row.close),
            "adj_close": _to_decimal(row.adj_close),
            "volume": int(row.volume),
        }
        bar = existing.get((row.timeframe, row.date))
        if bar is None:
            to_create.append(
                OHLCV(symbol=symbol, timeframe=row.timeframe, date=row.date, **values)
            )
        elif any(getattr(bar, field) != value for field, value in values.items()):
            for field, value in values.items():
                setattr(bar, field, value)
            to_update.append(bar)
        else:
            unchanged += 1

    if to_create:
        OHLCV.objects.bulk_create(to_create, batch_size=1000)
    if to_update:
        OHLCV.objects.bulk_update(to_update, fields, batch_size=1000)

    return {
        "created": len(to_create),
        "updated": len(to_update),
        "unchanged": unchanged,
        "total": len(df),
    }
