from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.market.models import Symbol
from apps.market.services_regime import calculate_market_regime


class Command(BaseCommand):
    help = "Compute auditable India and US market-regime snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--market", choices=Symbol.Market.values)
        parser.add_argument("--as-of", type=date.fromisoformat)

    def handle(self, *args, **options):
        markets = [options["market"]] if options["market"] else [Symbol.Market.INDIA, Symbol.Market.US]
        failures = []
        for market in markets:
            try:
                snapshot = calculate_market_regime(market, options["as_of"])
                certificate = "verified" if snapshot.is_verified else "unverified"
                self.stdout.write(self.style.SUCCESS(
                    f"{market} {snapshot.as_of_date}: {snapshot.regime} score={snapshot.score:+d} "
                    f"coverage={snapshot.coverage_pct}% benchmark={snapshot.benchmark.symbol} ({certificate})"
                ))
            except Exception as error:
                failures.append(f"{market}: {error}")
        for failure in failures:
            self.stderr.write(failure)
        if failures:
            raise CommandError(f"Market regime failed for {len(failures)} market(s).")
