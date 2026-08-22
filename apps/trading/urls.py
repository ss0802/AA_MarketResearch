from django.urls import path

from . import views

app_name = "trading"

urlpatterns = [
    path("alerts/", views.alert_list, name="alert_list"),
    path("book/", views.trade_book, name="trade_book"),
    path("api/chart-plan/", views.chart_trade_plan, name="chart_trade_plan"),
    path("", views.trade_list, name="trade_list"),
    path("new/", views.trade_create, name="trade_create"),
    path("<int:pk>/", views.trade_detail, name="trade_detail"),
]
