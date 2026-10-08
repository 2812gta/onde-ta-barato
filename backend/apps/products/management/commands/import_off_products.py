import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.products import openfoodfacts as off


class Command(BaseCommand):
    help = "Seed the catalog from Open Food Facts (ODbL): by GTIN list or Brazil search term."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument("--gtin", nargs="*", default=[], help="One or more EAN/GTIN codes")
        parser.add_argument("--search", help="Search term (Brazil products only)")
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--file", help="JSON file with a list of OFF product objects")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        raw: list[dict] = []
        if options["file"]:
            raw = json.loads(Path(options["file"]).read_text(encoding="utf-8"))
        for code in options["gtin"]:
            product = off.fetch_by_gtin(code)
            if product is None:
                self.stdout.write(self.style.WARNING(f"{code}: not found"))
            else:
                raw.append(product)
        if options["search"]:
            raw += off.search(options["search"], options["limit"])
        if not raw:
            raise CommandError("Nothing to import: use --gtin, --search or --file.")
        records = [r for r in (off.parse(p) for p in raw) if r is not None]
        self.stdout.write(
            f"{len(records)} usable of {len(raw)} (skipped: invalid GTIN/name/quantity)"
        )
        if options["dry_run"]:
            for record in records[:10]:
                detail = f"{record.name} | {record.brand} | {record.quantity} {record.unit}"
                self.stdout.write(f"  {record.gtin}  {detail}")
            self.stdout.write(self.style.WARNING("Dry run: nothing written."))
            return
        self.stdout.write(self.style.SUCCESS(f"Done: {off.import_products(records)}"))
        self.stdout.write("Attribution required: Open Food Facts contributors (ODbL).")
