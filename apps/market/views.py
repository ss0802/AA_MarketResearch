import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from django.db.models import Count, F, Max
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import ChartDrawing, MarketRegimeSnapshot, OHLCV, OHLCVIngestionState, Symbol, TechnicalSnapshot, WatchlistItem


def _yahoo_ticker_quotes(items):
    instruments = [item.symbol for item in items]
    from .services_quotes import fetch_yahoo_intraday_quotes
    fetched = fetch_yahoo_intraday_quotes(instruments)
    quotes = []
    for item in items:
        instrument = item.symbol
        try:
            quote = fetched[instrument.id]
            price = quote["price"]
            quote_time = quote["quote_time"]
            quote_date = quote_time.date()
            previous = instrument.ohlcv.filter(
                timeframe=OHLCV.Timeframe.DAILY, date__lt=quote_date,
            ).order_by("-date").first()
            if previous is None:
                previous = instrument.ohlcv.filter(timeframe=OHLCV.Timeframe.DAILY).order_by("-date").first()
            previous_close = previous.close if previous else None
            change = price - previous_close if previous_close is not None else None
            change_pct = change / previous_close * 100 if previous_close else None
            quotes.append({
                "id": item.id, "symbol": instrument.symbol, "market": instrument.market,
                "price": str(price.quantize(Decimal("0.01"))),
                "change": str(change.quantize(Decimal("0.01"))) if change is not None else None,
                "change_pct": str(change_pct.quantize(Decimal("0.01"))) if change_pct is not None else None,
                "quote_time": quote_time.isoformat(), "status": "ok",
            })
        except (InvalidOperation, KeyError, TypeError, ValueError):
            quotes.append({
                "id": item.id, "symbol": instrument.symbol, "market": instrument.market,
                "price": None, "change": None, "change_pct": None,
                "quote_time": None, "status": "unavailable",
            })
    return quotes


@require_http_methods(["GET", "POST"])
def watchlist_api(request):
    if request.method == "POST":
        try:
            payload = json.loads(request.body or "{}")
            market = str(payload.get("market") or "").upper()
            symbol_code = str(payload.get("symbol") or "").strip().upper()
            if market not in Symbol.Market.values or not symbol_code:
                raise ValueError("Choose a market and enter a symbol.")
            try:
                instrument = Symbol.objects.get(market=market, symbol=symbol_code, is_active=True)
            except Symbol.DoesNotExist:
                return JsonResponse({"error": f"No active {market} symbol named {symbol_code} was found."}, status=404)
            if WatchlistItem.objects.count() >= 20 and not WatchlistItem.objects.filter(symbol=instrument).exists():
                raise ValueError("The delayed ticker tape is limited to 20 symbols.")
            item, created = WatchlistItem.objects.get_or_create(symbol=instrument)
            return JsonResponse({"id": item.id, "created": created}, status=201 if created else 200)
        except (json.JSONDecodeError, ValueError) as error:
            return JsonResponse({"error": str(error)}, status=400)
    items = WatchlistItem.objects.select_related("symbol")
    return JsonResponse({
        "items": [{"id": item.id, "symbol": item.symbol.symbol, "market": item.symbol.market} for item in items]
    })


@require_http_methods(["DELETE"])
def watchlist_item_api(request, item_id):
    item = get_object_or_404(WatchlistItem, pk=item_id)
    item.delete()
    return JsonResponse({"deleted": True})


@ensure_csrf_cookie
@require_http_methods(["GET"])
def ticker_quotes_api(request):
    items = list(WatchlistItem.objects.select_related("symbol"))
    if not items:
        return JsonResponse({"quotes": [], "provider": "Yahoo", "delayed": True})
    cache_key = "ticker-quotes-v1-" + "-".join(str(item.id) for item in items)
    quotes = cache.get(cache_key)
    if quotes is None:
        try:
            quotes = _yahoo_ticker_quotes(items)
            cache.set(cache_key, quotes, 55)
        except Exception as error:
            return JsonResponse({
                "quotes": [], "provider": "Yahoo", "delayed": True,
                "error": f"Yahoo quotes are temporarily unavailable: {str(error)[:180]}",
            }, status=503)
    return JsonResponse({"quotes": quotes, "provider": "Yahoo", "delayed": True})


def _market_health_cards():
    cards = []
    ist = ZoneInfo("Asia/Kolkata")
    for market, name in ((Symbol.Market.INDIA, "India"), (Symbol.Market.US, "United States")):
        tradeable_symbols = Symbol.objects.filter(
            market=market,
            universe_memberships__universe__is_ohlcv_enabled=True,
            universe_memberships__effective_to__isnull=True,
        ).distinct()
        latest_date = OHLCV.objects.filter(
            symbol__market=market, timeframe=OHLCV.Timeframe.DAILY,
        ).aggregate(value=Max("date"))["value"]
        current_bars = 0
        if latest_date:
            current_bars = OHLCV.objects.filter(
                symbol__market=market, timeframe=OHLCV.Timeframe.DAILY, date=latest_date,
            ).values("symbol_id").distinct().count()
        states = OHLCVIngestionState.objects.filter(symbol__market=market, timeframe="D")
        running_count = states.filter(
            status=OHLCVIngestionState.Status.RUNNING,
            last_attempt_at__gte=timezone.now() - timedelta(minutes=30),
        ).values("symbol_id").distinct().count()
        latest_technical = TechnicalSnapshot.objects.filter(
            symbol__market=market, timeframe="D",
        ).aggregate(value=Max("as_of_date"))["value"]
        technical_count = TechnicalSnapshot.objects.filter(
            symbol__market=market, timeframe="D", as_of_date=latest_technical,
        ).count() if latest_technical else 0
        total = tradeable_symbols.count()
        coverage = (current_bars / total * 100) if total else 0
        finalization_cutoff = None
        finalized_bars = 0
        if latest_date:
            cutoff_date = latest_date if market == Symbol.Market.INDIA else latest_date + timedelta(days=1)
            cutoff_time = time(17, 45) if market == Symbol.Market.INDIA else time(5, 30)
            finalization_cutoff = datetime.combine(cutoff_date, cutoff_time, tzinfo=ist)
            finalized_bars = states.filter(
                status=OHLCVIngestionState.Status.SUCCESS,
                last_bar_date=latest_date,
                last_success_at__gte=finalization_cutoff,
            ).values("symbol_id").distinct().count()
        finalized_coverage = (finalized_bars / total * 100) if total else 0
        technical_coverage = (technical_count / total * 100) if total else 0
        technical_aligned = latest_technical == latest_date
        ready = (
            coverage >= 98
            and finalized_coverage >= 98
            and technical_coverage >= 98
            and technical_aligned
        )
        if running_count:
            certificate = "updating"
        elif coverage >= 98 and finalized_coverage < 98:
            certificate = "preliminary"
        elif ready:
            certificate = "ready"
        else:
            certificate = "attention"
        diagnostics = []
        if coverage < 98:
            diagnostics.append("Latest-session coverage is below 98%.")
        if coverage >= 98 and finalized_coverage < 98:
            diagnostics.append("Most candles were not confirmed by a successful post-close ingestion.")
        if not technical_aligned:
            diagnostics.append("Technical snapshots do not match the latest EOD date.")
        elif technical_coverage < 98:
            diagnostics.append("Technical-snapshot coverage is below 98%.")
        if states.filter(status=OHLCVIngestionState.Status.FAILED).exists():
            diagnostics.append("Known provider failures require review.")
        cards.append({
            "market": market, "name": name, "tradeable": total,
            "latest_date": latest_date, "current_bars": current_bars,
            "coverage_pct": coverage,
            "yahoo_success": states.filter(provider="yahoo", status="SUCCESS").values("symbol_id").distinct().count(),
            "yahoo_failed": states.filter(provider="yahoo", status="FAILED").values("symbol_id").distinct().count(),
            "tiingo_success": states.filter(provider="tiingo", status="SUCCESS").values("symbol_id").distinct().count(),
            "technical_date": latest_technical, "technical_count": technical_count,
            "technical_coverage_pct": technical_coverage,
            "running_count": running_count,
            "updating": running_count > 0,
            "finalized_bars": finalized_bars,
            "finalized_coverage_pct": finalized_coverage,
            "finalization_cutoff": finalization_cutoff,
            "certificate": certificate,
            "diagnostics": diagnostics,
            "ready": ready,
        })
    return cards


def dashboard(request):
    symbol_query = request.GET.get("symbol", "").strip().upper()
    market_query = request.GET.get("market", "IND")
    search_error = ""
    if symbol_query:
        matches = Symbol.objects.filter(symbol=symbol_query, market=market_query, is_active=True)
        if matches.exists():
            return redirect(f"/stocks/{symbol_query}/?market={market_query}")
        search_error = f"No active {market_query} symbol named {symbol_query} was found."

    market_cards = _market_health_cards()

    from apps.trading.models import Trade

    trades = Trade.objects.select_related("symbol")
    market_regimes = [
        MarketRegimeSnapshot.objects.filter(market=market).select_related("benchmark").order_by("-as_of_date").first()
        for market in (Symbol.Market.INDIA, Symbol.Market.US)
    ]
    context = {
        "market_cards": market_cards,
        "search_error": search_error,
        "trade_count": trades.count(),
        "open_trade_count": trades.filter(status=Trade.Status.OPEN).count(),
        "recent_trades": trades[:5],
        "market_regimes": market_regimes,
    }
    return render(request, "market/dashboard.html", context)


def data_health(request):
    from apps.trading.models import AlertWorkerState
    return render(request, "market/data_health.html", {
        "market_cards": _market_health_cards(),
        "us_worker": AlertWorkerState.objects.filter(name="tiingo_us").first(),
        "yahoo_worker": AlertWorkerState.objects.filter(name="yahoo_us_delayed").first(),
        "ind_worker": AlertWorkerState.objects.filter(name="indstocks_ind").first(),
    })


def guide(request):
    return render(request, "market/guide.html")


def market_condition(request, market):
    market = market.upper()
    if market not in Symbol.Market.values:
        return JsonResponse({"error": "Market must be IND or US."}, status=404)
    history = list(MarketRegimeSnapshot.objects.filter(market=market).select_related("benchmark").order_by("-as_of_date")[:300])
    history.reverse()
    chart_rows = [{
        "date": row.as_of_date, "close": row.benchmark_close,
        "sma20": row.benchmark_sma20, "sma50": row.benchmark_sma50, "sma200": row.benchmark_sma200,
        "above20": row.pct_above_sma20, "above50": row.pct_above_sma50, "above200": row.pct_above_sma200,
        "ad_line": row.advance_decline_line, "ad_net": row.advance_decline_net,
        "score": row.score, "regime": row.regime,
    } for row in history]
    return render(request, "market/market_condition.html", {
        "market": market, "market_name": "India" if market == Symbol.Market.INDIA else "United States",
        "latest": history[-1] if history else None,
        "transitions": list(reversed([row for row in history if row.is_transition][-12:])),
        "chart_data": json.dumps(chart_rows, cls=DjangoJSONEncoder),
    })


@ensure_csrf_cookie
def symbol_detail(request, symbol):
    symbol_code = symbol.upper()

    stock_lookup = {"symbol": symbol_code}
    if request.GET.get("market") in {"US", "IND"}:
        stock_lookup["market"] = request.GET["market"]
    stock = get_object_or_404(Symbol, **stock_lookup)

    def get_candles(timeframe):
        return list(
            OHLCV.objects
            .filter(
                symbol=stock,
                timeframe=timeframe,
            )
            .order_by("date")
            .values(
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
            )
        )

    daily = get_candles("D")
    weekly = get_candles("W")
    monthly = get_candles("M")

    chart_data = {
        "D": daily,
        "W": weekly,
        "M": monthly,
    }

    context = {
        "stock": stock,

        # Recent rows for tables
        "daily": reversed(daily[-20:]),
        "weekly": reversed(weekly[-20:]),
        "monthly": reversed(monthly[-20:]),

        "daily_count": len(daily),
        "weekly_count": len(weekly),
        "monthly_count": len(monthly),
        "market_regime": MarketRegimeSnapshot.objects.filter(
            market=stock.market, is_verified=True,
        ).order_by("-as_of_date").first(),

        # Complete history for chart
        "chart_data": json.dumps(
            chart_data,
            cls=DjangoJSONEncoder,
        ),
    }

    return render(
        request,
        "market/symbol_detail.html",
        context,
    )


def _drawing_payload(drawing):
    return {
        "id": drawing.id,
        "drawing_type": drawing.drawing_type,
        "source_timeframe": drawing.source_timeframe,
        "points": drawing.points,
        "label": drawing.label,
        "color": drawing.color,
        "line_width": drawing.line_width,
        "is_visible": drawing.is_visible,
        "is_locked": drawing.is_locked,
        "alert_count": drawing.price_alerts.exclude(status="ARCHIVED").count(),
    }


@require_http_methods(["GET", "POST"])
def chart_drawings(request, symbol_id):
    symbol = get_object_or_404(Symbol, pk=symbol_id)
    if request.method == "GET":
        drawings = symbol.chart_drawings.all()
        return JsonResponse({"drawings": [_drawing_payload(item) for item in drawings]})

    try:
        payload = json.loads(request.body or "{}")
        drawing_type = payload.get("drawing_type")
        required_points = {
            ChartDrawing.DrawingType.HORIZONTAL: 1,
            ChartDrawing.DrawingType.TREND_RAY: 2,
            ChartDrawing.DrawingType.PARALLEL_CHANNEL: 3,
        }[drawing_type]
        points = payload.get("points", [])
        if len(points) != required_points:
            raise ValueError(f"This drawing requires {required_points} point(s).")
        clean_points = []
        for point in points:
            point_date = date.fromisoformat(str(point["date"])[:10])
            point_price = Decimal(str(point["price"]))
            clean_points.append({"date": point_date.isoformat(), "price": str(point_price)})
        drawing = ChartDrawing(
            symbol=symbol,
            drawing_type=drawing_type,
            source_timeframe=payload.get("source_timeframe", "D"),
            points=clean_points,
            label=str(payload.get("label", ""))[:100],
            color=str(payload.get("color", "#7f56d9"))[:20],
            line_width=max(1, min(6, int(payload.get("line_width", 2)))),
        )
        drawing.full_clean()
        drawing.save()
    except (KeyError, TypeError, ValueError, InvalidOperation, DjangoValidationError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse({"drawing": _drawing_payload(drawing)}, status=201)


@require_http_methods(["PATCH", "DELETE"])
def chart_drawing_detail(request, drawing_id):
    drawing = get_object_or_404(ChartDrawing, pk=drawing_id)
    if request.method == "DELETE":
        if drawing.price_alerts.exclude(status="ARCHIVED").exists():
            return JsonResponse({"error": "Archive linked alerts before deleting this drawing."}, status=409)
        drawing.price_alerts.filter(status="ARCHIVED").update(source_drawing=None)
        try:
            drawing.delete()
        except ProtectedError:
            return JsonResponse({"error": "Archive linked alerts before deleting this drawing."}, status=409)
        return JsonResponse({}, status=204)
    try:
        payload = json.loads(request.body or "{}")
        for field in ("is_visible", "is_locked"):
            if field in payload:
                setattr(drawing, field, bool(payload[field]))
        if "label" in payload:
            drawing.label = str(payload["label"])[:100]
        drawing.save(update_fields=["is_visible", "is_locked", "label", "updated_at"])
    except (TypeError, ValueError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse({"drawing": _drawing_payload(drawing)})


@require_http_methods(["POST"])
def chart_drawing_alert(request, drawing_id):
    from apps.trading.models import PriceAlert

    drawing = get_object_or_404(ChartDrawing.objects.select_related("symbol"), pk=drawing_id)
    if drawing.drawing_type != ChartDrawing.DrawingType.HORIZONTAL:
        return JsonResponse({"error": "Dynamic ray/channel alerts are not enabled yet."}, status=400)
    try:
        payload = json.loads(request.body or "{}")
        direction = str(payload.get("direction", "")).upper()
        if direction not in PriceAlert.Direction.values:
            raise ValueError("Direction must be ABOVE or BELOW.")
        target = Decimal(str(drawing.points[0]["price"]))
        alert, created = PriceAlert.objects.get_or_create(
            source_drawing=drawing, direction=direction,
            defaults={"symbol": drawing.symbol, "target_price": target, "drawing_component": "LEVEL"},
        )
        if not created and alert.status != PriceAlert.Status.ACTIVE:
            alert.rearm()
        return JsonResponse({"alert": {"id": alert.id, "direction": alert.direction, "target_price": str(alert.target_price)}, "created": created}, status=201 if created else 200)
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        return JsonResponse({"error": str(error)}, status=400)


def technical_screener(request):
    market = request.GET.get("market", "IND")
    timeframe = request.GET.get("timeframe", "D")
    if market not in {"US", "IND"}:
        market = "IND"
    if timeframe not in {"D", "W", "M"}:
        timeframe = "D"
    market_regime = MarketRegimeSnapshot.objects.filter(
        market=market, is_verified=True,
    ).select_related("benchmark").order_by("-as_of_date").first()
    trade_direction = request.GET.get("trade_direction", "")
    if trade_direction not in {"LONG", "SHORT"}:
        trade_direction = ""
    regime_conflict = bool(market_regime and (
        (trade_direction == "LONG" and market_regime.regime == MarketRegimeSnapshot.Regime.BEARISH)
        or (trade_direction == "SHORT" and market_regime.regime == MarketRegimeSnapshot.Regime.BULLISH)
    ))

    snapshots = TechnicalSnapshot.objects.filter(
        symbol__market=market,
        timeframe=timeframe,
        symbol__is_active=True,
    ).select_related("symbol")

    text_filters = {
        "momentum": "momentum",
        "vwap": "vwap_status",
        "dmi": "dmi_status",
        "rsi_status": "rsi_status",
        "mcap": "symbol__market_cap_category",
    }
    for parameter, field in text_filters.items():
        value = request.GET.get(parameter)
        if value:
            snapshots = snapshots.filter(**{field: value})

    symbol_query = request.GET.get("symbol", "").strip()
    if symbol_query:
        snapshots = snapshots.filter(symbol__symbol__icontains=symbol_query)

    trending = request.GET.get("trending")
    if trending in {"yes", "no"}:
        snapshots = snapshots.filter(trending=(trending == "yes"))
    squeeze = request.GET.get("squeeze")
    if squeeze in {"yes", "no"}:
        snapshots = snapshots.filter(is_squeeze=(squeeze == "yes"))

    for period in (20, 50, 100, 150, 250):
        value = request.GET.get(f"sma{period}")
        field = f"sma{period}"
        if value == "above":
            snapshots = snapshots.filter(price__gt=F(field))
        elif value == "below":
            snapshots = snapshots.filter(price__lte=F(field))

    numeric_filters = {
        "rsi_min": ("rsi14__gte", float),
        "rsi_max": ("rsi14__lte", float),
        "adx_min": ("adx14__gte", float),
        "adx_max": ("adx14__lte", float),
    }
    for parameter, (lookup, converter) in numeric_filters.items():
        value = request.GET.get(parameter)
        if value:
            try:
                snapshots = snapshots.filter(**{lookup: converter(value)})
            except ValueError:
                pass

    regime_alignment = request.GET.get("regime_alignment", "")
    if regime_alignment == "aligned" and regime_conflict:
        snapshots = snapshots.none()
    elif regime_alignment == "conflict" and not regime_conflict:
        snapshots = snapshots.none()

    sort_fields = {
        "symbol": "symbol__symbol",
        "price": "price",
        "rsi": "rsi14",
        "adx": "adx14",
        "atr": "atr_pct",
    }
    sort = request.GET.get("sort", "symbol")
    direction = "-" if request.GET.get("direction") == "desc" else ""
    snapshots = snapshots.order_by(direction + sort_fields.get(sort, "symbol__symbol"))

    paginator = Paginator(snapshots, 100)
    page = paginator.get_page(request.GET.get("page"))
    for snapshot in page.object_list:
        for period in (20, 50, 100, 150, 250):
            average = getattr(snapshot, f"sma{period}")
            setattr(
                snapshot,
                f"sma{period}_status",
                "Bullish" if average is not None and snapshot.price > average else "Bearish",
            )

    query = request.GET.copy()
    query.pop("page", None)
    context = {
        "page": page,
        "market": market,
        "timeframe": timeframe,
        "filters": request.GET,
        "query_without_page": query.urlencode(),
        "result_count": paginator.count,
        "market_regime": market_regime,
        "trade_direction": trade_direction,
        "regime_alignment": regime_alignment,
        "regime_conflict": regime_conflict,
    }
    return render(request, "market/technical_screener.html", context)
