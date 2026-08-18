from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import TradeForm
from .models import Trade
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
