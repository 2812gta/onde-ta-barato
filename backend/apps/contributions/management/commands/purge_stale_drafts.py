from django.core.management.base import BaseCommand

from apps.contributions import services


class Command(BaseCommand):
    help = "Cancel drafts nobody confirmed within 24 h and delete their photos (LGPD retention)."

    def handle(self, *args: object, **options: object) -> None:
        self.stdout.write(f"expired drafts: {services.purge_stale_drafts()}")
