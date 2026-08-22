from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("market", "0007_providerinstrument")]

    operations = [
        migrations.CreateModel(
            name="WatchlistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("symbol", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="watchlist_item", to="market.symbol")),
            ],
            options={"ordering": ["position", "created_at", "id"]},
        ),
    ]
