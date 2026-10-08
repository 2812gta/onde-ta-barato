import pytest
from django.db import connection, models

from apps.core.models import SoftDeleteModel, TimeStampedModel


class Widget(TimeStampedModel, SoftDeleteModel):
    name = models.CharField(max_length=20)

    class Meta:
        app_label = "core"


@pytest.fixture
def widget_table(db):
    # `core` has no migrations, so Django may already have synced this test-only table.
    created = Widget._meta.db_table not in connection.introspection.table_names()
    if created:
        with connection.schema_editor() as editor:
            editor.create_model(Widget)
    yield
    if created:
        with connection.schema_editor() as editor:
            editor.delete_model(Widget)


def test_delete_marks_instead_of_removing(widget_table):
    widget = Widget.objects.create(name="a")
    widget.delete()
    assert Widget.objects.count() == 0
    assert Widget.all_objects.count() == 1
    assert Widget.all_objects.get().deleted_at is not None


def test_queryset_delete_is_soft(widget_table):
    Widget.objects.create(name="a")
    Widget.objects.create(name="b")
    Widget.objects.all().delete()
    assert Widget.objects.count() == 0
    assert Widget.all_objects.count() == 2


def test_hard_delete_removes_row(widget_table):
    widget = Widget.objects.create(name="a")
    widget.hard_delete()
    assert Widget.all_objects.count() == 0
