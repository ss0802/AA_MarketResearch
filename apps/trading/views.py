from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PriceAlertForm, TradeForm
from .models import AlertEvent, AlertWorkerState, PriceAlert, Trade
from .services import capture_trade_setup


def trade_list(request):
    trades = Trade.objects.select_related("symbol").all()
    return render(request, "trading/trade_list.html", {"trades": trades})


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
        "worker": AlertWorkerState.objects.filter(name="tiingo_us").first(),
    })
