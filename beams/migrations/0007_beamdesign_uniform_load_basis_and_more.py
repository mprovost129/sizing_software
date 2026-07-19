from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("beams", "0006_beamdesign_deflection_limits"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamdesign",
            name="roof_live_load_plf",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="spacing_in",
            field=models.FloatField(default=16),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="uniform_load_basis",
            field=models.CharField(default="plf", max_length=10),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="wind_load_plf",
            field=models.FloatField(default=0),
        ),
    ]
