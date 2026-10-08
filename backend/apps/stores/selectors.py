from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import QuerySet

from .models import Store, StoreStatus

MAX_RADIUS_KM = 50


def point_from(lat: float, lon: float) -> Point:
    return Point(lon, lat, srid=4326)  # PostGIS order is (x=lon, y=lat)


def stores_within(
    *, lat: float, lon: float, radius_km: float, store_type: str | None = None, name: str = ""
) -> QuerySet[Store]:
    """Active stores inside the radius, nearest first. Filtering and ordering run in PostGIS."""
    if not 0 < radius_km <= MAX_RADIUS_KM:
        raise ValueError(f"radius_km must be in (0, {MAX_RADIUS_KM}]")
    origin = point_from(lat, lon)
    queryset = (
        Store.objects.filter(status=StoreStatus.ACTIVE, location__dwithin=(origin, D(km=radius_km)))
        .select_related("merchant")
        .annotate(distance=Distance("location", origin))
        .order_by("distance")
    )
    if store_type:
        queryset = queryset.filter(store_type=store_type)
    if name:
        queryset = queryset.filter(name__icontains=name)
    return queryset
