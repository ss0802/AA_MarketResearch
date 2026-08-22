import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from django.forms.models import model_to_dict

from apps.market.models import MarketRegimeSnapshot, OHLCV, TechnicalSnapshot

from .models import TradeSetupSnapshot


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _serialise(record):
    return {key: _json_value(value) for key, value in record.items()}


def _distance(entry, reference):
    if reference is None:
        return None
    difference = entry - reference
    return {
        "amount": str(difference),
        "percent": str((difference / reference * 100) if reference else Decimal("0")),
    }


def capture_trade_setup(trade, screener_filters="", chart_image=None):
    technicals = {}
    versions = {}
    latest_date = None
    for snapshot in TechnicalSnapshot.objects.filter(symbol=trade.symbol):
        values = model_to_dict(snapshot, exclude=["id", "symbol"])
        technicals[snapshot.timeframe] = _serialise(values)
        versions[snapshot.timeframe] = snapshot.calculation_version
        if latest_date is None or snapshot.as_of_date > latest_date:
            latest_date = snapshot.as_of_date

    bars = {}
    for timeframe in (OHLCV.Timeframe.DAILY, OHLCV.Timeframe.WEEKLY, OHLCV.Timeframe.MONTHLY):
        rows = OHLCV.objects.filter(symbol=trade.symbol, timeframe=timeframe).order_by("-date").values(
            "date", "open", "high", "low", "close", "volume"
        )[:260]
        bars[timeframe] = [_serialise(row) for row in reversed(list(rows))]

    daily = technicals.get("D", {})
    daily_bars = bars.get("D", [])
    previous_bar = daily_bars[-2] if len(daily_bars) >= 2 else None
    entry = trade.entry_price
    atr = Decimal(daily["atr14"]) if daily.get("atr14") else None
    stop_distance = abs(entry - trade.stop_price)
    entry_quality = {
        "risk_per_share": str(stop_distance),
        "planned_risk": str(trade.planned_risk),
        "stop_percent": str(stop_distance / entry * 100),
        "stop_atr_units": str(stop_distance / atr) if atr else None,
        "previous_close": _distance(entry, Decimal(previous_bar["close"])) if previous_bar else None,
        "previous_high": _distance(entry, Decimal(previous_bar["high"])) if previous_bar else None,
    }
    for field in ("sma20", "sma50", "sma100", "sma150", "sma250", "bb20_upper", "bb20_middle", "bb20_lower"):
        value = daily.get(field)
        entry_quality[field] = _distance(entry, Decimal(value)) if value else None

    context = {
        "raw": screener_filters,
        "lines": [line.strip() for line in screener_filters.splitlines() if line.strip()],
        "setup_name": trade.setup_name,
        "setup_tags": trade.setup_tags,
    }
    regime = MarketRegimeSnapshot.objects.filter(
        market=trade.symbol.market, is_verified=True,
    ).select_related("benchmark").order_by("-as_of_date").first()
    context["market_regime"] = None if regime is None else {
        "id": regime.id, "market": regime.market, "as_of_date": regime.as_of_date.isoformat(),
        "benchmark": regime.benchmark.symbol, "regime": regime.regime,
        "score": regime.score, "coverage_pct": str(regime.coverage_pct),
        "pct_above_sma20": str(regime.pct_above_sma20),
        "pct_above_sma50": str(regime.pct_above_sma50),
        "pct_above_sma200": str(regime.pct_above_sma200),
        "advance_decline_net": regime.advance_decline_net,
        "reasons": regime.reasons,
    }
    payload = {
        "technicals": technicals, "recent_bars": bars, "entry_quality": entry_quality,
        "screener_context": context, "calculation_versions": versions,
    }
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TradeSetupSnapshot.objects.create(
        trade=trade, data_as_of_date=latest_date, chart_image=chart_image,
        payload_hash=payload_hash, **payload,
    )
