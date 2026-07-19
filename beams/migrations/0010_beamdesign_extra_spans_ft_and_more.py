from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beams", "0009_beamdesign_span_3_ft_beamdesign_bearing_length_mid_2_in_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamdesign",
            name="extra_interior_bearing_lengths_in",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="extra_interior_support_types",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="extra_spans_ft",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
