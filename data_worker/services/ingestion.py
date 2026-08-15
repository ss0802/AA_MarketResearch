from decimal import Decimal

import pandas as pd
from django.db import transaction

from apps.market.models import OHLCV, Symbol
from data_worker.services.validator import validate_ohlcv


def _to_decimal(value) -> Decimal:
    """
    Convert pandas/numpy numeric values safely to Decimal.
    """
    return Decimal(str(value))


@transaction.atomic
def ingest_ohlcv(df: pd.DataFrame) -> dict:
    """
    Validate and persist canonical OHLCV data.

    The DataFrame must already have been normalized.

    Returns ingestion statistics:
        created
        updated
        unchanged
        total
    """

    validate_ohlcv(df)

    stats = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "total": len(df),
    }

    for row in df.itertuples(index=False):

        symbol, _ = Symbol.objects.get_or_create(
            symbol=row.symbol,
            defaults={
                "currency": "USD",
            },
        )

        values = {
            "open": _to_decimal(row.open),
            "high": _to_decimal(row.high),
            "low": _to_decimal(row.low),
            "close": _to_decimal(row.close),
            "adj_close": _to_decimal(row.adj_close),
            "volume": int(row.volume),
        }

        existing = OHLCV.objects.filter(
            symbol=symbol,
            timeframe=row.timeframe,
            date=row.date,
        ).first()

        if existing is None:
            OHLCV.objects.create(
                symbol=symbol,
                timeframe=row.timeframe,
                date=row.date,
                **values,
            )

            stats["created"] += 1
            continue

        changed = any(
            getattr(existing, field) != value
            for field, value in values.items()
        )

        if not changed:
            stats["unchanged"] += 1
            continue

        for field, value in values.items():
            setattr(existing, field, value)

        existing.save(
            update_fields=list(values.keys())
        )

        stats["updated"] += 1

    return stats