import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beams", "0015_beamdesign_distributed_loads"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BeamLoadTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("uniform_load_basis", models.CharField(default="plf", max_length=10)),
                ("spacing_in", models.FloatField(default=16)),
                ("dead_load_plf", models.FloatField(default=0)),
                ("live_load_plf", models.FloatField(default=0)),
                ("snow_load_plf", models.FloatField(default=0)),
                ("roof_live_load_plf", models.FloatField(default=0)),
                ("wind_load_plf", models.FloatField(default=0)),
                ("point_loads", models.JSONField(blank=True, default=list)),
                ("distributed_loads", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="beam_load_templates", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="beamloadtemplate",
            constraint=models.UniqueConstraint(fields=("user", "name"), name="unique_beam_load_template_name_per_user"),
        ),
    ]
