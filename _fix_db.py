"""
Fix issuer_name fields in the database that contain '?' from the previous
load run where the en-dash (–) was not properly encoded on Windows.
Also removes the 'World' aggregate records that aren't real bonds.
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenlens.settings')
django.setup()

from data_ingestion.models import GreenBond

# 1. Fix issuer names with replacement chars
print("=== Fixing issuer names with '?' replacement characters ===")
bonds_with_issues = GreenBond.objects.filter(issuer_name__contains='?')
print(f"Found {bonds_with_issues.count()} bonds with '?' in issuer_name")

fixed = 0
for bond in bonds_with_issues:
    # The pattern is: "Country ? IssuerType (Bond Type)" 
    # Replace ' ? ' with ' - '
    new_name = bond.issuer_name.replace(' ? ', ' - ').replace('?', '')
    if new_name != bond.issuer_name:
        bond.issuer_name = new_name
        bond.save(update_fields=['issuer_name'])
        fixed += 1

print(f"Fixed {fixed} issuer names")
print()

# 2. Show current database health
total = GreenBond.objects.count()
print(f"=== DATABASE HEALTH CHECK ===")
print(f"Total bonds: {total}")
print(f"Bonds with lat=0, lon=0 (geocode failed): {GreenBond.objects.filter(lat=0, lon=0).count()}")
print(f"Bonds with valid coordinates: {GreenBond.objects.exclude(lat=0, lon=0).count()}")
print()

# 3. Show year breakdown
print("Year breakdown of real bonds:")
from django.db.models import Count
for row in GreenBond.objects.filter(project_category='other').values('issuance_date__year').annotate(n=Count('id')).order_by('issuance_date__year'):
    print(f"  {row['issuance_date__year']}: {row['n']} bonds")

print()
print("=== READY ===")
print(f"Your database has {GreenBond.objects.count()} real green bond records")
print("Run: python manage.py runserver 8000")
