from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("greenwash_detector", "0002_greenwashflag_verification_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="greenwashflag",
            name="before_image_url",
            field=models.URLField(
                blank=True,
                max_length=2000,
                null=True,
                help_text="GEE Sentinel-2 thumbnail URL for the pre-project period",
            ),
        ),
        migrations.AddField(
            model_name="greenwashflag",
            name="after_image_url",
            field=models.URLField(
                blank=True,
                max_length=2000,
                null=True,
                help_text="GEE Sentinel-2 thumbnail URL for the post-project period",
            ),
        ),
    ]
