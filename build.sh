#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python manage.py migrate
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv || true
python manage.py collectstatic --no-input
