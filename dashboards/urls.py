from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.home, name="home"),
    path("student/", views.student_dashboard, name="student"),
    path("hod/", views.hod_dashboard, name="hod"),
    path("admin/", views.admin_dashboard, name="admin"),
    path("analytics/", views.analytics, name="analytics"),
    path("reports/", views.reports, name="reports"),
    path("complaints/<int:pk>/unmask/", views.unmask, name="unmask"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/toggle/", views.user_toggle_active, name="user_toggle"),
    path("departments/", views.department_list, name="departments"),
    path("activity/", views.activity_log, name="activity"),
]
