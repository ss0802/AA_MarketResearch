from django.urls import path

from . import views


app_name = "market"


urlpatterns = [
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
