"""Proves the whole geo stack the M2 stores/radius queries will rely on.

Reference points (lon, lat): Maracanaú center and Fortaleza (Praça do Ferreira).
"""

import pytest
from django.contrib.gis.gdal import CoordTransform, SpatialReference
from django.contrib.gis.geos import Point
from django.db import connection

MARACANAU = "SRID=4326;POINT(-38.6256 -3.8767)"
FORTALEZA = "SRID=4326;POINT(-38.5434 -3.7319)"


def scalar(sql: str, params: list | None = None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchone()[0]


@pytest.mark.django_db
class TestPostgis:
    def test_extension_is_available(self):
        assert scalar("SELECT PostGIS_Lib_Version()").startswith("3.")

    def test_engine_is_postgis(self):
        assert connection.vendor == "postgresql"
        assert "postgis" in connection.settings_dict["ENGINE"]

    def test_geography_distance_is_in_meters(self):
        meters = scalar("SELECT ST_Distance(%s::geography, %s::geography)", [MARACANAU, FORTALEZA])
        assert 17_000 < meters < 20_000  # ~18.4 km

    def test_radius_query_uses_st_dwithin(self):
        sql = "SELECT ST_DWithin(%s::geography, %s::geography, %s)"
        assert scalar(sql, [MARACANAU, FORTALEZA, 20_000]) is True  # 20 km radius
        assert scalar(sql, [MARACANAU, FORTALEZA, 5_000]) is False  # 5 km radius

    def test_gist_index_can_be_used_for_radius_queries(self):
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE probe (id serial, location geography(Point, 4326))")
            cursor.execute("CREATE INDEX probe_gix ON probe USING GIST (location)")
            cursor.execute(
                "INSERT INTO probe (location) SELECT ST_SetSRID(ST_MakePoint(-38.5 - i/1000.0, "
                "-3.7 - i/1000.0), 4326)::geography FROM generate_series(1, 2000) AS i"
            )
            cursor.execute("ANALYZE probe")
            cursor.execute("SET LOCAL enable_seqscan = off")
            cursor.execute(
                "EXPLAIN SELECT id FROM probe WHERE ST_DWithin(location, %s::geography, 3000)",
                [FORTALEZA],
            )
            plan = "\n".join(row[0] for row in cursor.fetchall())
        assert "probe_gix" in plan


class TestGeoDjangoLibraries:
    """GDAL/GEOS/PROJ must load (Windows: from the PostGIS bundle; Linux: system)."""

    def test_geos_point(self):
        point = Point(-38.5434, -3.7319, srid=4326)
        assert point.srid == 4326
        assert point.wkt.startswith("POINT")

    def test_proj_transform_to_sirgas2000_utm_24s(self):
        point = Point(-38.5434, -3.7319, srid=4326)
        transform = CoordTransform(SpatialReference(4326), SpatialReference(31984))
        projected = point.transform(transform, clone=True)
        assert 540_000 < projected.x < 560_000  # Fortaleza easting
        assert 9_580_000 < projected.y < 9_600_000  # Fortaleza northing
