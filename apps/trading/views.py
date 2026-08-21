from django.contrib import messages
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import PriceAlertForm, TradeForm
from .models import AlertEvent, AlertWorkerState, PriceAlert, Trade, TradePositionMark
from .services import capture_trade_setup


@csrf_exempt
@require_http_methods(["GET", "POST"])
def indstocks_postback(request):
    if request.method == "GET":
        return JsonResponse({
            "status": "available",
            "provider": "INDstocks",
            "order_processing": "disabled",
        })
    # Registration-safe placeholder: deliberately no payload storage or action.
    return JsonResponse({
        "status": "accepted",
        "order_processing": "disabled",
    }, status=202)


def trade_list(request):
    trades = Trade.objects.select_related("symbol").all()
    return render(request, "trading/trade_list.html", {"trades": trades})


def trade_book(request):
    if request.method == "POST":
        trade = get_object_or_404(Trade, pk=request.POST.get("trade_id"), status=Trade.Status.OPEN)
        try:
            if request.POST.get("current_stop"):
                current_stop = Decimal(request.POST["current_stop"])
                if current_stop <= 0:
                    raise ValueError("Stop must be positive.")
                trade.current_stop_price = current_stop
                trade.save(update_fields=["current_stop_price", "updated_at"])
            if request.POST.get("mark_price"):
                mark_price = Decimal(request.POST["mark_price"])
                if mark_price <= 0:
                    raise ValueError("Price must be positive.")
                TradePositionMark.objects.create(
                    trade=trade, price=mark_price, marked_at=timezone.now(),
                    source=TradePositionMark.Source.MANUAL,
                )
            messages.success(request, "Open position updated.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter valid positive prices.")
        return redirect("trading:trade_book")

    positions = list(
        Trade.objects.filter(status=Trade.Status.OPEN)
        .select_related("symbol").prefetch_related("position_marks")
    )
    for trade in positions:
        mark = trade.position_marks.first()
        if mark is None:
            candle = trade.symbol.ohlcv.filter(timeframe="D").order_by("-date").first()
            if candle:
                trade.monitor_price = candle.close
                trade.monitor_time = candle.date
                trade.monitor_source = "EOD"
        else:
            trade.monitor_price = mark.price
            trade.monitor_time = mark.marked_at
            trade.monitor_source = mark.get_source_display()
        if hasattr(trade, "monitor_price"):
            direction = Decimal("1") if trade.side == Trade.Side.LONG else Decimal("-1")
            trade.unrealized_pnl = (trade.monitor_price - trade.entry_price) * trade.quantity * direction
            trade.open_r = trade.unrealized_pnl / trade.planned_risk if trade.planned_risk else None
            trade.return_pct = ((trade.monitor_price - trade.entry_price) / trade.entry_price * 100) * direction
            stop_pnl = (trade.active_stop_price - trade.entry_price) * trade.quantity * direction
            trade.stop_r = stop_pnl / trade.planned_risk if trade.planned_risk else None
    return render(request, "trading/trade_book.html", {"positions": positions})


def trade_create(request):
    form = TradeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            trade = form.save()
            capture_trade_setup(
                trade, form.cleaned_data.get("screener_filters", ""),
                form.cleaned_data.get("chart_image"),
            )
        messages.success(request, "Trade saved and its setup snapshot was frozen.")
        return redirect("trading:trade_detail", pk=trade.pk)
    return render(request, "trading/trade_form.html", {"form": form})


def trade_detail(request, pk):
    trade = get_object_or_404(Trade.objects.select_related("symbol"), pk=pk)
    return render(request, "trading/trade_detail.html", {"trade": trade})


def alert_list(request):
    if request.method == "POST" and request.POST.get("alert_id"):
        alert = get_object_or_404(PriceAlert, pk=request.POST["alert_id"])
        action = request.POST.get("action")
        if action == "pause":
            alert.status, alert.is_active = PriceAlert.Status.PAUSED, False
            alert.save(update_fields=["status", "is_active"])
        elif action == "rearm":
            alert.rearm()
        elif action == "archive":
            alert.status, alert.is_active = PriceAlert.Status.ARCHIVED, False
            alert.save(update_fields=["status", "is_active"])
        return redirect("trading:alert_list")
    form = PriceAlertForm(request.POST or None)
    if request.method == "POST" and not request.POST.get("alert_id") and form.is_valid():
        form.save()
        messages.success(request, "Price alert saved.")
        return redirect("trading:alert_list")
    return render(request, "trading/alert_list.html", {
        "form": form,
        "alerts": PriceAlert.objects.select_related("symbol").exclude(status=PriceAlert.Status.ARCHIVED),
        "events": AlertEvent.objects.select_related("alert__symbol")[:25],
        "us_worker": AlertWorkerState.objects.filter(name="tiingo_us").first(),
        "ind_worker": AlertWorkerState.objects.filter(name="indstocks_ind").first(),
    })
