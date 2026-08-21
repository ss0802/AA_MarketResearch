import os
from decimal import Decimal

import requests
from django.utils import timezone

from .models import AlertEvent, PriceAlert


def process_quote(symbol_code, price, quote_at=None, market="US"):
    price = Decimal(str(price))
    quote_at = quote_at or timezone.now()
    triggered = []
    for alert in PriceAlert.objects.select_related("symbol").filter(
        is_active=True, status=PriceAlert.Status.ACTIVE,
        symbol__market=market, symbol__symbol=symbol_code.upper()
    ):
        previous = alert.last_price
        crossed = previous is not None and (
            (alert.direction == PriceAlert.Direction.ABOVE and previous < alert.target_price <= price)
            or (alert.direction == PriceAlert.Direction.BELOW and previous > alert.target_price >= price)
        )
        alert.last_price = price
        alert.last_quote_at = quote_at
        if crossed:
            alert.is_active = False
            alert.status = PriceAlert.Status.TRIGGERED
            alert.triggered_at = timezone.now()
        alert.save(update_fields=["last_price", "last_quote_at", "is_active", "status", "triggered_at"])
        if crossed:
            event = AlertEvent.objects.create(alert=alert, price=price, quote_at=quote_at)
            if alert.notify_telegram:
                _send_telegram(event)
            if alert.notify_desktop:
                _send_desktop(event)
            if alert.notify_sound:
                _play_sound(event)
            triggered.append(event)
    return triggered


def _send_telegram(event):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        event.telegram_status = "NOT_CONFIGURED"
    else:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"PRICE ALERT: {event.alert.symbol.symbol} {event.alert.get_direction_display()} {event.alert.target_price}; latest {event.price}"},
                timeout=20,
            )
            response.raise_for_status()
            event.telegram_status = "SENT"
        except Exception as exc:
            event.telegram_status = "FAILED"
            event.telegram_error = str(exc)[:1000]
    event.save(update_fields=["telegram_status", "telegram_error"])


def _message(event):
    return f"{event.alert.symbol.symbol} {event.alert.get_direction_display()} {event.alert.target_price}; latest {event.price}"


def _send_desktop(event):
    try:
        from winotify import Notification
        Notification(app_id="AA MarketResearch Alerts", title="Price alert triggered", msg=_message(event), duration="long").show()
        event.desktop_status = "SENT"
    except Exception as exc:
        event.desktop_status = "FAILED"
        event.desktop_error = str(exc)[:1000]
    event.save(update_fields=["desktop_status", "desktop_error"])


def _play_sound(event):
    try:
        import time
        import winsound

        winsound.Beep(1200, 500)
        time.sleep(0.12)
        winsound.Beep(1600, 500)
        time.sleep(0.12)
        winsound.Beep(1200, 700)
        event.sound_status = "PLAYED"
    except Exception as exc:
        event.sound_status = "FAILED"
        event.sound_error = str(exc)[:1000]
    event.save(update_fields=["sound_status", "sound_error"])
