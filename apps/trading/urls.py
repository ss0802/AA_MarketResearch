from django.urls import path

from . import views

app_name = "trading"

urlpatterns = [
    path("alerts/", views.alert_list, name="alert_list"),
    path("", views.trade_list, name="trade_list"),
    path("new/", views.trade_create, name="trade_create"),
    path("<int:pk>/", views.trade_detail, name="trade_detail"),
]
