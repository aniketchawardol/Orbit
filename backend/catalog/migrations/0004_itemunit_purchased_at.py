from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_product_origin"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemunit",
            name="purchased_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
