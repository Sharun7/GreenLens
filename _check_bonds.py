import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenlens.settings')
django.setup()

from data_ingestion.models import GreenBond
from django.db.models import Count

total = GreenBond.objects.count()
print("=== DATABASE STATUS ===")
print(f"Total bonds in database: {total}")
print()

print("Year distribution:")
for row in GreenBond.objects.values('issuance_date__year').annotate(n=Count('id')).order_by('issuance_date__year'):
    yr = row['issuance_date__year']
    n = row['n']
    bar = '#' * (n // 10)
    print(f"  {yr}: {n:4d}  {bar}")

print()
print("Bond types:")
for row in GreenBond.objects.values('project_category').annotate(n=Count('id')).order_by('-n'):
    print(f"  {row['project_category']}: {row['n']}")

print()
print("Top 15 countries by bond count:")
for row in GreenBond.objects.values('country').annotate(n=Count('id')).order_by('-n')[:15]:
    print(f"  {row['country']}: {row['n']} bonds")

print()
cbi_count = GreenBond.objects.filter(bond_id__contains='_Green_Bond_').count() + \
            GreenBond.objects.filter(bond_id__contains='_Social_Bond_').count() + \
            GreenBond.objects.filter(bond_id__contains='_Sustainability_').count()

# Synthetic bonds use simple patterns like DE_SOLAR_2021
synthetic_count = GreenBond.objects.filter(issuer_name__in=[
    'KfW Bankengruppe','Caisse des Depots','Apple Green Bond LLC',
    'Industrial Bank Co.','Adani Green Energy'
]).count()

print(f"CBI real-data bonds (approx): {total - 50}")
print(f"Synthetic demo bonds (approx): 50")
print()
print("Sample real bond IDs:")
for b in GreenBond.objects.filter(bond_id__contains='_Bond_')[:8]:
    print(f"  {b.bond_id} | {b.issuer_name[:50]} | {b.country}")
