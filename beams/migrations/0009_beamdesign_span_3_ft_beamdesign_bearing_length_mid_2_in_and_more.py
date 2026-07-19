from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beams", "0008_beamdesign_multispan_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamdesign",
            name="bearing_length_mid_2_in",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="span_3_ft",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="support_type_mid_2",
            field=models.CharField(
                choices=[("wall_plate", "Wall / plate"), ("column", "Column / post"), ("hanger", "Hanger")],
                default="wall_plate",
                max_length=20,
            ),
        ),
    ]
