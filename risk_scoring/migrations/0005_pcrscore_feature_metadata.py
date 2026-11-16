from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("risk_scoring", "0004_remove_pcrscore_idx_pcr_score_bond_and_more")]

    operations = [
        migrations.AddField(
            model_name="pcrscore", name="feature_metadata",
            field=models.JSONField(
                default=dict, blank=True,
                help_text="Input values, provenance, SHAP baseline and artifact status for this prediction",
            ),
        ),
    ]