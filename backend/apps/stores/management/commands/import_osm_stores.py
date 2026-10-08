import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.stores import osm


class Command(BaseCommand):
    help = "Seed stores from OpenStreetMap (ODbL). Default area: Fortaleza metropolitan region."

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--bbox",
            help="south,west,north,east (default: Fortaleza metro area)",
        )
        parser.add_argument("--file", help="Read an Overpass JSON file instead of calling the API")
        parser.add_argument(
            "--dry-run", action="store_true", help="Parse and report, write nothing"
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        bbox = osm.DEFAULT_BBOX
        if options["bbox"]:
            try:
                parts = [float(v) for v in options["bbox"].split(",")]
                if len(parts) != 4:
                    raise ValueError("expected 4 numbers")
                bbox = (parts[0], parts[1], parts[2], parts[3])
            except ValueError as exc:
                raise CommandError("--bbox must be 'south,west,north,east'") from exc
        if options["file"]:
            payload = json.loads(Path(options["file"]).read_text(encoding="utf-8"))
        else:
            self.stdout.write(f"Querying Overpass for bbox {bbox} ...")
            try:
                payload = osm.fetch(bbox)
            except osm.OverpassError as exc:
                raise CommandError(f"{exc}\nTip: retry later or pass a smaller --bbox.") from exc
        records = osm.parse(payload)
        skipped = len(payload.get("elements", [])) - len(records)
        self.stdout.write(
            f"{len(records)} usable stores ({skipped} skipped: no name/coordinate/type)"
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing written."))
            return
        result = osm.import_stores(records)
        self.stdout.write(self.style.SUCCESS(f"Done: {result}"))
        self.stdout.write("Attribution required: © OpenStreetMap contributors (ODbL).")
