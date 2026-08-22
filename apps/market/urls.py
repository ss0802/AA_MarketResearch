from django.urls import path

from . import views


app_name = "market"


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("data-health/", views.data_health, name="data_health"),
    path("guide/", views.guide, name="guide"),
    path("market-condition/<str:market>/", views.market_condition, name="market_condition"),
    path("api/watchlist/", views.watchlist_api, name="watchlist_api"),
    path("api/watchlist/<int:item_id>/", views.watchlist_item_api, name="watchlist_item_api"),
    path("api/ticker-quotes/", views.ticker_quotes_api, name="ticker_quotes_api"),
    path(
        "api/symbols/<int:symbol_id>/drawings/",
        views.chart_drawings,
        name="chart_drawings",
    ),
    path(
        "api/drawings/<int:drawing_id>/",
        views.chart_drawing_detail,
        name="chart_drawing_detail",
    ),
    path(
        "api/drawings/<int:drawing_id>/alert/",
        views.chart_drawing_alert,
        name="chart_drawing_alert",
    ),
    path(
        "technicals/",
        views.technical_screener,
        name="technical_screener",
    ),
    path(
        "stocks/<str:symbol>/",
        views.symbol_detail,
        name="symbol_detail",
    ),
]
