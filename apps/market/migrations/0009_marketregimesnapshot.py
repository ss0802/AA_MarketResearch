from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("market", "0008_watchlistitem")]

    operations = [
        migrations.AddField(
            model_name="technicalsnapshot",
            name="sma200",
            field=models.DecimalField(decimal_places=6, max_digits=20, null=True),
        ),
        migrations.CreateModel(
            name="MarketRegimeSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("market", models.CharField(choices=[("US", "United States"), ("IND", "India")], max_length=3)),
                ("as_of_date", models.DateField()),
                ("benchmark_close", models.DecimalField(decimal_places=6, max_digits=20)),
                ("benchmark_sma20", models.DecimalField(decimal_places=6, max_digits=20)),
                ("benchmark_sma50", models.DecimalField(decimal_places=6, max_digits=20)),
                ("benchmark_sma200", models.DecimalField(decimal_places=6, max_digits=20)),
                ("benchmark_sma20_slope", models.DecimalField(decimal_places=8, max_digits=20)),
                ("universe_size", models.PositiveIntegerField()),
                ("breadth_count", models.PositiveIntegerField()),
                ("coverage_pct", models.DecimalField(decimal_places=3, max_digits=7)),
                ("pct_above_sma20", models.DecimalField(decimal_places=3, max_digits=7)),
                ("pct_above_sma50", models.DecimalField(decimal_places=3, max_digits=7)),
                ("pct_above_sma200", models.DecimalField(decimal_places=3, max_digits=7)),
                ("advances", models.PositiveIntegerField(default=0)),
                ("declines", models.PositiveIntegerField(default=0)),
                ("unchanged", models.PositiveIntegerField(default=0)),
                ("advance_decline_net", models.IntegerField(default=0)),
                ("advance_decline_line", models.BigIntegerField(default=0)),
                ("score", models.SmallIntegerField()),
                ("regime", models.CharField(choices=[("BULLISH", "Bullish"), ("NEUTRAL", "Neutral"), ("BEARISH", "Bearish")], max_length=8)),
                ("previous_regime", models.CharField(blank=True, choices=[("BULLISH", "Bullish"), ("NEUTRAL", "Neutral"), ("BEARISH", "Bearish")], max_length=8)),
                ("is_transition", models.BooleanField(default=False)),
                ("is_verified", models.BooleanField(default=False)),
                ("reasons", models.JSONField(default=list)),
                ("calculation_version", models.CharField(default="regime-v1", max_length=20)),
                ("calculated_at", models.DateTimeField(auto_now=True)),
                ("benchmark", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="market_regime_snapshots", to="market.symbol")),
            ],
            options={
                "ordering": ["-as_of_date", "market"],
                "indexes": [models.Index(fields=["market", "-as_of_date"], name="regime_market_date_idx")],
                "constraints": [models.UniqueConstraint(fields=("market", "as_of_date"), name="unique_market_regime_date")],
            },
        ),
    ]
