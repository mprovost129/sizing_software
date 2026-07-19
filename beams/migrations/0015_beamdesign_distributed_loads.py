from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beams", "0014_beamdesign_material"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamdesign",
            name="distributed_loads",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
