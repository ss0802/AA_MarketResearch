from django.contrib import admin

from .models import ChartDrawing


@admin.register(ChartDrawing)
class ChartDrawingAdmin(admin.ModelAdmin):
    list_display = ("symbol", "drawing_type", "source_timeframe", "label", "is_visible", "is_locked")
    list_filter = ("drawing_type", "source_timeframe", "is_visible", "is_locked")
    search_fields = ("symbol__symbol", "label")

# Register your models here.
