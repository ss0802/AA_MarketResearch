from decimal import Decimal, ROUND_HALF_UP

from django.db.models import F, Max

from .models import MarketRegimeSnapshot, OHLCV, Symbol, TechnicalSnapshot


BENCHMARK_CANDIDATES = {
    Symbol.Market.INDIA: ["^NSEI"],
    Symbol.Market.US: ["SPY"],
}


def _pct(numerator, denominator):
    if not denominator:
        return Decimal("0")
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def classify_regime(score, previous_regime=""):
    # Hysteresis prevents a single borderline session from repeatedly flipping
    # a useful regime signal. Entry needs +/-4; an established regime persists
    # until its score weakens through +/-2.
    if previous_regime == MarketRegimeSnapshot.Regime.BULLISH and score >= 2:
        return MarketRegimeSnapshot.Regime.BULLISH
    if previous_regime == MarketRegimeSnapshot.Regime.BEARISH and score <= -2:
        return MarketRegimeSnapshot.Regime.BEARISH
    if score >= 4:
        return MarketRegimeSnapshot.Regime.BULLISH
    if score <= -4:
        return MarketRegimeSnapshot.Regime.BEARISH
    return MarketRegimeSnapshot.Regime.NEUTRAL


def _benchmark_for(market):
    for code in BENCHMARK_CANDIDATES[market]:
        for benchmark in Symbol.objects.filter(market=market, symbol=code, is_active=True):
            if benchmark.ohlcv.filter(timeframe=OHLCV.Timeframe.DAILY).count() >= 200:
                return benchmark
    raise ValueError(f"No benchmark with at least 200 daily bars exists for {market}.")


def calculate_market_regime(market, as_of_date=None):
    tradeable = Symbol.objects.filter(
        market=market, is_active=True,
        universe_memberships__universe__is_ohlcv_enabled=True,
        universe_memberships__effective_to__isnull=True,
    ).distinct()
    universe_size = tradeable.count()
    if not universe_size:
        raise ValueError(f"No active tradeable universe exists for {market}.")
    if as_of_date is None:
        as_of_date = TechnicalSnapshot.objects.filter(
            symbol__in=tradeable, timeframe=OHLCV.Timeframe.DAILY,
        ).aggregate(value=Max("as_of_date"))["value"]
    if as_of_date is None:
        raise ValueError(f"No daily technical snapshots exist for {market}.")

    current_snapshots = TechnicalSnapshot.objects.filter(
        symbol__in=tradeable, timeframe=OHLCV.Timeframe.DAILY, as_of_date=as_of_date,
    )
    breadth_count = current_snapshots.count()
    if not breadth_count:
        raise ValueError(f"No current breadth snapshots exist for {market} on {as_of_date}.")
    breadth20 = current_snapshots.exclude(sma20=None)
    breadth50 = current_snapshots.exclude(sma50=None)
    breadth200 = current_snapshots.exclude(sma200=None)
    eligible20, eligible50, eligible200 = breadth20.count(), breadth50.count(), breadth200.count()
    if not min(eligible20, eligible50, eligible200):
        raise ValueError(f"Insufficient moving-average eligibility for {market} on {as_of_date}.")
    above20 = breadth20.filter(price__gt=F("sma20")).count()
    above50 = breadth50.filter(price__gt=F("sma50")).count()
    above200 = breadth200.filter(price__gt=F("sma200")).count()
    pct20, pct50, pct200 = (_pct(above20, eligible20), _pct(above50, eligible50), _pct(above200, eligible200))

    previous_date = OHLCV.objects.filter(
        symbol__in=tradeable, timeframe=OHLCV.Timeframe.DAILY, date__lt=as_of_date,
    ).aggregate(value=Max("date"))["value"]
    current_prices = dict(OHLCV.objects.filter(
        symbol__in=tradeable, timeframe=OHLCV.Timeframe.DAILY, date=as_of_date,
    ).values_list("symbol_id", "close"))
    previous_prices = dict(OHLCV.objects.filter(
        symbol_id__in=current_prices, timeframe=OHLCV.Timeframe.DAILY, date=previous_date,
    ).values_list("symbol_id", "close")) if previous_date else {}
    advances = declines = unchanged = 0
    for symbol_id, close in current_prices.items():
        previous = previous_prices.get(symbol_id)
        if previous is None:
            continue
        if close > previous:
            advances += 1
        elif close < previous:
            declines += 1
        else:
            unchanged += 1
    ad_net = advances - declines

    benchmark = _benchmark_for(market)
    bars = list(benchmark.ohlcv.filter(
        timeframe=OHLCV.Timeframe.DAILY, date__lte=as_of_date,
    ).order_by("-date").values_list("date", "close")[:220])
    if not bars or bars[0][0] != as_of_date or len(bars) < 205:
        raise ValueError(f"Benchmark {benchmark.symbol} is not aligned to {as_of_date} with sufficient history.")
    closes = [Decimal(value) for _, value in reversed(bars)]
    close = closes[-1]
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50
    sma200 = sum(closes[-200:]) / 200
    sma20_five_days_ago = sum(closes[-25:-5]) / 20
    sma20_slope = (sma20 - sma20_five_days_ago) / Decimal("5")

    score = 0
    reasons = []
    binary_signals = [
        (close > sma20, "Benchmark above SMA20", "Benchmark below SMA20"),
        (sma20 > sma50, "SMA20 above SMA50", "SMA20 below SMA50"),
        (close > sma200, "Benchmark above SMA200", "Benchmark below SMA200"),
        (sma20_slope > 0, "SMA20 slope rising", "SMA20 slope falling"),
    ]
    for positive, positive_reason, negative_reason in binary_signals:
        score += 1 if positive else -1
        reasons.append(positive_reason if positive else negative_reason)
    for label, value in (("SMA20", pct20), ("SMA50", pct50), ("SMA200", pct200)):
        if value >= 55:
            score += 1
            reasons.append(f"{value}% above {label}: broad participation")
        elif value <= 45:
            score -= 1
            reasons.append(f"{value}% above {label}: weak participation")
        else:
            reasons.append(f"{value}% above {label}: mixed participation")
    if ad_net > 0:
        score += 1
        reasons.append("Advances exceed declines")
    elif ad_net < 0:
        score -= 1
        reasons.append("Declines exceed advances")
    else:
        reasons.append("Advances equal declines")
    previous = MarketRegimeSnapshot.objects.filter(market=market, as_of_date__lt=as_of_date).order_by("-as_of_date").first()
    regime = classify_regime(score, previous.regime if previous else "")
    previous_line = previous.advance_decline_line if previous else 0
    coverage = _pct(breadth_count, universe_size)
    long_term_eligibility = _pct(eligible200, universe_size)
    reasons.append(f"Current-data coverage {coverage}%; SMA200 eligibility {long_term_eligibility}%")
    snapshot, _ = MarketRegimeSnapshot.objects.update_or_create(
        market=market, as_of_date=as_of_date,
        defaults={
            "benchmark": benchmark, "benchmark_close": close, "benchmark_sma20": sma20,
            "benchmark_sma50": sma50, "benchmark_sma200": sma200,
            "benchmark_sma20_slope": sma20_slope, "universe_size": universe_size,
            "breadth_count": breadth_count, "coverage_pct": coverage,
            "eligible_sma20": eligible20, "eligible_sma50": eligible50, "eligible_sma200": eligible200,
            "pct_above_sma20": pct20, "pct_above_sma50": pct50, "pct_above_sma200": pct200,
            "advances": advances, "declines": declines, "unchanged": unchanged,
            "advance_decline_net": ad_net, "advance_decline_line": previous_line + ad_net,
            "score": score, "regime": regime, "previous_regime": previous.regime if previous else "",
            "is_transition": bool(previous and previous.regime != regime),
            "is_verified": coverage >= Decimal("98") and long_term_eligibility >= Decimal("80"),
            "reasons": reasons,
        },
    )
    return snapshot
