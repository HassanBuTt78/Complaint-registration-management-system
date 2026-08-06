from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("new/", views.complaint_create, name="create"),
    path("<int:pk>/", views.complaint_detail, name="detail"),
    path("<int:pk>/edit/", views.complaint_edit, name="edit"),
    path("<int:pk>/cancel/", views.complaint_cancel, name="cancel"),
    path("<int:pk>/status/", views.complaint_status_update, name="status"),
    path("<int:pk>/assign/", views.complaint_assign, name="assign"),
    path("<int:pk>/remark/", views.complaint_add_remark, name="remark"),
    path("attachment/<int:pk>/", views.attachment_download, name="attachment"),
    path("api/suggest/", views.categorize_suggest, name="suggest"),
]
