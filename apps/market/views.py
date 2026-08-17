import json

from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.db.models import F
from django.shortcuts import get_object_or_404, render

from .models import OHLCV, Symbol, TechnicalSnapshot


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
