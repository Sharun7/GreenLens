@echo off
cd /d "C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens"

echo === Step 1: Installing datasets package ===
C:\Users\sharu\AppData\Local\Programs\Python\Python311\python.exe -m pip install "datasets>=2.20.0" --quiet

if errorlevel 1 (
    echo Step 1 failed
    exit /b 1
)

echo Step 1 completed successfully

echo.
echo === Step 2: Running batch_greenwash_check ===
set DJANGO_SETTINGS_MODULE=greenlens.settings
C:\Users\sharu\AppData\Local\Programs\Python\Python311\python.exe manage.py batch_greenwash_check --limit 20

exit /b %errorlevel%
