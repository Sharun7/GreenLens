# Quick Fix: Load Data to Render

## Problem
Website https://greenlens-97d0.onrender.com/ is blank because **database is empty**.

## Solution (Choose ONE)

### Option 1: Export Local Database and Import to Render (EASIEST)

Since your local project has 1,345 bonds, export and import:

#### Step 1: Export Local Database
```bash
# On your local machine
pg_dump greenlens_db > greenlens_backup.sql
```

#### Step 2: Import to Render
```bash
# Use the DATABASE_URL from your Render environment variables
psql "postgresql://greenlens:dkMnvnkHPDMAn3/dUAnjZ4Z79Ybp01YJadpg-d82Gv19j2pic739kBkj0-a/greenlens" < greenlens_backup.sql
```

#### Step 3: Restart Render Service
- Go to Render Dashboard
- Click "Manual Deploy" → "Clear build cache & deploy"

---

### Option 2: Use Render Shell to Load Data

#### Step 1: Go to Render Dashboard
- Visit: https://dashboard.render.com
- Click on `greenlens` web service
- Click **"Shell"** button

#### Step 2: Check Current State
```bash
# Check if migrations ran
python manage.py showmigrations

# Check bond count
python manage.py shell -c "from data_ingestion.models import GreenBond; print(f'Bonds: {GreenBond.objects.count()}')"
```

#### Step 3: Create Superuser
```bash
python manage.py createsuperuser
# Username: admin
# Email: your@email.com
# Password: (choose a strong password)
```

#### Step 4: Add Data via Admin
- Visit: https://greenlens-97d0.onrender.com/admin/
- Login with superuser
- Add some test bonds manually

---

### Option 3: Add CSV to Git and Deploy

#### Step 1: Find Your CSV File
The CSV file should be at:
```
C:\Users\sharu\Downloads\green_bonds-21.csv
```

#### Step 2: Copy to Project
```bash
copy "C:\Users\sharu\Downloads\green_bonds-21.csv" "C:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens\data\green_bonds-21.csv"
```

#### Step 3: Update .gitignore
Edit `.gitignore` and comment out this line:
```
# data/*.csv  ← Add # to comment out
```

#### Step 4: Push to GitHub
```bash
git add data/green_bonds-21.csv .gitignore
git commit -m "Add CSV data for deployment"
git push
```

#### Step 5: Load Data in Render Shell
After deployment completes:
- Open Render Shell
- Run:
```bash
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

---

## Verify It Works

After loading data, visit:
- **Homepage**: https://greenlens-97d0.onrender.com/
- **Admin**: https://greenlens-97d0.onrender.com/admin/
- **API Docs**: https://greenlens-97d0.onrender.com/api/docs/

You should see:
- ✅ Dashboard with bond data
- ✅ Statistics and charts
- ✅ Map with locations
- ✅ AI predictions

---

## Why This Happened

Your local database has 1,345 bonds, but Render's database is empty because:
1. CSV file is in `.gitignore` (not pushed to GitHub)
2. Render deployed the code but has no data
3. The `build.sh` script doesn't load data automatically

---

## All Your Code is Deployed ✅

Everything is working correctly:
- ✅ Python 3.11
- ✅ Django 5.0.6
- ✅ All dependencies installed
- ✅ Database connected
- ✅ Migrations ran
- ✅ Static files collected
- ✅ Environment variables set

**Only missing**: Data in the database!

---

## Recommended: Option 1 (Export/Import)

This is the fastest and easiest method because:
- Your local database already has all 1,345 bonds
- One command to export
- One command to import
- No need to modify code or push changes

---

## Need Help?

If you get stuck, check:
1. **Render Logs**: Dashboard → greenlens → Logs
2. **Database Connection**: Verify DATABASE_URL is set
3. **Migrations**: Run `python manage.py showmigrations` in Shell

---

**Status**: Code deployed ✅ | Data missing ❌  
**Fix Time**: 5-10 minutes
