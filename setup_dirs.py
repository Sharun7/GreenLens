# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

import os

base = r'c:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens'
dirs = [
    'greenlens',
    'data_ingestion/migrations',
    'risk_scoring/migrations',
    'pricing_analysis/migrations',
    'greenwash_detector/migrations',
    'dashboard/migrations',
    'templates/dashboard',
    'static/css',
    'static/js',
]
for d in dirs:
    os.makedirs(os.path.join(base, d), exist_ok=True)
    print(f'Created: {d}')

init_dirs = [
    'greenlens',
    'data_ingestion',
    'data_ingestion/migrations',
    'risk_scoring',
    'risk_scoring/migrations',
    'pricing_analysis',
    'pricing_analysis/migrations',
    'greenwash_detector',
    'greenwash_detector/migrations',
    'dashboard',
    'dashboard/migrations',
]
for d in init_dirs:
    p = os.path.join(base, d, '__init__.py')
    open(p, 'a').close()
    print(f'Init: {p}')

print('ALL DONE')
