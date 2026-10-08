from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models import Q

from apps.core.models import SoftDeleteModel, TimeStampedModel


class StoreType(models.TextChoices):
    SUPERMARKET = "SUPERMARKET", "Supermercado"
    MINIMARKET = "MINIMARKET", "Mercadinho"
    WHOLESALE = "WHOLESALE", "Atacado"
    BAKERY = "BAKERY", "Padaria"
    BUTCHER = "BUTCHER", "Açougue"
    GREENGROCER = "GREENGROCER", "Hortifruti"
    PHARMACY = "PHARMACY", "Farmácia"
    OTHER = "OTHER", "Outro"


class StoreStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Ativa"
    INACTIVE = "INACTIVE", "Inativa"


class StoreSource(models.TextChoices):
    MERCHANT = "MERCHANT", "Comerciante"
    OPENSTREETMAP = "OPENSTREETMAP", "OpenStreetMap"
    USER = "USER", "Usuário"


class Store(TimeStampedModel, SoftDeleteModel):
    # Null for stores seeded from open data that no merchant has claimed yet.
    merchant = models.ForeignKey(
        "merchants.Merchant", null=True, blank=True, on_delete=models.PROTECT, related_name="stores"
    )
    name = models.CharField(max_length=200)
    store_type = models.CharField(max_length=20, choices=StoreType.choices, default=StoreType.OTHER)
    cnpj = models.CharField(max_length=14, null=True, blank=True)
    street = models.CharField(max_length=200, blank=True)
    number = models.CharField(max_length=20, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, blank=True)
    postal_code = models.CharField(max_length=8, blank=True)
    # geography: distances and radius queries are in meters, computed by PostGIS.
    location = gis_models.PointField(geography=True, srid=4326)
    phone = models.CharField(max_length=30, blank=True)
    opening_hours = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=10, choices=StoreStatus.choices, default=StoreStatus.ACTIVE
    )
    source = models.CharField(
        max_length=20, choices=StoreSource.choices, default=StoreSource.MERCHANT
    )
    external_id = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~Q(external_id="") & Q(deleted_at__isnull=True),
                name="store_unique_alive_external_id",
            )
        ]
        indexes = [models.Index(fields=["status", "store_type"])]

    def __str__(self) -> str:
        return self.name

    @property
    def lat(self) -> float:
        return self.location.y

    @property
    def lon(self) -> float:
        return self.location.x
