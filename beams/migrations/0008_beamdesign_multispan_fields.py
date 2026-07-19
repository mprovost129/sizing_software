from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("beams", "0007_beamdesign_uniform_load_basis_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamdesign",
            name="bearing_length_mid_in",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="span_2_ft",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="support_type_mid",
            field=models.CharField(choices=[("wall_plate", "Wall / Plate"), ("column", "Column / Post"), ("hanger", "Hanger")], default="wall_plate", max_length=20),
        ),
    ]
