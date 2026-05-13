# File Locations Summary - GDAL & CSV

## Quick Answer to Your Questions

### 1. Where are these files referenced in code?

#### GDAL-3.11.4-cp311-cp311-win_amd64.whl

**Referenced in**:
- `requirements.txt` (lines 14-17) - Installation instructions only

**NOT referenced in any Python code** ✅

```txt
# From requirements.txt:
# GDAL installation (Windows):
# Download GDAL wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/#gdal
# pip install GDAL-3.11.4-cp311-cp311-win_amd64.whl
# Then install rasterio
```

This is just a **comment/instruction**, not actual code that runs.

#### green_bonds-21.csv

**Referenced in**:
- `data_ingestion/management/commands/load_cbi_bonds.py` (line 19)

```python
# Line 19 in load_cbi_bonds.py:
parser.add_argument("--file", required=True, help="Path to green_bonds-21.csv")
```

**This is CORRECT!** ✅ The file path is passed as a command-line argument, not hardcoded.

### 2. Should these files be moved to GreenLens folder?

| File | Move to GreenLens? | Reason |
|------|-------------------|--------|
| `GDAL-*.whl` | ❌ **NO** | Windows-specific, 20+ MB, not needed for production |
| `green_bonds-21.csv` | ✅ **YES** | Needed for initial data load, should be in `data/` folder |

### 3. How do these files work during hosting?

#### GDAL Wheel File

**Answer**: **NOT needed for hosting!** ❌

**Why?**
1. Your Django app uses `django.db.backends.postgresql` (not PostGIS backend)
2. PostGIS extension in PostgreSQL handles all spatial operations
3. Your models don't use `PointField` or other GIS fields that require GDAL
4. GDAL is only needed for local development on Windows

**During hosting**: Skip GDAL installation completely. Your production server doesn't need it.

#### Green Bonds CSV File

**Answer**: **Load once during deployment** ✅

**How it works**:

1. **Local Development**:
   ```bash
   # Place CSV in data/ folder
   python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
   ```

2. **Production Deployment**:
   ```bash
   # Option A: Upload CSV to server, then load
   scp data/green_bonds-21.csv user@server:/app/data/
   python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
   
   # Option B: Export local database, import to production
   pg_dump greenlens_db > backup.sql
   psql production_db < backup.sql
   
   # Option C: Store in cloud storage (S3, GCS)
   aws s3 cp data/green_bonds-21.csv s3://bucket/data/
   # Download during deployment and load
   ```

3. **After Loading**:
   - Data is stored in PostgreSQL database
   - CSV file is no longer needed for daily operations
   - Database persists across server restarts

---

## Current File Status

### GDAL Wheel File

**Current Location**: `C:\Users\sharu\Downloads\GDAL-3.11.4-cp311-cp311-win_amd64.whl`

**Action Needed**: ✅ **NONE** - Leave it in Downloads

**Reason**: 
- Not needed for production
- Windows-specific (won't work on Linux servers)
- Too large for Git (20+ MB)
- Only used for local development

### Green Bonds CSV File

**Current Location**: ❓ **NOT FOUND** in Downloads or data/ folder

**Action Needed**: 
1. Locate the CSV file (check Downloads, Desktop, or other folders)
2. Move it to: `C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens\data\green_bonds-21.csv`
3. Run: `python manage.py load_cbi_bonds --file=data/green_bonds-21.csv`

**If CSV file is missing**:
- You may have already loaded the data into your database
- Check if you have bond data in your database: `python manage.py shell` → `from data_ingestion.models import GreenBond` → `GreenBond.objects.count()`
- If you have data, you don't need the CSV file anymore (it's already in the database)

---

## File Paths in Code

### Where GDAL is Referenced

**File**: `requirements.txt`

```txt
# Lines 14-17:
# GDAL installation (Windows):
# Download GDAL wheel from https://www.lfd.uci.edu/~gohlke/pythonlibs/#gdal
# pip install GDAL-3.11.4-cp311-cp311-win_amd64.whl
# Then install rasterio
```

**Type**: Comment/instruction only (not executed code)

**Action**: No changes needed ✅

### Where CSV is Referenced

**File**: `data_ingestion/management/commands/load_cbi_bonds.py`

**Line 19**:
```python
parser.add_argument("--file", required=True, help="Path to green_bonds-21.csv")
```

**Line 256** (usage):
```python
csv_path = Path(options["file"])
if not csv_path.exists():
    raise CommandError(f"File not found: {csv_path}")
```

**Type**: Command-line argument (not hardcoded) ✅

**Action**: No changes needed ✅

---

## Hosting Workflow

### Step 1: Local Development (Already Done ✅)

```bash
# 1. Install GDAL (Windows only)
pip install C:\Users\sharu\Downloads\GDAL-3.11.4-cp311-cp311-win_amd64.whl

# 2. Load bond data
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv

# 3. Run server
python manage.py runserver
```

### Step 2: Push to GitHub (Already Done ✅)

```bash
git add .
git commit -m "GreenLens v2.0 - Initial public release"
git push origin main
```

**Files excluded by .gitignore**:
- ✅ `.env` (secrets)
- ✅ `*.sqlite3` (local database)
- ✅ `data/*.csv` (large data files)
- ✅ `GDAL-*.whl` (not in project folder anyway)

### Step 3: Deploy to Production

**On production server (Render, Heroku, AWS, etc.)**:

```bash
# 1. Clone repository
git clone https://github.com/Sharun7/GreenLens.git
cd GreenLens

# 2. Install dependencies (NO GDAL!)
pip install -r requirements.txt
# Note: Skip GDAL installation - not needed!

# 3. Configure environment
cp .env.example .env
nano .env  # Add your production values

# 4. Run migrations
python manage.py migrate

# 5. Load bond data (one-time)
# Upload CSV file first, then:
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv

# 6. Start server
gunicorn greenlens.wsgi:application --bind 0.0.0.0:8000
```

### Step 4: Background Tasks

```bash
# Start Celery worker
celery -A greenlens worker -l info

# Start Celery beat (scheduled tasks)
celery -A greenlens beat -l info
```

---

## Summary Table

| File | Current Location | Should Be In | Commit to Git? | Needed for Hosting? | How It Works |
|------|------------------|--------------|----------------|---------------------|--------------|
| `GDAL-*.whl` | Downloads | Downloads | ❌ NO | ❌ NO | Local dev only, not needed for production |
| `green_bonds-21.csv` | ❓ Not found | `data/` folder | ⚠️ Optional | ✅ YES | Load once during deployment, data persists in database |
| `.env` | Root | Root | ❌ NO | ✅ YES | Create on server with production values |
| `credentials.json` | Root | Root | ❌ NO | ✅ YES | Upload to server for Google Earth Engine |

---

## Action Items

### For GDAL Wheel File

✅ **DONE** - No action needed. Leave it in Downloads.

### For Green Bonds CSV File

**If you can find the CSV file**:

```bash
# Move to data folder
move "C:\Users\sharu\Downloads\green_bonds-21.csv" "C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens\data\green_bonds-21.csv"

# Commit to Git (optional, if file is small)
git add data/green_bonds-21.csv
git commit -m "Add green bonds CSV data"
git push origin main
```

**If CSV file is missing**:

1. Check if data is already in database:
   ```bash
   python manage.py shell
   >>> from data_ingestion.models import GreenBond
   >>> GreenBond.objects.count()
   ```

2. If you have data (count > 0), you're good! ✅
3. If no data (count = 0), you need to find the CSV file or obtain it again

### For Production Deployment

1. ✅ **GDAL**: Skip installation (not needed)
2. ✅ **CSV**: Upload to server and load once
3. ✅ **Database**: Data persists after loading
4. ✅ **Environment**: Configure `.env` on server

---

## Questions Answered

### Q: Where did I call these files in old location to change the new file location?

**A**: 
- **GDAL**: Only in `requirements.txt` as a comment (no code change needed)
- **CSV**: In `load_cbi_bonds.py` as a command-line argument (no code change needed)

**No code changes required!** ✅ Both files are referenced correctly.

### Q: How do these files work when hosting?

**A**:
- **GDAL**: Not needed for hosting at all ❌
- **CSV**: Load once during deployment, data persists in PostgreSQL database ✅

### Q: Should I move both files to GreenLens folder?

**A**:
- **GDAL**: ❌ NO - Keep in Downloads
- **CSV**: ✅ YES - Move to `data/` folder (if you can find it)

---

## Next Steps

1. **Check if CSV file exists**:
   ```bash
   dir "C:\Users\sharu\Downloads\green*.csv"
   dir "C:\Users\sharu\Desktop\green*.csv"
   dir "C:\Users\sharu\Documents\green*.csv"
   ```

2. **If found, move to data folder**:
   ```bash
   move "path\to\green_bonds-21.csv" "C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens\data\green_bonds-21.csv"
   ```

3. **If not found, check database**:
   ```bash
   python manage.py shell
   >>> from data_ingestion.models import GreenBond
   >>> print(f"Bonds in database: {GreenBond.objects.count()}")
   ```

4. **For production deployment**:
   - See `DEPLOYMENT_GUIDE.md` for complete instructions
   - GDAL is NOT needed
   - CSV is loaded once, data persists in database

---

**Last Updated**: May 13, 2026  
**Status**: Ready for production deployment ✅
