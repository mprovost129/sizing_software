import uuid

import django.db.models.deletion
from django.db import migrations, models


def assign_revision_groups(apps, schema_editor):
    beam_design = apps.get_model("beams", "BeamDesign")
    for design in beam_design.objects.filter(revision_group__isnull=True).iterator():
        design.revision_group = uuid.uuid4()
        design.save(update_fields=["revision_group"])


class Migration(migrations.Migration):
    dependencies = [("beams", "0016_beamloadtemplate")]

    operations = [
        migrations.AddField(
            model_name="beamproject",
            name="project_number",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="beamproject",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("on_hold", "On Hold"),
                    ("complete", "Complete"),
                    ("archived", "Archived"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="revision_group",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(assign_revision_groups, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="beamdesign",
            name="revision_group",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="revision_number",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="revision_note",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="supersedes",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="revisions",
                to="beams.beamdesign",
            ),
        ),
    ]
