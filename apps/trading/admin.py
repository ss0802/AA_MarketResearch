from django.contrib import admin

from .models import AlertEvent, PriceAlert, Trade, TradeSetupSnapshot

admin.site.register(PriceAlert)
admin.site.register(AlertEvent)


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("symbol", "side", "status", "entry_at", "entry_price", "quantity")
    list_filter = ("side", "status", "symbol__market")
    search_fields = ("symbol__symbol", "setup_name", "setup_tags")


@admin.register(TradeSetupSnapshot)
class TradeSetupSnapshotAdmin(admin.ModelAdmin):
    list_display = ("trade", "captured_at", "data_as_of_date", "payload_hash")
    readonly_fields = (
        "trade", "captured_at", "data_as_of_date", "technicals", "recent_bars",
        "entry_quality", "screener_context", "calculation_versions", "payload_hash", "chart_image",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
