from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingestionjob",
            name="failed_rows",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ingestionjob",
            name="row_errors",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
