from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max

from apps.market.models import MarketRegimeSnapshot, OHLCV, Symbol
from apps.market.services_regime import _benchmark_for, _pct, classify_regime


class Command(BaseCommand):
    help = "Backfill daily market regime, breadth and advance/decline history."

    def add_arguments(self, parser):
        parser.add_argument("--market", required=True, choices=Symbol.Market.values)
        parser.add_argument("--start", type=date.fromisoformat)
        parser.add_argument("--end", type=date.fromisoformat)
        parser.add_argument("--days", type=int, default=365)

    def handle(self, *args, **options):
        market = options["market"]
        tradeable = Symbol.objects.filter(
            market=market, is_active=True,
            universe_memberships__universe__is_ohlcv_enabled=True,
            universe_memberships__effective_to__isnull=True,
        ).distinct()
        universe_size = tradeable.count()
        if not universe_size:
            raise CommandError("No tradeable universe exists.")
        end = options["end"] or OHLCV.objects.filter(
            symbol__in=tradeable, timeframe="D",
        ).aggregate(value=Max("date"))["value"]
        if end is None:
            raise CommandError("No daily OHLCV exists.")
        start = options["start"] or end - timedelta(days=options["days"])
        load_from = start - timedelta(days=420)
        rows = list(OHLCV.objects.filter(
            symbol__in=tradeable, timeframe="D", date__gte=load_from, date__lte=end,
        ).values("symbol_id", "date", "close"))
        if not rows:
            raise CommandError("No OHLCV rows matched the requested period.")
        frame = pd.DataFrame.from_records(rows).sort_values(["symbol_id", "date"])
        frame["close"] = pd.to_numeric(frame["close"])
        grouped = frame.groupby("symbol_id", sort=False)["close"]
        frame["previous"] = grouped.shift(1)
        for length in (20, 50, 200):
            frame[f"sma{length}"] = grouped.transform(lambda values, n=length: values.rolling(n).mean())

        daily = frame[frame["date"].between(start, end)].groupby("date").agg(
            breadth_count=("symbol_id", "nunique"),
            eligible_sma20=("sma20", "count"), eligible_sma50=("sma50", "count"), eligible_sma200=("sma200", "count"),
        )
        # Boolean participation and A/D require aligned columns, so aggregate separately.
        scoped = frame[frame["date"].between(start, end)].copy()
        participation = scoped.assign(
            above20=scoped["close"] > scoped["sma20"],
            above50=scoped["close"] > scoped["sma50"],
            above200=scoped["close"] > scoped["sma200"],
            advance=scoped["close"] > scoped["previous"],
            decline=scoped["close"] < scoped["previous"],
            unchanged=scoped["close"] == scoped["previous"],
        ).groupby("date").agg(
            above20=("above20", "sum"), above50=("above50", "sum"), above200=("above200", "sum"),
            advances=("advance", "sum"), declines=("decline", "sum"), unchanged=("unchanged", "sum"),
        )
        daily = daily.join(participation)

        benchmark = _benchmark_for(market)
        benchmark_rows = list(benchmark.ohlcv.filter(
            timeframe="D", date__gte=load_from, date__lte=end,
        ).order_by("date").values("date", "close"))
        benchmark_frame = pd.DataFrame.from_records(benchmark_rows)
        benchmark_frame["close"] = pd.to_numeric(benchmark_frame["close"])
        for length in (20, 50, 200):
            benchmark_frame[f"sma{length}"] = benchmark_frame["close"].rolling(length).mean()
        benchmark_frame["sma20_slope"] = (benchmark_frame["sma20"] - benchmark_frame["sma20"].shift(5)) / 5
        benchmark_frame = benchmark_frame.set_index("date")

        previous = MarketRegimeSnapshot.objects.filter(market=market, as_of_date__lt=start).order_by("-as_of_date").first()
        previous_regime = previous.regime if previous else ""
        ad_line = previous.advance_decline_line if previous else 0
        snapshots = []
        for as_of, values in daily.iterrows():
            if as_of not in benchmark_frame.index:
                continue
            bench = benchmark_frame.loc[as_of]
            if pd.isna(bench["sma200"]) or pd.isna(bench["sma20_slope"]):
                continue
            eligible20, eligible50, eligible200 = int(values.eligible_sma20), int(values.eligible_sma50), int(values.eligible_sma200)
            if not min(eligible20, eligible50, eligible200):
                continue
            pct20 = _pct(int(values.above20), eligible20)
            pct50 = _pct(int(values.above50), eligible50)
            pct200 = _pct(int(values.above200), eligible200)
            advances, declines, unchanged = int(values.advances), int(values.declines), int(values.unchanged)
            ad_net = advances - declines
            ad_line += ad_net
            score = 0
            reasons = []
            binary = [
                (bench["close"] > bench["sma20"], "Benchmark above SMA20", "Benchmark below SMA20"),
                (bench["sma20"] > bench["sma50"], "SMA20 above SMA50", "SMA20 below SMA50"),
                (bench["close"] > bench["sma200"], "Benchmark above SMA200", "Benchmark below SMA200"),
                (bench["sma20_slope"] > 0, "SMA20 slope rising", "SMA20 slope falling"),
            ]
            for positive, good, bad in binary:
                score += 1 if positive else -1
                reasons.append(good if positive else bad)
            for label, pct in (("SMA20", pct20), ("SMA50", pct50), ("SMA200", pct200)):
                if pct >= 55: score += 1; reasons.append(f"{pct}% above {label}: broad participation")
                elif pct <= 45: score -= 1; reasons.append(f"{pct}% above {label}: weak participation")
                else: reasons.append(f"{pct}% above {label}: mixed participation")
            if ad_net > 0: score += 1; reasons.append("Advances exceed declines")
            elif ad_net < 0: score -= 1; reasons.append("Declines exceed advances")
            else: reasons.append("Advances equal declines")
            regime = classify_regime(score, previous_regime)
            coverage = _pct(int(values.breadth_count), universe_size)
            eligibility = _pct(eligible200, universe_size)
            reasons.append(f"Current-data coverage {coverage}%; SMA200 eligibility {eligibility}%")
            reasons.append("Historical breadth reconstructed from the current tradeable universe")
            snapshots.append(MarketRegimeSnapshot(
                market=market, as_of_date=as_of, benchmark=benchmark,
                benchmark_close=Decimal(str(bench["close"])), benchmark_sma20=Decimal(str(bench["sma20"])),
                benchmark_sma50=Decimal(str(bench["sma50"])), benchmark_sma200=Decimal(str(bench["sma200"])),
                benchmark_sma20_slope=Decimal(str(bench["sma20_slope"])), universe_size=universe_size,
                breadth_count=int(values.breadth_count), coverage_pct=coverage,
                eligible_sma20=eligible20, eligible_sma50=eligible50, eligible_sma200=eligible200,
                pct_above_sma20=pct20, pct_above_sma50=pct50, pct_above_sma200=pct200,
                advances=advances, declines=declines, unchanged=unchanged,
                advance_decline_net=ad_net, advance_decline_line=ad_line, score=score, regime=regime,
                previous_regime=previous_regime, is_transition=bool(previous_regime and previous_regime != regime),
                is_verified=coverage >= 98 and eligibility >= 80, reasons=reasons,
            ))
            previous_regime = regime
        if not snapshots:
            raise CommandError("No regime snapshots could be calculated.")
        update_fields = [field.name for field in MarketRegimeSnapshot._meta.fields if field.name not in {"id", "market", "as_of_date", "calculated_at"}]
        MarketRegimeSnapshot.objects.bulk_create(
            snapshots, batch_size=500, update_conflicts=True,
            unique_fields=["market", "as_of_date"], update_fields=update_fields,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Stored {len(snapshots)} {market} regime snapshots from {snapshots[0].as_of_date} to {snapshots[-1].as_of_date}."
        ))
