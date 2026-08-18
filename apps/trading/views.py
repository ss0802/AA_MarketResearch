from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PriceAlertForm, TradeForm
from .models import AlertEvent, PriceAlert, Trade
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
    if request.method == "POST" and request.POST.get("toggle"):
        alert = get_object_or_404(PriceAlert, pk=request.POST["toggle"])
        alert.is_active = not alert.is_active
        alert.save(update_fields=["is_active"])
        return redirect("trading:alert_list")
    form = PriceAlertForm(request.POST or None)
    if request.method == "POST" and not request.POST.get("toggle") and form.is_valid():
        form.save()
        messages.success(request, "Price alert saved.")
        return redirect("trading:alert_list")
    return render(request, "trading/alert_list.html", {
        "form": form,
        "alerts": PriceAlert.objects.select_related("symbol"),
        "events": AlertEvent.objects.select_related("alert__symbol")[:25],
    })
