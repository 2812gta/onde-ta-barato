from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Domain services raise Django's ValidationError; expose it as a normal 400."""
    if isinstance(exc, DjangoValidationError):
        exc = serializers.ValidationError(detail=exc.messages)
    return drf_exception_handler(exc, context)


def parse_coordinates(lat: float, lon: float) -> tuple[float, float]:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise serializers.ValidationError("Coordenadas fora do intervalo válido.")
    return lat, lon


class GeoQuerySerializer(serializers.Serializer):
    """Location comes in the POST body, never the URL, so it stays out of access logs."""

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    radius_km = serializers.FloatField(min_value=0.1, max_value=50, default=5)
