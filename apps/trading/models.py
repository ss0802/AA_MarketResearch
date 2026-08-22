from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.market.models import ChartDrawing, Symbol


class Trade(models.Model):
    class Side(models.TextChoices):
        LONG = "LONG", "Long"
        SHORT = "SHORT", "Short"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        STOPPED = "STOPPED", "Stopped out"
        CANCELLED = "CANCELLED", "Cancelled"

    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT, related_name="trades")
    side = models.CharField(max_length=5, choices=Side.choices, default=Side.LONG)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    entry_at = models.DateTimeField()
    entry_price = models.DecimalField(max_digits=20, decimal_places=6)
    quantity = models.PositiveIntegerField()
    stop_price = models.DecimalField(max_digits=20, decimal_places=6)
    current_stop_price = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    target_price = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    exit_at = models.DateTimeField(null=True, blank=True)
    exit_price = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    setup_name = models.CharField(max_length=120, blank=True)
    setup_tags = models.CharField(max_length=300, blank=True)
    thesis = models.TextField(blank=True)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-entry_at"], name="trade_status_entry_idx"),
            models.Index(fields=["symbol", "-entry_at"], name="trade_symbol_entry_idx"),
        ]

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero."})
        if self.side == self.Side.LONG and self.stop_price >= self.entry_price:
            raise ValidationError({"stop_price": "A long trade stop must be below entry."})
        if self.side == self.Side.SHORT and self.stop_price <= self.entry_price:
            raise ValidationError({"stop_price": "A short trade stop must be above entry."})
        if self.status in {self.Status.CLOSED, self.Status.STOPPED}:
            if self.exit_price is None or self.exit_at is None:
                raise ValidationError("Closed trades require an exit price and time.")

    @property
    def risk_per_share(self):
        return abs(self.entry_price - self.stop_price)

    @property
    def planned_risk(self):
        return self.risk_per_share * self.quantity

    @property
    def active_stop_price(self):
        return self.current_stop_price if self.current_stop_price is not None else self.stop_price

    @property
    def gross_pnl(self):
        if self.exit_price is None:
            return None
        direction = Decimal("1") if self.side == self.Side.LONG else Decimal("-1")
        return (self.exit_price - self.entry_price) * self.quantity * direction

    @property
    def net_pnl(self):
        return None if self.gross_pnl is None else self.gross_pnl - self.charges

    @property
    def r_multiple(self):
        if self.net_pnl is None or not self.planned_risk:
            return None
        return self.net_pnl / self.planned_risk

    def __str__(self):
        return f"{self.symbol.market}:{self.symbol.symbol} {self.side} {self.entry_at:%Y-%m-%d}"


class TradeSetupSnapshot(models.Model):
    trade = models.OneToOneField(Trade, on_delete=models.CASCADE, related_name="setup_snapshot")
    captured_at = models.DateTimeField(auto_now_add=True)
    data_as_of_date = models.DateField(null=True, blank=True)
    technicals = models.JSONField(default=dict)
    recent_bars = models.JSONField(default=dict)
    entry_quality = models.JSONField(default=dict)
    screener_context = models.JSONField(default=dict)
    calculation_versions = models.JSONField(default=dict)
    payload_hash = models.CharField(max_length=64, editable=False)
    chart_image = models.FileField(upload_to="trade_snapshots/%Y/%m/", blank=True)

    class Meta:
        ordering = ["-captured_at"]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Trade setup snapshots are immutable.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Snapshot for trade {self.trade_id}"


class TradePositionMark(models.Model):
    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        EOD = "EOD", "End of day"
        LIVE = "LIVE", "Live feed"

    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="position_marks")
    price = models.DecimalField(max_digits=20, decimal_places=6)
    marked_at = models.DateTimeField()
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-marked_at", "-id"]
        indexes = [models.Index(fields=["trade", "-marked_at"], name="position_mark_trade_idx")]


class PriceAlert(models.Model):
    class Role(models.TextChoices):
        ENTRY = "ENTRY", "Entry"
        STOP = "STOP", "Stop-loss"
        TARGET = "TARGET", "Target"

    class Direction(models.TextChoices):
        ABOVE = "ABOVE", "Crosses above"
        BELOW = "BELOW", "Crosses below"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        PAUSED = "PAUSED", "Paused"
        TRIGGERED = "TRIGGERED", "Triggered"
        ARCHIVED = "ARCHIVED", "Archived"

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="price_alerts")
    source_trade = models.ForeignKey(
        Trade, on_delete=models.CASCADE, related_name="price_alerts",
        null=True, blank=True,
    )
    alert_role = models.CharField(max_length=10, choices=Role.choices, blank=True)
    source_drawing = models.ForeignKey(
        ChartDrawing, on_delete=models.PROTECT, related_name="price_alerts",
        null=True, blank=True,
    )
    drawing_component = models.CharField(max_length=20, blank=True)
    direction = models.CharField(max_length=5, choices=Direction.choices)
    target_price = models.DecimalField(max_digits=20, decimal_places=6)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notify_in_app = models.BooleanField(default=True)
    notify_telegram = models.BooleanField(default=True)
    notify_desktop = models.BooleanField(default=True)
    notify_sound = models.BooleanField(default=True)
    last_price = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    last_quote_at = models.DateTimeField(null=True, blank=True)
    triggered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "symbol__market", "symbol__symbol"]

    def __str__(self):
        return f"{self.symbol.market}:{self.symbol.symbol} {self.direction} {self.target_price}"

    def rearm(self):
        self.status = self.Status.ACTIVE
        self.is_active = True
        self.last_price = None
        self.last_quote_at = None
        self.triggered_at = None
        self.save(update_fields=["status", "is_active", "last_price", "last_quote_at", "triggered_at"])


class AlertEvent(models.Model):
    alert = models.ForeignKey(PriceAlert, on_delete=models.CASCADE, related_name="events")
    price = models.DecimalField(max_digits=20, decimal_places=6)
    quote_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    telegram_status = models.CharField(max_length=20, default="NOT_REQUESTED")
    telegram_error = models.TextField(blank=True)
    desktop_status = models.CharField(max_length=20, default="NOT_REQUESTED")
    desktop_error = models.TextField(blank=True)
    sound_status = models.CharField(max_length=20, default="NOT_REQUESTED")
    sound_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class AlertWorkerState(models.Model):
    name = models.CharField(max_length=30, unique=True, default="tiingo_us")
    status = models.CharField(max_length=20, default="STOPPED")
    connected_at = models.DateTimeField(null=True, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_quote_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
