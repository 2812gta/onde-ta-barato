from typing import Any

from django.db import models


class ImmutableRecordError(Exception):
    """Append-only records can be created, never changed or removed."""


class AppendOnlyQuerySet(models.QuerySet[Any]):
    def update(self, **kwargs: Any) -> int:
        raise ImmutableRecordError(f"{self.model.__name__} is append-only")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError(f"{self.model.__name__} is append-only")


class AppendOnlyModel(models.Model):
    """History that must stay trustworthy (audit trail, price observations).

    Corrections are new rows that reference the old one, never edits.
    """

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableRecordError(f"{type(self).__name__} is append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ImmutableRecordError(f"{type(self).__name__} is append-only")
