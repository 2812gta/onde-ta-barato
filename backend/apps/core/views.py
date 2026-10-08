from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness plus database check. Reveals no internal details."""

    permission_classes = [permissions.AllowAny]
    authentication_classes: list[type] = []
    throttle_classes: list[type] = []

    @extend_schema(exclude=True)
    def get(self, request: Request) -> Response:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            return Response({"status": "unavailable"}, status=503)
        return Response({"status": "ok"})
