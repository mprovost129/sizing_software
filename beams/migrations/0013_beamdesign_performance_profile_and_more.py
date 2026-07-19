from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("beams", "0012_beamproject_beamdesign_project"),
    ]

    operations = [
        migrations.AddField(
            model_name="beamdesign",
            name="performance_profile",
            field=models.CharField(
                choices=[
                    ("code_minimum", "Code minimum"),
                    ("enhanced_comfort", "Enhanced comfort"),
                    ("premium_finish", "Premium finish / hard-surface focus"),
                ],
                default="code_minimum",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="beamdesign",
            name="subfloor_profile",
            field=models.CharField(
                choices=[
                    ("none", "None / not applicable"),
                    ("panel", "Standard panel subfloor"),
                    ("glued_screwed", "Glued and screwed panel subfloor"),
                ],
                default="none",
                max_length=30,
            ),
        ),
    ]
