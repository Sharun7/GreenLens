# Data Files Guide - GDAL & Green Bonds CSV

## Overview

You have two important files that need special handling:

1. **GDAL-3.11.4-cp311-cp311-win_amd64.whl** - GDAL library for Windows
2. **green_bonds-21.csv** - Bond data CSV file

---

## 1. GDAL Wheel File

### Current Status

**File**: `GDAL-3.11.4-cp311-cp311-win_amd64.whl`

**Purpose**: This is a pre-compiled GDAL library for Windows Python 3.11

**Where it's referenced**: 
- `requirements.txt` (lines 14-17) - Installation instructions only
- **NOT hardcoded in any Python file** ✅

### Important Notes

❌ **DO NOT move this file to the GreenLens folder**  
❌ **DO NOT commit this file to GitHub** (it's 20+ MB)  
✅ **Keep it in Downloads or a separate folder**

### Why?

1. **Windows-specific**: This `.whl` file only works on Windows
2. **Large file**: 20+ MB - too big for Git
3. **Platform-dependent**: Different OS needs different GDAL versions

### Installation (Local Development)

```bash
# On Windows (your current setup)
pip install C:\Users\sharu\Downloads\GDAL-3.11.4-cp311-cp311-win_amd64.whl
```

### For Hosting (Production)

**GDAL is NOT needed for hosting!** Here's why:

1. **PostGIS handles spatial data**: Your production database (PostgreSQL + PostGIS) handles all spatial operations
2. **Django doesn't use GDAL**: Your `settings.py` uses `django.db.backends.postgresql` (NOT `django.contrib.gis`)
3. **No spatial queries**: Your models don't use `PointField` or other GIS fields

**Conclusion**: GDAL is optional for local development, but **NOT required for production hosting**.

---

## 2. Green Bonds CSV File

### Current Status

**File**: `green_bonds-21.csv`

**Purpose**: Initial bond data to load into database

**Where it's referenced**:
- `data_ingestion/management/commands/load_cbi_bonds.py` (line 19, 21, 23, 256)

### Current Usage

```python
# In load_cbi_bonds.py
parser.add_argument("--file", required=True, help="Path to green_bonds-21.csv")
```

**This is CORRECT!** ✅ The file path is passed as a command-line argument, not hardcoded.

### Recommended Location

Create a `data/` folder in your project:

```
GreenLens/
├── data/
│   └── green_bonds-21.csv    # Move CSV here
├── ai_features/
├── dashboard/
└── ...
```

### How to Move the File

```bash
# Create data folder
mkdir data

# Move CSV file (from Downloads to project)
move "C:\Users\sharu\Downloads\green_bonds-21.csv" "C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens\data\green_bonds-21.csv"
```

### Update .gitignore

Add this to `.gitignore` to prevent committing large CSV files:

```
# Data files (large CSV files)
data/*.csv
data/*.json
data/*.xlsx
```

### How to Use (After Moving)

```bash
# Load bonds from new location
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

### For Hosting (Production)

**Option 1: Load data once during deployment**

```bash
# On production server (one-time setup)
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

**Option 2: Use database dump/restore**

```bash
# Export from local database
pg_dump greenlens_db > greenlens_backup.sql

# Import to production database
psql production_db < greenlens_backup.sql
```

**Option 3: Store in cloud storage**

- Upload CSV to AWS S3, Google Cloud Storage, or Azure Blob
- Download during deployment
- Load into database

---

## Summary

### GDAL Wheel File

| Question | Answer |
|----------|--------|
| Move to GreenLens folder? | ❌ NO - Keep in Downloads |
| Commit to GitHub? | ❌ NO - Too large, Windows-only |
| Needed for hosting? | ❌ NO - PostGIS handles spatial data |
| How to install locally? | `pip install path/to/GDAL-*.whl` |

### Green Bonds CSV File

| Question | Answer |
|----------|--------|
| Move to GreenLens folder? | ✅ YES - Move to `data/` folder |
| Commit to GitHub? | ⚠️ OPTIONAL - Add to .gitignore if large |
| Needed for hosting? | ✅ YES - Load once during deployment |
| How to use? | `python manage.py load_cbi_bonds --file=data/green_bonds-21.csv` |

---

## Step-by-Step: Prepare for Hosting

### 1. Move CSV File

```bash
# Create data folder
cd "C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens"
mkdir data

# Move CSV
move "C:\Users\sharu\Downloads\green_bonds-21.csv" "data\green_bonds-21.csv"
```

### 2. Update .gitignore

Add to `.gitignore`:

```
# Data files
data/*.csv
data/*.json
data/*.xlsx
```

### 3. GDAL - Do Nothing!

- ✅ Keep GDAL wheel in Downloads
- ✅ Don't move it
- ✅ Don't commit it
- ✅ It's not needed for hosting

### 4. For Production Deployment

**On your hosting platform (Render, Heroku, AWS, etc.):**

```bash
# 1. Deploy your code
git push origin main

# 2. Run migrations
python manage.py migrate

# 3. Load bond data (one-time)
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv

# 4. Start server
python manage.py runserver
```

---

## Hosting Platform Recommendations

### Render.com (Recommended)

**Pros**:
- ✅ Free PostgreSQL database
- ✅ Automatic deployments from GitHub
- ✅ No GDAL needed
- ✅ PostGIS support built-in

**Setup**:
1. Connect GitHub repository
2. Set environment variables from `.env.example`
3. Run build command: `pip install -r requirements.txt`
4. Run migrations: `python manage.py migrate`
5. Load data: `python manage.py load_cbi_bonds --file=data/green_bonds-21.csv`

### Heroku

**Pros**:
- ✅ PostgreSQL with PostGIS addon
- ✅ No GDAL needed
- ✅ Easy deployment

**Setup**:
1. Install Heroku CLI
2. `heroku create greenlens`
3. `heroku addons:create heroku-postgresql:mini`
4. `git push heroku main`
5. `heroku run python manage.py migrate`
6. `heroku run python manage.py load_cbi_bonds --file=data/green_bonds-21.csv`

### AWS / DigitalOcean

**Pros**:
- ✅ Full control
- ✅ Scalable

**Cons**:
- ⚠️ More setup required
- ⚠️ Need to configure PostgreSQL + PostGIS manually

---

## Common Questions

### Q: Do I need GDAL for hosting?

**A**: ❌ NO! Your Django app uses `django.db.backends.postgresql` (not PostGIS), so GDAL is not required.

### Q: Where should I keep the GDAL wheel file?

**A**: Keep it in your Downloads folder or a separate `installers/` folder. Don't move it to the project.

### Q: Should I commit the CSV file to GitHub?

**A**: 
- If CSV is < 10 MB: ✅ YES, commit it to `data/` folder
- If CSV is > 10 MB: ❌ NO, add to `.gitignore` and upload separately during deployment

### Q: How do I load data on production?

**A**: Three options:
1. Run `python manage.py load_cbi_bonds --file=data/green_bonds-21.csv` on production
2. Export local database and import to production
3. Use database fixtures: `python manage.py dumpdata > fixtures.json`

### Q: What if the CSV file is too large for GitHub?

**A**: Use Git LFS (Large File Storage) or store in cloud:

```bash
# Option 1: Git LFS
git lfs track "data/*.csv"
git add .gitattributes
git add data/green_bonds-21.csv
git commit -m "Add bond data with LFS"

# Option 2: Cloud storage
# Upload to AWS S3, Google Cloud Storage, etc.
# Download during deployment
```

---

## Conclusion

### ✅ What to Do

1. **Move CSV to `data/` folder** in your project
2. **Update .gitignore** to exclude large data files
3. **Keep GDAL wheel in Downloads** - don't move it
4. **Don't worry about GDAL for hosting** - it's not needed

### ❌ What NOT to Do

1. ❌ Don't move GDAL wheel to project folder
2. ❌ Don't commit GDAL wheel to GitHub
3. ❌ Don't hardcode file paths in Python code
4. ❌ Don't worry about GDAL for production

### 🚀 Ready for Hosting

Your project is ready for hosting! Just:
1. Push to GitHub (already done ✅)
2. Deploy to Render/Heroku
3. Set environment variables
4. Run migrations
5. Load bond data once
6. Start server

**No GDAL needed for production!** 🎉
