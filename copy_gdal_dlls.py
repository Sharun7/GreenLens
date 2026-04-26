"""
copy_gdal_dlls.py — Run with: python copy_gdal_dlls.py

Copies all GDAL/GEOS DLLs from AppData (blocked by Application Control)
to C:\ProgramData\greenlens-gdal\ (trusted system path).
"""
import os
import shutil
import glob

SOURCE = r"C:\Users\sharu\AppData\Local\Programs\OSGeo4W\bin"
DEST   = r"C:\ProgramData\greenlens-gdal"

alt_sources = [
    r"C:\OSGeo4W\bin",
    r"C:\Program Files\OSGeo4W\bin",
]
for alt in alt_sources:
    if not os.path.isdir(SOURCE) and os.path.isdir(alt):
        SOURCE = alt

if not os.path.isdir(SOURCE):
    print(f"ERROR: OSGeo4W bin not found at {SOURCE}")
    raise SystemExit(1)

os.makedirs(DEST, exist_ok=True)
print(f"Source : {SOURCE}")
print(f"Dest   : {DEST}\n")

dlls = glob.glob(os.path.join(SOURCE, "*.dll"))
copied = 0
for dll in dlls:
    name = os.path.basename(dll)
    shutil.copy2(dll, os.path.join(DEST, name))
    copied += 1
    if copied % 20 == 0:
        print(f"  copied {copied}/{len(dlls)} ...")

gdal_dlls = glob.glob(os.path.join(DEST, "gdal*.dll"))
geos_dll  = os.path.join(DEST, "geos_c.dll")

print(f"\nCopied {copied} DLLs to {DEST}")
print(f"GDAL : {gdal_dlls[0] if gdal_dlls else 'NOT FOUND'}")
print(f"GEOS : {geos_dll if os.path.exists(geos_dll) else 'NOT FOUND'}")

if gdal_dlls and os.path.exists(geos_dll):
    print("\nSuccess! Now run:")
    print("  python manage.py makemigrations pricing_analysis")
    print("  python manage.py migrate")
    print("  python manage.py train_pcrs_model")
else:
    print("\nWARNING: Some DLLs missing — check source path")
