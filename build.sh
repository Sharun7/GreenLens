#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Running database migrations..."
python manage.py migrate --no-input

echo "Seeding bond data and triggering ML scoring..."
# The seed_demo_data command was configured to load the entire CSV previously
python manage.py seed_demo_data
