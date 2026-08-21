from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("market", "0006_chartdrawing")]

    operations = [
        migrations.CreateModel(
            name="ProviderInstrument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=30)),
                ("instrument_id", models.CharField(max_length=80)),
                ("exchange_code", models.CharField(max_length=20)),
                ("segment", models.CharField(blank=True, max_length=30)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="provider_instruments", to="market.symbol")),
            ],
        ),
        migrations.AddConstraint(
            model_name="providerinstrument",
            constraint=models.UniqueConstraint(fields=("symbol", "provider"), name="unique_symbol_provider_instrument"),
        ),
        migrations.AddConstraint(
            model_name="providerinstrument",
            constraint=models.UniqueConstraint(fields=("provider", "exchange_code", "instrument_id"), name="unique_provider_exchange_instrument"),
        ),
        migrations.AddIndex(
            model_name="providerinstrument",
            index=models.Index(fields=["provider", "instrument_id"], name="provider_instrument_idx"),
        ),
    ]
