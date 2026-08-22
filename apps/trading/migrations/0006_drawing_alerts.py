from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("market", "0007_providerinstrument"), ("trading", "0005_trade_book")]

    operations = [
        migrations.AddField(model_name="pricealert", name="drawing_component", field=models.CharField(blank=True, max_length=20)),
        migrations.AddField(model_name="pricealert", name="source_drawing", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="price_alerts", to="market.chartdrawing")),
    ]
