import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("beams", "0017_project_status_and_design_revisions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BeamProjectIssue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=80)),
                ("notes", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="beam_project_issues",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issues",
                        to="beams.beamproject",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="BeamProjectIssueMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(default=0)),
                (
                    "design_revision",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="project_issue_memberships",
                        to="beams.beamdesign",
                    ),
                ),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="beams.beamprojectissue",
                    ),
                ),
            ],
            options={"ordering": ["position", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="beamprojectissuemember",
            constraint=models.UniqueConstraint(
                fields=("issue", "design_revision"), name="unique_design_revision_per_project_issue",
            ),
        ),
    ]
