import json

from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import get_object_or_404, render

from .models import OHLCV, Symbol


def symbol_detail(request, symbol):
    symbol_code = symbol.upper()

    stock = get_object_or_404(
        Symbol,
        symbol=symbol_code,
    )

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