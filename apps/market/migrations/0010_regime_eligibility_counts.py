from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("market", "0009_marketregimesnapshot")]

    operations = [
        migrations.AddField(
            model_name="marketregimesnapshot", name="eligible_sma20",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="marketregimesnapshot", name="eligible_sma50",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="marketregimesnapshot", name="eligible_sma200",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
