import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, F, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import ChartDrawing, OHLCV, OHLCVIngestionState, Symbol, TechnicalSnapshot


def dashboard(request):
    symbol_query = request.GET.get("symbol", "").strip().upper()
    market_query = request.GET.get("market", "IND")
    search_error = ""
    if symbol_query:
        matches = Symbol.objects.filter(symbol=symbol_query, market=market_query, is_active=True)
        if matches.exists():
            return redirect(f"/stocks/{symbol_query}/?market={market_query}")
        search_error = f"No active {market_query} symbol named {symbol_query} was found."

    market_cards = []
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
        state_counts = {
            item["status"]: item["count"]
            for item in OHLCVIngestionState.objects.filter(
                symbol__market=market, timeframe=OHLCV.Timeframe.DAILY,
            ).values("status").annotate(count=Count("id"))
        }
        latest_technical = TechnicalSnapshot.objects.filter(
            symbol__market=market, timeframe=OHLCV.Timeframe.DAILY,
        ).aggregate(value=Max("as_of_date"))["value"]
        technical_count = 0
        if latest_technical:
            technical_count = TechnicalSnapshot.objects.filter(
                symbol__market=market,
                timeframe=OHLCV.Timeframe.DAILY,
                as_of_date=latest_technical,
            ).count()
        total = tradeable_symbols.count()
        market_cards.append({
            "market": market,
            "name": name,
            "tradeable": total,
            "latest_date": latest_date,
            "current_bars": current_bars,
            "coverage_pct": (current_bars / total * 100) if total else 0,
            "success": state_counts.get("SUCCESS", 0),
            "failed": state_counts.get("FAILED", 0),
            "technical_date": latest_technical,
            "technical_count": technical_count,
        })

    from apps.trading.models import Trade

    trades = Trade.objects.select_related("symbol")
    context = {
        "market_cards": market_cards,
        "search_error": search_error,
        "trade_count": trades.count(),
        "open_trade_count": trades.filter(status=Trade.Status.OPEN).count(),
        "recent_trades": trades[:5],
    }
    return render(request, "market/dashboard.html", context)


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
        drawing.delete()
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


def technical_screener(request):
    market = request.GET.get("market", "IND")
    timeframe = request.GET.get("timeframe", "D")
    if market not in {"US", "IND"}:
        market = "IND"
    if timeframe not in {"D", "W", "M"}:
        timeframe = "D"

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
    }
    return render(request, "market/technical_screener.html", context)
