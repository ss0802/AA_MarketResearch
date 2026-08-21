from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from apps.trading import views as trading_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "integrations/indstocks/postback/",
        trading_views.indstocks_postback,
        name="indstocks_postback",
    ),
    path("journal/", include("apps.trading.urls")),
    path("", include("apps.market.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
