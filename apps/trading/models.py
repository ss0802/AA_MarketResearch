from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.market.models import Symbol


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
