# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

#!/usr/bin/env python
import subprocess
import sys
import os

# Change to the correct directory
os.chdir(r"C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens")
python_path = r"C:\Users\sharu\AppData\Local\Programs\Python\Python311\python.exe"

# Step 1: Install datasets package
print("=== Step 1: Installing datasets package ===")
result1 = subprocess.run(
    [python_path, "-m", "pip", "install", "datasets>=2.20.0", "--quiet"],
    capture_output=False,
)

if result1.returncode != 0:
    print("Step 1 failed with return code:", result1.returncode)
    sys.exit(1)

print("Step 1 completed successfully\n")

# Step 2: Run batch_greenwash_check with environment variable
print("=== Step 2: Running batch_greenwash_check ===")
env = os.environ.copy()
env["DJANGO_SETTINGS_MODULE"] = "greenlens.settings"

result2 = subprocess.run(
    [python_path, "manage.py", "batch_greenwash_check", "--limit", "20"],
    env=env,
    cwd=r"C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens"
)

sys.exit(result2.returncode)
