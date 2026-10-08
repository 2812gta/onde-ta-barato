import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection

from apps.audit.models import AuditLog
from apps.stores import selectors, services
from apps.stores.models import Store, StoreSource, StoreStatus
from tests.conftest import FORTALEZA, MARACANAU, NEAR


@pytest.mark.django_db
class TestRadiusSelector:
    def test_returns_stores_inside_radius_nearest_first(self, make_store):
        near = make_store(coords=NEAR, name="Perto")
        center = make_store(coords=MARACANAU, name="Centro")
        make_store(coords=FORTALEZA, name="Longe")  # ~18.4 km away
        found = list(selectors.stores_within(lat=MARACANAU[0], lon=MARACANAU[1], radius_km=3))
        assert [s.name for s in found] == ["Centro", "Perto"]
        assert found[0].pk == center.pk and found[1].pk == near.pk

    @pytest.mark.parametrize(("radius", "expected"), [(1, 2), (3, 2), (5, 2), (10, 2), (20, 3)])
    def test_supported_radii(self, make_store, radius, expected):
        make_store(coords=MARACANAU)
        make_store(coords=NEAR)
        make_store(coords=FORTALEZA)
        found = selectors.stores_within(lat=MARACANAU[0], lon=MARACANAU[1], radius_km=radius)
        assert found.count() == expected

    def test_distance_is_in_meters(self, make_store):
        make_store(coords=FORTALEZA)
        store = selectors.stores_within(lat=MARACANAU[0], lon=MARACANAU[1], radius_km=25).get()
        assert 17_000 < store.distance.m < 20_000

    def test_inactive_and_soft_deleted_stores_are_hidden(self, make_store):
        make_store(coords=MARACANAU, status=StoreStatus.INACTIVE)
        gone = make_store(coords=NEAR)
        gone.delete()
        assert not selectors.stores_within(lat=MARACANAU[0], lon=MARACANAU[1], radius_km=5).exists()

    def test_filters_by_type_and_name(self, make_store):
        make_store(coords=NEAR, name="Padaria Doce", store_type="BAKERY")
        make_store(coords=MARACANAU, name="Mercantil Sol", store_type="SUPERMARKET")
        base = {"lat": MARACANAU[0], "lon": MARACANAU[1], "radius_km": 5}
        assert selectors.stores_within(**base, store_type="BAKERY").get().name == "Padaria Doce"
        assert selectors.stores_within(**base, name="sol").get().name == "Mercantil Sol"

    @pytest.mark.parametrize("radius", [0, -1, 51])
    def test_radius_bounds(self, radius):
        with pytest.raises(ValueError):
            selectors.stores_within(lat=0, lon=0, radius_km=radius)

    def test_longitude_latitude_order_is_correct(self, make_store):
        """A swapped (lat, lon) would put Fortaleza in the Atlantic; this guards the order."""
        store = make_store(coords=FORTALEZA)
        assert store.lat == pytest.approx(FORTALEZA[0])
        assert store.lon == pytest.approx(FORTALEZA[1])

    def test_radius_query_uses_the_spatial_index_at_realistic_volume(self, make_store):
        """With a handful of rows PostgreSQL rightly prefers other plans, so load a grid first."""
        from django.contrib.gis.geos import Point

        make_store()
        template = Store.objects.get()
        # ~4,000 stores on a 0.5 km grid across the metropolitan area (a few km per radius query).
        stores = [
            Store(
                name=f"S{i}-{j}",
                location=Point(-38.9 + i * 0.005, -4.1 + j * 0.005, srid=4326),
                merchant=template.merchant,
            )
            for i in range(80)
            for j in range(50)
        ]
        Store.objects.bulk_create(stores)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE stores_store")
        queryset = selectors.stores_within(lat=MARACANAU[0], lon=MARACANAU[1], radius_km=3)
        sql, params = queryset.query.sql_with_params()
        assert "ST_DWithin" in sql
        with connection.cursor() as cursor:
            cursor.execute("EXPLAIN " + sql, params)
            plan = "\n".join(row[0] for row in cursor.fetchall())
        assert "stores_store_location" in plan, plan
        assert "Seq Scan on stores_store" not in plan, plan


@pytest.mark.django_db
class TestStoreServices:
    def test_manager_creates_store_and_it_is_audited(self, make_user, make_merchant):
        owner = make_user()
        merchant = make_merchant(owner=owner)
        store = services.create_store(
            merchant=merchant,
            actor=owner,
            lat=MARACANAU[0],
            lon=MARACANAU[1],
            name="Filial 1",
            city="Maracanaú",
            state="CE",
        )
        assert store.source == StoreSource.MERCHANT
        assert AuditLog.objects.filter(action="store.created", entity_id=str(store.pk)).exists()

    def test_operator_cannot_create_or_edit_stores(self, make_user, make_merchant, make_store):
        from apps.merchants import services as merchant_services

        owner, operator = make_user(), make_user()
        merchant = make_merchant(owner=owner)
        merchant_services.add_member(
            merchant=merchant, actor=owner, email=operator.email, role="MERCHANT_OPERATOR"
        )
        with pytest.raises(PermissionDenied):
            services.create_store(merchant=merchant, actor=operator, lat=0, lon=0, name="X")
        store = make_store(merchant=merchant)
        with pytest.raises(PermissionDenied):
            services.update_store(store=store, actor=operator, name="Y")

    def test_stranger_cannot_create_in_someone_elses_merchant(self, make_user, make_merchant):
        merchant = make_merchant()
        with pytest.raises(PermissionDenied):
            services.create_store(merchant=merchant, actor=make_user(), lat=0, lon=0, name="X")

    def test_unclaimed_seeded_store_cannot_be_edited(self, make_user, make_store):
        store = make_store(merchant=None, source=StoreSource.OPENSTREETMAP)
        store.merchant = None
        with pytest.raises(PermissionDenied):
            services.update_store(store=store, actor=make_user(), name="Meu")

    def test_update_records_previous_and_new_values(self, make_user, make_merchant, make_store):
        owner = make_user()
        merchant = make_merchant(owner=owner)
        store = make_store(merchant=merchant, name="Antigo")
        services.update_store(store=store, actor=owner, name="Novo", lat=NEAR[0], lon=NEAR[1])
        entry = AuditLog.objects.get(action="store.updated")
        assert entry.previous_value["name"] == "Antigo"
        assert entry.new_value["name"] == "Novo"
        assert store.lat == pytest.approx(NEAR[0])

    def test_unknown_fields_are_refused(self, make_user, make_merchant, make_store):
        owner = make_user()
        merchant = make_merchant(owner=owner)
        store = make_store(merchant=merchant)
        with pytest.raises(ValidationError):
            services.update_store(store=store, actor=owner, merchant_id="x")

    def test_lat_and_lon_must_come_together(self, make_user, make_merchant, make_store):
        owner = make_user()
        store = make_store(merchant=make_merchant(owner=owner))
        with pytest.raises(ValidationError):
            services.update_store(store=store, actor=owner, lat=1.0)

    def test_duplicate_external_id_is_blocked_per_source(self, make_store):
        from django.db import IntegrityError, transaction

        make_store(merchant=None, source=StoreSource.OPENSTREETMAP, external_id="node/1")
        with pytest.raises(IntegrityError), transaction.atomic():
            make_store(merchant=None, source=StoreSource.OPENSTREETMAP, external_id="node/1")
        assert Store.objects.count() == 1


@pytest.mark.django_db
class TestStoreApi:
    BODY = {"lat": MARACANAU[0], "lon": MARACANAU[1], "radius_km": 5}

    def test_search_requires_authentication(self, api):
        assert api.post("/api/v1/stores/search/", self.BODY, format="json").status_code == 401

    def test_search_returns_distance_and_hides_unverified_badge(
        self, make_user, login_as, make_store, make_merchant
    ):
        make_store(coords=NEAR, merchant=make_merchant(verified=True, trade_name="Verificado"))
        make_store(coords=MARACANAU, merchant=make_merchant(trade_name="Novo"))
        client = login_as(make_user())
        data = client.post("/api/v1/stores/search/", self.BODY, format="json").json()
        by_name = {s["merchant"]["trade_name"]: s for s in data}
        assert by_name["Verificado"]["merchant"]["is_verified"] is True
        assert by_name["Novo"]["merchant"]["is_verified"] is False
        assert [s["distance_m"] for s in data] == sorted(s["distance_m"] for s in data)
        assert 300 < by_name["Verificado"]["distance_m"] < 700

    def test_default_radius_and_validation(self, make_user, login_as):
        client = login_as(make_user())
        ok = client.post("/api/v1/stores/search/", {"lat": -3.8, "lon": -38.6}, format="json")
        assert ok.status_code == 200
        for bad in (
            {"lat": 91, "lon": 0},
            {"lat": 0, "lon": 181},
            {"lat": 0, "lon": 0, "radius_km": 51},
            {"lat": 0},
            {"lat": "x", "lon": 0},
        ):
            assert client.post("/api/v1/stores/search/", bad, format="json").status_code == 400

    def test_location_is_not_accepted_in_the_url(self, make_user, login_as):
        client = login_as(make_user())
        assert client.get("/api/v1/stores/search/?lat=-3.8&lon=-38.6").status_code == 405

    def test_search_does_not_persist_user_location(self, make_user, login_as, make_store):
        make_store()
        client = login_as(make_user())
        client.post("/api/v1/stores/search/", self.BODY, format="json")
        dumped = " ".join(str(row) for row in AuditLog.objects.values_list("new_value", "metadata"))
        assert str(MARACANAU[0]) not in dumped

    def test_merchant_creates_and_edits_store_over_http(self, make_user, login_as, make_merchant):
        owner = make_user()
        merchant = make_merchant(owner=owner)
        client = login_as(owner)
        created = client.post(
            f"/api/v1/merchants/{merchant.pk}/stores/",
            {
                "name": "Matriz",
                "lat": MARACANAU[0],
                "lon": MARACANAU[1],
                "store_type": "SUPERMARKET",
            },
            format="json",
        )
        assert created.status_code == 201
        sid = created.json()["id"]
        edited = client.patch(f"/api/v1/stores/{sid}/", {"phone": "8533334444"}, format="json")
        assert edited.status_code == 200 and edited.json()["phone"] == "8533334444"

    def test_stranger_gets_403_on_edit(self, make_user, login_as, make_store):
        store = make_store()
        client = login_as(make_user())
        assert (
            client.patch(f"/api/v1/stores/{store.pk}/", {"name": "Hack"}, format="json").status_code
            == 403
        )

    def test_cnpj_cannot_be_changed_after_creation(
        self, make_user, login_as, make_merchant, make_store
    ):
        owner = make_user()
        store = make_store(merchant=make_merchant(owner=owner))
        client = login_as(owner)
        client.patch(f"/api/v1/stores/{store.pk}/", {"cnpj": "11222333000181"}, format="json")
        store.refresh_from_db()
        assert store.cnpj is None
