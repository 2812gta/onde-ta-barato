from django.db import migrations

# (name, slug, price_ttl_hours) - how long a price stays "current" per category.
CATEGORIES = [
    ("Hortifruti", "hortifruti", 48),
    ("Carnes e frios", "carnes-e-frios", 72),
    ("Padaria", "padaria", 72),
    ("Laticínios", "laticinios", 120),
    ("Congelados", "congelados", 168),
    ("Bebidas", "bebidas", 240),
    ("Mercearia", "mercearia", 240),
    ("Limpeza", "limpeza", 336),
    ("Higiene pessoal", "higiene-pessoal", 336),
    ("Bebê", "bebe", 336),
    ("Pet", "pet", 336),
    ("Outros", "outros", 168),
]


def seed(apps, schema_editor):
    Category = apps.get_model("products", "Category")
    for name, slug, ttl in CATEGORIES:
        # Idempotent and non-destructive: an operator-tuned TTL is never overwritten.
        Category.objects.get_or_create(slug=slug, defaults={"name": name, "price_ttl_hours": ttl})


def unseed(apps, schema_editor):
    apps.get_model("products", "Category").objects.filter(
        slug__in=[slug for _, slug, _ in CATEGORIES], products__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("products", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
