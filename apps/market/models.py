from django.db import models


class Symbol(models.Model):
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255, blank=True)
    exchange = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=50, blank=True)
    sector = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=150, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]

    def __str__(self):
        return self.symbol




class OHLCV(models.Model):
    class Timeframe(models.TextChoices):
        DAILY = "D", "Daily"
        WEEKLY = "W", "Weekly"
        MONTHLY = "M", "Monthly"

    symbol = models.ForeignKey(
        Symbol,
        on_delete=models.CASCADE,
        related_name="ohlcv",
    )

    timeframe = models.CharField(
        max_length=1,
        choices=Timeframe.choices,
    )

    date = models.DateField()

    open = models.DecimalField(
        max_digits=20,
        decimal_places=6,
    )

    high = models.DecimalField(
        max_digits=20,
        decimal_places=6,
    )

    low = models.DecimalField(
        max_digits=20,
        decimal_places=6,
    )

    close = models.DecimalField(
        max_digits=20,
        decimal_places=6,
    )

    adj_close = models.DecimalField(
        max_digits=20,
        decimal_places=6,
    )

    volume = models.BigIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["symbol", "timeframe", "date"]

        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "timeframe", "date"],
                name="unique_symbol_timeframe_date",
            ),
        ]

        indexes = [
            models.Index(
                fields=["symbol", "timeframe", "-date"],
                name="ohlcv_symbol_tf_date_idx",
            ),
            models.Index(
                fields=["timeframe", "-date"],
                name="ohlcv_tf_date_idx",
            ),
        ]

    def __str__(self):
        return f"{self.symbol.symbol} - {self.timeframe} - {self.date}"