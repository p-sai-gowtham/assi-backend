from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0002_alertrule_enabled_alertrule_last_evaluated_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertrule",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
