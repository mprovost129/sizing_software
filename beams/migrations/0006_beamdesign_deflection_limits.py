from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("beams", "0005_beamdesign_left_overhang_ft_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamdesign",
            name="cantilever_deflection_limit_live",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="cantilever_deflection_limit_total",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="deflection_limit_live",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="deflection_limit_total",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
