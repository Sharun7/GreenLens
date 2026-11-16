from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai_features", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="portfoliooptimization",
            name="current_return",
            field=models.FloatField(null=True, blank=True, help_text="Externally evidenced return %, if available"),
        ),
        migrations.AlterField(
            model_name="portfoliooptimization",
            name="optimized_return",
            field=models.FloatField(null=True, blank=True, help_text="Externally evidenced scenario return %, if available"),
        ),
    ]