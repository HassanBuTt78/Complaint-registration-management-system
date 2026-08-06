"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

handler403 = "config.views.permission_denied"
handler404 = "config.views.page_not_found"
handler500 = "config.views.server_error"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboards:home", permanent=False)),
    path("dashboard/", include("dashboards.urls")),
    path("complaints/", include("complaints.urls")),
    path("accounts/", include("accounts.urls")),
    path("django-admin/", admin.site.urls),
]

# Static files are served by WhiteNoise in every environment; media is served
# exclusively through the permission-checked `complaints:attachment` view, so it
# is deliberately *not* exposed here.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

admin.site.site_header = "OCR Portal Administration"
admin.site.site_title = "OCR Portal"
admin.site.index_title = "System administration"
