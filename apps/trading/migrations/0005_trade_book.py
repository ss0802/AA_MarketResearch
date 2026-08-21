from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("trading", "0004_alert_lifecycle_worker_state")]

    operations = [
        migrations.AddField(
            model_name="trade",
            name="current_stop_price",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=20, null=True),
        ),
        migrations.CreateModel(
            name="TradePositionMark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.DecimalField(decimal_places=6, max_digits=20)),
                ("marked_at", models.DateTimeField()),
                ("source", models.CharField(choices=[("MANUAL", "Manual"), ("EOD", "End of day"), ("LIVE", "Live feed")], default="MANUAL", max_length=10)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("trade", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="position_marks", to="trading.trade")),
            ],
            options={"ordering": ["-marked_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="tradepositionmark",
            index=models.Index(fields=["trade", "-marked_at"], name="position_mark_trade_idx"),
        ),
    ]
