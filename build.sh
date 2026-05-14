#!/usr/bin/env bash
set -o errexit

echo "Installing dependencies..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo "Running migrations..."
python manage.py migrate

echo "Loading bond data..."
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv || true

echo "Initializing demo data (risk scores, pricing, bias detection)..."
python manage.py initialize_demo_data || true

echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Build complete!"
