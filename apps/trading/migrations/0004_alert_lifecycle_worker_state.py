from django.db import migrations, models

def initialize_status(apps, schema_editor):
    Alert = apps.get_model("trading", "PriceAlert")
    Alert.objects.filter(is_active=True).update(status="ACTIVE")
    Alert.objects.filter(is_active=False, triggered_at__isnull=False).update(status="TRIGGERED")
    Alert.objects.filter(is_active=False, triggered_at__isnull=True).update(status="PAUSED")

class Migration(migrations.Migration):
    dependencies = [("trading", "0003_alert_delivery_statuses")]
    operations = [
        migrations.AddField(model_name="pricealert", name="status", field=models.CharField(choices=[("ACTIVE", "Active"), ("PAUSED", "Paused"), ("TRIGGERED", "Triggered"), ("ARCHIVED", "Archived")], default="ACTIVE", max_length=10)),
        migrations.CreateModel(name="AlertWorkerState", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(default="tiingo_us", max_length=30, unique=True)),
            ("status", models.CharField(default="STOPPED", max_length=20)),
            ("connected_at", models.DateTimeField(blank=True, null=True)),
            ("last_heartbeat_at", models.DateTimeField(blank=True, null=True)),
            ("last_quote_at", models.DateTimeField(blank=True, null=True)),
            ("last_error", models.TextField(blank=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.RunPython(initialize_status, migrations.RunPython.noop),
    ]
