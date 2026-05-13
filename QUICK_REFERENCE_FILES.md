# Quick Reference: GDAL & CSV Files

## TL;DR (Too Long; Didn't Read)

### GDAL Wheel File
- ❌ **Don't move it** - Keep in Downloads
- ❌ **Don't commit it** - Not needed for Git
- ❌ **Don't install on production** - Not needed for hosting
- ✅ **Leave it alone** - It's fine where it is

### Green Bonds CSV File
- ✅ **Data already loaded** - 1,345 bonds in database
- ⚠️ **CSV file optional** - Data persists in database
- ✅ **For production** - Export database or load CSV once
- ✅ **No code changes needed** - Implementation is correct

---

## Your 3 Questions - Quick Answers

### 1. Where did I call these files in old location?

**GDAL**: `requirements.txt` (line 14-17) - Just a comment, not code

**CSV**: `load_cbi_bonds.py` (line 19) - Command-line argument, not hardcoded

**Result**: ✅ No code changes needed!

### 2. Should I move both files to GreenLens folder?

**GDAL**: ❌ NO - Leave in Downloads

**CSV**: ⚠️ OPTIONAL - Data already in database

**Result**: ✅ No action required!

### 3. How do these files work during hosting?

**GDAL**: ❌ Not needed - PostGIS handles spatial data

**CSV**: ✅ Load once - Data persists in database

**Result**: ✅ Production ready!

---

## File Status

```
GDAL-3.11.4-cp311-cp311-win_amd64.whl
├─ Location: Downloads
├─ Move to project? NO
├─ Commit to Git? NO
├─ Needed for hosting? NO
└─ Action: NONE ✅

green_bonds-21.csv
├─ Location: Already loaded in database
├─ Database records: 1,345 bonds ✅
├─ Move to project? OPTIONAL
├─ Commit to Git? OPTIONAL
├─ Needed for hosting? YES (load once)
└─ Action: Export database for production ✅
```

---

## Production Deployment (3 Steps)

### Step 1: Export Database
```bash
pg_dump greenlens_db > greenlens_backup.sql
```

### Step 2: Deploy Code
```bash
git clone https://github.com/Sharun7/GreenLens.git
cd GreenLens
pip install -r requirements.txt  # Skip GDAL!
```

### Step 3: Import Database
```bash
python manage.py migrate
psql production_db < greenlens_backup.sql
gunicorn greenlens.wsgi:application --bind 0.0.0.0:8000
```

---

## What You DON'T Need to Do

❌ Move GDAL to project folder  
❌ Commit GDAL to Git  
❌ Install GDAL on production  
❌ Change any code  
❌ Reload CSV file daily  
❌ Worry about file paths  

---

## What You DO Need to Do

✅ Export database for production  
✅ Configure .env on server  
✅ Run migrations on production  
✅ Import database on production  
✅ Start Celery workers  

---

## Documentation Files

1. **DEPLOYMENT_GUIDE.md** - Complete deployment instructions
2. **FILE_LOCATIONS_SUMMARY.md** - Detailed file handling guide
3. **TASK_12_COMPLETE.md** - Full task summary
4. **data/README.md** - Data folder documentation
5. **QUICK_REFERENCE_FILES.md** - This file (quick reference)

---

## Need Help?

**Email**: sharuntomy7@gmail.com  
**GitHub**: https://github.com/Sharun7/GreenLens  
**LinkedIn**: https://www.linkedin.com/in/sharun-tomy-5ba872271

---

**Last Updated**: May 13, 2026  
**Status**: ✅ Production Ready
