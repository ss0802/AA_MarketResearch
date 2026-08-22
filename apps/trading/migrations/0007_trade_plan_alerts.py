from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("trading", "0006_drawing_alerts")]

    operations = [
        migrations.AddField(
            model_name="pricealert",
            name="alert_role",
            field=models.CharField(blank=True, choices=[("ENTRY", "Entry"), ("STOP", "Stop-loss"), ("TARGET", "Target")], max_length=10),
        ),
        migrations.AddField(
            model_name="pricealert",
            name="source_trade",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="price_alerts", to="trading.trade"),
        ),
    ]
