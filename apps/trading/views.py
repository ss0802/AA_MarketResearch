from django.contrib import messages
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
import json

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


@require_http_methods(["POST"])
def chart_trade_plan(request):
    from apps.market.models import ChartDrawing, Symbol

    try:
        payload = json.loads(request.body or "{}")
        symbol = get_object_or_404(Symbol, pk=payload.get("symbol_id"))
        side = str(payload.get("side", Trade.Side.LONG)).upper()
        if side not in Trade.Side.values:
            raise ValueError("Side must be LONG or SHORT.")
        entry = Decimal(str(payload["entry_price"]))
        stop = Decimal(str(payload["stop_price"]))
        if entry <= 0 or stop <= 0 or entry == stop:
            raise ValueError("Entry and stop must be positive and different.")
        risk_per_share = abs(entry - stop)
        maximum_risk = Decimal(str(payload.get("maximum_risk") or "0"))
        quantity = int(payload.get("quantity") or 0)
        if quantity <= 0 and maximum_risk > 0:
            quantity = int(maximum_risk / risk_per_share)
        if quantity <= 0:
            raise ValueError("Enter a quantity or a maximum-risk amount large enough for one share.")
        target_r = Decimal(str(payload.get("target_r") or "3"))
        if target_r <= 0:
            raise ValueError("Target R must be positive.")
        direction = Decimal("1") if side == Trade.Side.LONG else Decimal("-1")
        target = entry + direction * risk_per_share * target_r
        drawing_ids = [value for value in (payload.get("entry_drawing_id"), payload.get("stop_drawing_id")) if value]
        drawing_objects = {
            drawing.id: drawing for drawing in ChartDrawing.objects.filter(pk__in=drawing_ids, symbol=symbol)
        }
        drawings = list(drawing_objects)
        source_context = "\n".join([
            f"Chart timeframe: {str(payload.get('timeframe') or 'D')[:1]}",
            f"Source page: {str(payload.get('source_url') or '')[:500]}",
            f"Linked drawing IDs: {','.join(map(str, drawings)) or 'none'}",
        ])
        with transaction.atomic():
            trade = Trade(
                symbol=symbol, side=side, status=Trade.Status.PLANNED,
                entry_at=timezone.now(), entry_price=entry, quantity=quantity,
                stop_price=stop, target_price=target,
                setup_name=str(payload.get("setup_name") or "Chart plan")[:120],
                setup_tags=str(payload.get("setup_tags") or "")[:300],
                thesis=str(payload.get("thesis") or ""),
            )
            trade.full_clean()
            trade.save()
            capture_trade_setup(trade, source_context)
            requested_alerts = {
                PriceAlert.Role.ENTRY: bool(payload.get("create_entry_alert")),
                PriceAlert.Role.STOP: bool(payload.get("create_stop_alert")),
                PriceAlert.Role.TARGET: bool(payload.get("create_target_alert")),
            }
            directions = {
                PriceAlert.Role.ENTRY: PriceAlert.Direction.ABOVE if side == Trade.Side.LONG else PriceAlert.Direction.BELOW,
                PriceAlert.Role.STOP: PriceAlert.Direction.BELOW if side == Trade.Side.LONG else PriceAlert.Direction.ABOVE,
                PriceAlert.Role.TARGET: PriceAlert.Direction.ABOVE if side == Trade.Side.LONG else PriceAlert.Direction.BELOW,
            }
            prices = {
                PriceAlert.Role.ENTRY: entry,
                PriceAlert.Role.STOP: stop,
                PriceAlert.Role.TARGET: target,
            }
            alert_ids = []
            entry_is_staging = requested_alerts[PriceAlert.Role.ENTRY]
            for role, requested in requested_alerts.items():
                if not requested:
                    continue
                staged = entry_is_staging and role != PriceAlert.Role.ENTRY
                drawing_id = payload.get("entry_drawing_id") if role == PriceAlert.Role.ENTRY else payload.get("stop_drawing_id") if role == PriceAlert.Role.STOP else None
                alert = PriceAlert.objects.create(
                    symbol=symbol, source_trade=trade, alert_role=role,
                    source_drawing=drawing_objects.get(int(drawing_id)) if drawing_id else None,
                    drawing_component=role if drawing_id else "",
                    direction=directions[role], target_price=prices[role],
                    is_active=not staged,
                    status=PriceAlert.Status.PAUSED if staged else PriceAlert.Status.ACTIVE,
                )
                alert_ids.append(alert.id)
        return JsonResponse({
            "trade_id": trade.id, "quantity": quantity, "planned_risk": str(trade.planned_risk),
            "target_price": str(target), "alert_ids": alert_ids, "detail_url": f"/journal/{trade.id}/",
        }, status=201)
    except (KeyError, InvalidOperation, TypeError, ValueError, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=400)


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
    if request.method == "POST" and request.POST.get("action") == "create_plan_alerts":
        long_side = trade.side == Trade.Side.LONG
        definitions = [
            (PriceAlert.Role.ENTRY, PriceAlert.Direction.ABOVE if long_side else PriceAlert.Direction.BELOW, trade.entry_price, True),
            (PriceAlert.Role.STOP, PriceAlert.Direction.BELOW if long_side else PriceAlert.Direction.ABOVE, trade.stop_price, False),
        ]
        if trade.target_price is not None:
            definitions.append((
                PriceAlert.Role.TARGET,
                PriceAlert.Direction.ABOVE if long_side else PriceAlert.Direction.BELOW,
                trade.target_price, False,
            ))
        created_count = 0
        with transaction.atomic():
            for role, direction, price, active in definitions:
                _, created = PriceAlert.objects.get_or_create(
                    source_trade=trade, alert_role=role,
                    defaults={
                        "symbol": trade.symbol, "direction": direction, "target_price": price,
                        "is_active": active,
                        "status": PriceAlert.Status.ACTIVE if active else PriceAlert.Status.PAUSED,
                    },
                )
                created_count += int(created)
        messages.success(request, f"Created {created_count} plan alert(s). Stop and target wait for entry.")
        return redirect("trading:trade_detail", pk=trade.pk)
    plan_alerts = trade.price_alerts.exclude(status=PriceAlert.Status.ARCHIVED)
    return render(request, "trading/trade_detail.html", {"trade": trade, "plan_alerts": plan_alerts})


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
        "yahoo_worker": AlertWorkerState.objects.filter(name="yahoo_us_delayed").first(),
        "ind_worker": AlertWorkerState.objects.filter(name="indstocks_ind").first(),
    })
