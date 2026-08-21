from django.contrib import admin

from .models import ChartDrawing, ProviderInstrument


@admin.register(ProviderInstrument)
class ProviderInstrumentAdmin(admin.ModelAdmin):
    list_display = ("symbol", "provider", "exchange_code", "instrument_id", "updated_at")
    list_filter = ("provider", "exchange_code", "segment")
    search_fields = ("symbol__symbol", "instrument_id")


@admin.register(ChartDrawing)
class ChartDrawingAdmin(admin.ModelAdmin):
    list_display = ("symbol", "drawing_type", "source_timeframe", "label", "is_visible", "is_locked")
    list_filter = ("drawing_type", "source_timeframe", "is_visible", "is_locked")
    search_fields = ("symbol__symbol", "label")

# Register your models here.
