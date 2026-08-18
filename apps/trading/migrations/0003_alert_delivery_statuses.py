from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("trading", "0002_price_alerts")]
    operations = [
        migrations.AddField(model_name="alertevent", name="desktop_status", field=models.CharField(default="NOT_REQUESTED", max_length=20)),
        migrations.AddField(model_name="alertevent", name="desktop_error", field=models.TextField(blank=True)),
        migrations.AddField(model_name="alertevent", name="sound_status", field=models.CharField(default="NOT_REQUESTED", max_length=20)),
        migrations.AddField(model_name="alertevent", name="sound_error", field=models.TextField(blank=True)),
    ]
