from django.db import models


class Symbol(models.Model):
    class Market(models.TextChoices):
        US = "US", "United States"
        INDIA = "IND", "India"

    symbol = models.CharField(max_length=20)
    market = models.CharField(max_length=3, choices=Market.choices, default=Market.US)
    name = models.CharField(max_length=255, blank=True)
    exchange = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=50, blank=True)
    sector = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=150, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    ipo_date = models.DateField(null=True, blank=True)
    market_cap = models.DecimalField(max_digits=24, decimal_places=2, null=True, blank=True)
    market_cap_category = models.CharField(max_length=20, blank=True)
    index_membership = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["market", "symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["market", "exchange", "symbol"],
                name="unique_market_exchange_symbol",
            ),
        ]
        indexes = [
            models.Index(fields=["market", "is_active"], name="symbol_market_active_idx"),
        ]

    def __str__(self):
        return f"{self.market}:{self.exchange}:{self.symbol}"


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "Running"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    filename = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64, db_index=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-imported_at"]


class Universe(models.Model):
    code = models.CharField(max_length=30, unique=True)
    market = models.CharField(max_length=3, choices=Symbol.Market.choices)
    name = models.CharField(max_length=100)
    definition = models.TextField(blank=True)
    is_ohlcv_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ["market", "code"]

    def __str__(self):
        return self.code


class UniverseMembership(models.Model):
    universe = models.ForeignKey(Universe, on_delete=models.CASCADE, related_name="memberships")
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="universe_memberships")
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="memberships")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["universe", "symbol", "effective_from"],
                name="unique_universe_symbol_effective_from",
            ),
        ]
        indexes = [
            models.Index(
                fields=["universe", "effective_to"],
                name="universe_current_members_idx",
            ),
        ]


class UnresolvedUniverseSymbol(models.Model):
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="unresolved_symbols")
    universe_code = models.CharField(max_length=30)
    symbol = models.CharField(max_length=20)
    reason = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["import_batch", "universe_code", "symbol"],
                name="unique_unresolved_symbol_per_batch",
            ),
        ]


class OHLCVIngestionState(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="ingestion_states")
    provider = models.CharField(max_length=30, default="yahoo")
    timeframe = models.CharField(
        max_length=1,
        choices=[("D", "Daily"), ("W", "Weekly"), ("M", "Monthly")],
        default="D",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_bar_date = models.DateField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "provider", "timeframe"],
                name="unique_symbol_provider_timeframe_state",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "last_attempt_at"], name="ingest_status_attempt_idx"),
        ]




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


class TechnicalSnapshot(models.Model):
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="technical_snapshots")
    timeframe = models.CharField(max_length=1, choices=OHLCV.Timeframe.choices)
    as_of_date = models.DateField()
    price = models.DecimalField(max_digits=20, decimal_places=6)

    sma20 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    sma50 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    sma100 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    sma150 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    sma250 = models.DecimalField(max_digits=20, decimal_places=6, null=True)

    atr14 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    atr_pct = models.DecimalField(max_digits=16, decimal_places=8, null=True)
    adr20 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    adr_pct = models.DecimalField(max_digits=16, decimal_places=8, null=True)

    macd = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    macd_signal = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    momentum = models.CharField(max_length=8, blank=True)

    vwap = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    vwap_status = models.CharField(max_length=8, blank=True)

    adx14 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    trending = models.BooleanField(null=True)
    dmi_plus14 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    dmi_minus14 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    dmi_status = models.CharField(max_length=8, blank=True)

    rsi14 = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    rsi_status = models.CharField(max_length=12, blank=True)

    bb20_upper = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    bb20_middle = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    bb20_lower = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    bb20_width = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    kc20_upper = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    kc20_middle = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    kc20_lower = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    kc20_width = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    bb_kc_ratio = models.DecimalField(max_digits=20, decimal_places=8, null=True)
    is_squeeze = models.BooleanField(null=True)

    calculation_version = models.CharField(max_length=20, default="v1")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "timeframe"],
                name="unique_symbol_timeframe_technical",
            ),
        ]
        indexes = [
            models.Index(fields=["timeframe", "as_of_date"], name="technical_tf_date_idx"),
            models.Index(fields=["timeframe", "momentum"], name="technical_tf_momentum_idx"),
            models.Index(fields=["timeframe", "is_squeeze"], name="technical_tf_squeeze_idx"),
        ]


class ChartDrawing(models.Model):
    class DrawingType(models.TextChoices):
        HORIZONTAL = "HORIZONTAL", "Horizontal level"
        TREND_RAY = "TREND_RAY", "Trend ray"
        PARALLEL_CHANNEL = "PARALLEL_CHANNEL", "Parallel channel"

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name="chart_drawings")
    drawing_type = models.CharField(max_length=20, choices=DrawingType.choices)
    source_timeframe = models.CharField(max_length=1, choices=OHLCV.Timeframe.choices)
    points = models.JSONField(default=list)
    label = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=20, default="#7f56d9")
    line_width = models.PositiveSmallIntegerField(default=2)
    is_visible = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["symbol", "is_visible"], name="drawing_symbol_visible_idx"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        required = {
            self.DrawingType.HORIZONTAL: 1,
            self.DrawingType.TREND_RAY: 2,
            self.DrawingType.PARALLEL_CHANNEL: 3,
        }[self.drawing_type]
        if not isinstance(self.points, list) or len(self.points) != required:
            raise ValidationError({"points": f"{self.get_drawing_type_display()} requires {required} point(s)."})
        for point in self.points:
            if not isinstance(point, dict) or "date" not in point or "price" not in point:
                raise ValidationError({"points": "Each point requires a date and price."})

    def __str__(self):
        return f"{self.symbol.symbol} {self.get_drawing_type_display()}"
