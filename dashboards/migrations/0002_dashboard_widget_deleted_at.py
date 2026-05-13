from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="dashboard",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="widget",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
