from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("trading", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="PriceAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("direction", models.CharField(choices=[("ABOVE", "Crosses above"), ("BELOW", "Crosses below")], max_length=5)),
                ("target_price", models.DecimalField(decimal_places=6, max_digits=20)),
                ("is_active", models.BooleanField(default=True)),
                ("notify_in_app", models.BooleanField(default=True)),
                ("notify_telegram", models.BooleanField(default=True)),
                ("notify_desktop", models.BooleanField(default=True)),
                ("notify_sound", models.BooleanField(default=True)),
                ("last_price", models.DecimalField(blank=True, decimal_places=6, max_digits=20, null=True)),
                ("last_quote_at", models.DateTimeField(blank=True, null=True)),
                ("triggered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("symbol", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="price_alerts", to="market.symbol")),
            ],
            options={"ordering": ["-is_active", "symbol__market", "symbol__symbol"]},
        ),
        migrations.CreateModel(
            name="AlertEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.DecimalField(decimal_places=6, max_digits=20)),
                ("quote_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("telegram_status", models.CharField(default="NOT_REQUESTED", max_length=20)),
                ("telegram_error", models.TextField(blank=True)),
                ("alert", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="trading.pricealert")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
