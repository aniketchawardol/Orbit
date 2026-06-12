from django.core.management.base import BaseCommand

from facility.engine import accrue_one_day


class Command(BaseCommand):
    help = "Accrue one day of storage cost (cron daily; demo can call repeatedly)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=1)

    def handle(self, *args, **options):
        for _ in range(options["days"]):
            summary = accrue_one_day()
            self.stdout.write(self.style.SUCCESS(str(summary)))
