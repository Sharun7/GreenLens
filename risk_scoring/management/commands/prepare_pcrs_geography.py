"""Install the public coastline dataset used for PCRS geographic features."""

from django.core.management.base import BaseCommand, CommandError

from risk_scoring.geography import download_coastline


class Command(BaseCommand):
    help = "Download Natural Earth 1:50m coastline data for local, offline PCRS features"

    def handle(self, *args, **options):
        try:
            status = download_coastline()
        except Exception as error:
            raise CommandError(f"Coastline preparation failed: {type(error).__name__}") from None
        self.stdout.write(self.style.SUCCESS(status["method"] + " ready"))