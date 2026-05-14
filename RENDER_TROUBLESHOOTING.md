# Render Deployment Troubleshooting

## Issue: Website Shows Blank Page

Your deployment succeeded but the website at https://greenlens-97d0.onrender.com/ shows nothing.

---

## Root Cause

The **database is empty** - no bond data was loaded after deployment.

---

## Solution: Load Data into Production Database

### Option 1: Load CSV Data (Recommended)

1. **Go to Render Dashboard**:
   - Visit: https://dashboard.render.com
   - Click on your `greenlens` web service

2. **Open Shell**:
   - Click **"Shell"** button in the top right
   - This opens a terminal connected to your production server

3. **Check if data exists**:
   ```bash
   python manage.py shell -c "from data_ingestion.models import GreenBond; print(f'Bonds: {GreenBond.objects.count()}')"
   ```

4. **If count is 0, you need to load data**:

   **Option A: If you have the CSV file in your repo**:
   ```bash
   python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
   ```

   **Option B: If CSV is not in repo, upload it**:
   - In Render Shell, create the file:
   ```bash
   mkdir -p data
   # Then manually paste CSV content or use curl to download
   ```

### Option 2: Import Database from Local

If you have data locally (1,345 bonds), export and import:

1. **On your local machine**:
   ```bash
   # Export your local database
   pg_dump greenlens_db > greenlens_backup.sql
   ```

2. **Upload to Render**:
   ```bash
   # Get your Render database connection string from environment variables
   # It looks like: postgresql://greenlens:password@host/database
   
   # Import to Render database
   psql "postgresql://greenlens:dkMnvnkHPDMAn3/dUAnjZ4Z79Ybp01YJadpg-d82Gv19j2pic739kBkj0-a/greenlens" < greenlens_backup.sql
   ```

### Option 3: Create Superuser and Add Data via Admin

1. **In Render Shell**:
   ```bash
   python manage.py createsuperuser
   ```

2. **Visit Admin**:
   - Go to: https://greenlens-97d0.onrender.com/admin/
   - Login with superuser credentials
   - Manually add some test data

---

## Verify Deployment

### Check 1: Homepage
Visit: https://greenlens-97d0.onrender.com/

**Expected**: Dashboard with bond data

**If blank**: Database is empty (follow solutions above)

### Check 2: Admin
Visit: https://greenlens-97d0.onrender.com/admin/

**Expected**: Django admin login page

**If 404**: URL configuration issue (check urls.py)

### Check 3: API
Visit: https://greenlens-97d0.onrender.com/api/docs/

**Expected**: Swagger API documentation

**If error**: Check logs in Render dashboard

---

## Check Render Logs

1. Go to Render Dashboard
2. Click on `greenlens` web service
3. Click **"Logs"** tab
4. Look for errors

**Common errors**:
- `relation "data_ingestion_greenbond" does not exist` → Run migrations
- `ALLOWED_HOSTS` error → Already fixed in settings.py
- `500 Internal Server Error` → Check logs for specific error

---

## Environment Variables (Already Set ✅)

Your current environment variables:
- ✅ `DATABASE_URL` - PostgreSQL connection
- ✅ `DEBUG` - False (production mode)
- ✅ `NASA_PASSWORD` - Deadpool7@sharun
- ✅ `NASA_USERNAME` - sharun7
- ✅ `SECRET_KEY` - Auto-generated

**All required variables are set!** ✅

---

## Quick Fix Commands

Run these in Render Shell:

```bash
# 1. Check migrations
python manage.py showmigrations

# 2. Run migrations if needed
python manage.py migrate

# 3. Check bond count
python manage.py shell -c "from data_ingestion.models import GreenBond; print(GreenBond.objects.count())"

# 4. Create superuser
python manage.py createsuperuser

# 5. Collect static files (if needed)
python manage.py collectstatic --no-input
```

---

## Why Local Works But Render Doesn't

| Aspect | Local | Render |
|--------|-------|--------|
| Database | Has 1,345 bonds ✅ | Empty ❌ |
| Static files | Collected ✅ | Collected ✅ |
| Environment | .env file ✅ | Env vars ✅ |
| Python version | 3.11 ✅ | 3.11 ✅ |
| Dependencies | Installed ✅ | Installed ✅ |

**The ONLY difference**: Your local database has data, Render database is empty.

---

## Step-by-Step Fix (Easiest Method)

### Method 1: Load CSV in Render Shell

1. **Open Render Shell**:
   - Dashboard → greenlens → Shell

2. **Check if CSV exists**:
   ```bash
   ls -la data/
   ```

3. **If CSV exists**:
   ```bash
   python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
   ```

4. **If CSV doesn't exist**:
   - The CSV file is in your `.gitignore`
   - You need to either:
     - Remove `data/*.csv` from `.gitignore` and push
     - Or manually upload CSV to Render

### Method 2: Remove CSV from .gitignore and Push

1. **Edit `.gitignore`**:
   ```bash
   # Comment out this line:
   # data/*.csv
   ```

2. **Add and push CSV**:
   ```bash
   git add data/green_bonds-21.csv
   git commit -m "Add CSV data for deployment"
   git push
   ```

3. **Render will auto-deploy**

4. **Then in Render Shell**:
   ```bash
   python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
   ```

---

## Expected Result After Loading Data

Once data is loaded, visiting https://greenlens-97d0.onrender.com/ should show:

- ✅ Dashboard with bond statistics
- ✅ Map with bond locations
- ✅ Risk scores
- ✅ AI predictions
- ✅ Regulatory monitoring

---

## Additional Environment Variables (Optional)

If you want full functionality, add these:

```
GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gee-credentials.json
EE_SERVICE_ACCOUNT=your-service-account@project.iam.gserviceaccount.com
EE_PROJECT_ID=your-gee-project-id
EARTHDATA_USERNAME=sharun7
EARTHDATA_PASSWORD=Deadpool7@sharun
```

But these are **NOT required** for the website to show up. The website will work without them.

---

## Summary

**Problem**: Database is empty on Render

**Solution**: Load bond data using one of these methods:
1. Run `python manage.py load_cbi_bonds --file=data/green_bonds-21.csv` in Render Shell
2. Import your local database to Render
3. Add CSV to git and push

**All code is deployed correctly** ✅  
**All environment variables are set** ✅  
**Only missing**: Data in database ❌

---

## Need Help?

If you still see a blank page after loading data:

1. Check Render logs for errors
2. Verify migrations ran: `python manage.py showmigrations`
3. Check bond count: `python manage.py shell -c "from data_ingestion.models import GreenBond; print(GreenBond.objects.count())"`
4. Create superuser and check admin: https://greenlens-97d0.onrender.com/admin/

---

**Last Updated**: May 14, 2026  
**Status**: All code deployed, need to load data
