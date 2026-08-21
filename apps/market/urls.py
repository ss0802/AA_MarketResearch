from django.urls import path

from . import views


app_name = "market"


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("data-health/", views.data_health, name="data_health"),
    path("guide/", views.guide, name="guide"),
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
