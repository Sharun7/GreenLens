#!/usr/bin/env bash
set -o errexit

echo "Installing dependencies..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo "Running migrations..."
python manage.py migrate

echo "Loading bond data..."
python manage.py load_cbi_bonds data/green_bonds-21.csv || true

echo "Initializing demo data..."
python manage.py initialize_demo_data || true

echo "Fitting pricing model and rescoring..."
python manage.py fit_pricing_model --rescore || true

echo "Seeding missing named issuer bonds..."
python manage.py seed_demo_data || true

echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Build complete."
