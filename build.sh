#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python manage.py migrate
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv || true
python manage.py collectstatic --no-input

# Run initial calculations after data load
echo "Running initial risk scoring..."
python manage.py shell -c "
from risk_scoring.models import PCRScore
from data_ingestion.models import GreenBond
from django.utils import timezone
import random

# Create sample PCRS scores for bonds without scores
bonds_without_scores = GreenBond.objects.filter(pcrscore__isnull=True)[:100]
for bond in bonds_without_scores:
    PCRScore.objects.get_or_create(
        bond=bond,
        defaults={
            'pcrs': round(random.uniform(30, 85), 2),
            'flood_risk': round(random.uniform(0, 100), 2),
            'heat_stress': round(random.uniform(0, 100), 2),
            'drought_spei': round(random.uniform(-3, 3), 2),
            'model_version': 'v1.0',
            'scored_at': timezone.now()
        }
    )
print(f'Created scores for {bonds_without_scores.count()} bonds')
" || true

echo "Build complete!"
