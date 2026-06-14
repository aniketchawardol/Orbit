from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="origin",
            field=models.CharField(
                choices=[
                    ("PLATFORM", "Platform catalog"),
                    ("EXTERNAL", "User-listed (brought from outside)"),
                ],
                default="PLATFORM",
                max_length=10,
            ),
        ),
    ]
