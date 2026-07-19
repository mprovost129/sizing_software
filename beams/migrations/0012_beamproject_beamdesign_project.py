import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("beams", "0011_alter_beamdesign_support_type_mid_2"),
    ]

    operations = [
        migrations.CreateModel(
            name="BeamProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("client_name", models.CharField(blank=True, max_length=120)),
                ("site_address", models.CharField(blank=True, max_length=200)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="beam_projects", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["name", "-updated_at"],
            },
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="project",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="designs", to="beams.beamproject"),
        ),
    ]
