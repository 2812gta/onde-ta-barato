import os
import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.core import demo_seed


class Command(BaseCommand):
    help = (
        "Create FICTIONAL demo data (Fortaleza): merchants, stores, products, prices, "
        "promotions and demo users. Safe to re-run; refuses to run in production."
    )

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--password",
            help="Password for the demo users (default: random, shown once if users are created)",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".production"):
            raise CommandError("seed_demo never runs with production settings.")
        password = options["password"] or secrets.token_urlsafe(12)
        report = demo_seed.seed(password)
        for what, count in sorted(report.created.items()):
            self.stdout.write(self.style.SUCCESS(f"created  {what}: {count}"))
        for what, count in sorted(report.skipped.items()):
            self.stdout.write(f"existing {what}: {count}")
        if report.new_users:
            self.stdout.write(self.style.WARNING("Demo users (same password for all):"))
            for email in report.new_users:
                self.stdout.write(f"  {email}")
            self.stdout.write(self.style.WARNING(f"Password: {password}"))
        self.stdout.write("All data is fictional. Store coordinates are approximate.")
