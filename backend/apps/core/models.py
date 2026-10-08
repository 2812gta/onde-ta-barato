import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """UUID primary key (non-enumerable ids) plus audit timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet["SoftDeleteModel"]):
    def delete(self) -> tuple[int, dict[str, int]]:
        count = self.update(deleted_at=timezone.now())
        return count, {self.model._meta.label: count}

    def alive(self) -> "SoftDeleteQuerySet":
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> "SoftDeleteQuerySet":
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager["SoftDeleteModel"]):
    """Default manager hides soft-deleted rows. Use `all_objects` to see them."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    """Commercial history must never vanish silently: delete marks, does not remove."""

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager["SoftDeleteModel"]()

    class Meta:
        abstract = True

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:  # type: ignore[override]
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
        return 1, {self._meta.label: 1}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        return super().delete()
