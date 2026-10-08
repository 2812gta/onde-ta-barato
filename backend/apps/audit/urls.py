from django.urls import path

from .api import AuditLogListView

urlpatterns = [path("logs/", AuditLogListView.as_view(), name="audit-logs")]
