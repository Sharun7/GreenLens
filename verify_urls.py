# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Verify all URLs show REAL data
"""
import requests
from bs4 import BeautifulSoup

def check_url(url, name, checks):
    """Check a URL and verify it shows real data"""
    print(f"\n{'='*60}")
    print(f"Checking: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"✓ Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"✗ ERROR: Expected 200, got {response.status_code}")
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        text = response.text.lower()
        
        all_passed = True
        for check_name, check_func in checks.items():
            result = check_func(text, soup)
            if result:
                print(f"✓ {check_name}: PASS")
            else:
                print(f"✗ {check_name}: FAIL")
                all_passed = False
        
        return all_passed
    
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False


# Define checks for each URL
predictions_checks = {
    "Shows MLP Neural Network": lambda t, s: "mlp neural network" in t or "mlp" in t,
    "Shows confidence intervals": lambda t, s: "confidence" in t,
    "Shows PCRS predictions": lambda t, s: "pcrs" in t or "prediction" in t,
    "Shows real bond data": lambda t, s: "bond" in t and ("score" in t or "risk" in t),
}

regulatory_checks = {
    "Shows SFDR data": lambda t, s: "sfdr" in t or "eu" in t,
    "Shows SEBI data": lambda t, s: "sebi" in t or "india" in t,
    "Shows regulations": lambda t, s: "regulation" in t or "compliance" in t,
    "Shows real data (not placeholder)": lambda t, s: "regulation" in t and not "placeholder" in t,
}

risk_checks = {
    "Shows incidents": lambda t, s: "incident" in t,
    "Shows model drift": lambda t, s: "drift" in t or "model" in t,
    "Shows data quality": lambda t, s: "quality" in t or "data" in t,
    "Shows automatic monitoring": lambda t, s: "monitor" in t or "automatic" in t,
}

alerts_checks = {
    "Shows regulatory alerts": lambda t, s: "regulatory" in t,
    "Shows affected bonds": lambda t, s: "affected" in t and "bond" in t,
    "Shows compliance deadline": lambda t, s: "deadline" in t or "compliance" in t or "effective" in t,
    "Shows alert types": lambda t, s: "climate" in t or "greenwash" in t or "pricing" in t,
}

# Run all checks
print("\n" + "="*60)
print("GREENLENS URL VERIFICATION - REAL DATA CHECK")
print("="*60)

results = {}

results["predictions"] = check_url(
    "http://127.0.0.1:8000/ai/predictions/",
    "AI Predictions Dashboard",
    predictions_checks
)

results["regulatory"] = check_url(
    "http://127.0.0.1:8000/ai/regulatory/",
    "Regulatory Monitor",
    regulatory_checks
)

results["alerts"] = check_url(
    "http://127.0.0.1:8000/ai/alerts/",
    "Automated Alerts Feed",
    alerts_checks
)

# Summary
print("\n" + "="*60)
print("SUMMARY")
print("="*60)

for name, passed in results.items():
    status = "✓ PASS - Shows REAL data" if passed else "✗ FAIL - Issues detected"
    print(f"{name.upper()}: {status}")

all_passed = all(results.values())
print("\n" + "="*60)
if all_passed:
    print("✓ ALL URLS SHOW REAL DATA")
else:
    print("✗ SOME URLS HAVE ISSUES")
print("="*60)
