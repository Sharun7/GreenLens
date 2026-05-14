# Final Step: Load Data in Render

## ✅ What's Done

1. ✅ CSV file moved to `data/green_bonds-21.csv`
2. ✅ `.gitignore` updated to allow CSV
3. ✅ CSV committed to Git
4. ✅ CSV pushed to GitHub
5. ✅ Render is auto-deploying now

---

## 🚀 Final Step: Load Data in Render Shell

### Wait for Deployment to Complete

1. Go to: https://dashboard.render.com
2. Click on your `greenlens` web service
3. Wait for the deployment to finish (you'll see "Live" status)

### Open Render Shell

1. Click the **"Shell"** button (top right)
2. A terminal will open

### Run These Commands

```bash
# 1. Check if CSV file exists
ls -la data/green_bonds-21.csv

# 2. Check current bond count (should be 0)
python manage.py shell -c "from data_ingestion.models import GreenBond; print(f'Bonds before: {GreenBond.objects.count()}')"

# 3. Load the CSV data
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv

# 4. Verify data loaded
python manage.py shell -c "from data_ingestion.models import GreenBond; print(f'Bonds after: {GreenBond.objects.count()}')"
```

### Expected Output

```
Bonds before: 0
Read 1345 rows from green_bonds-21.csv
Country-level issuance rows: 1345
Bond records to process: 1345
Geocoding countries … (1 req/sec, cached per country)
-- Summary ------------------------------
  Created        : 1345
  Updated        : 0
  Geocode fails  : 0
  Skipped        : 0
  Errors         : 0
-----------------------------------------
Bonds after: 1345
```

---

## 🎉 Verify Your Website

After loading data, visit these URLs:

### 1. Homepage
**URL**: https://greenlens-97d0.onrender.com/

**Expected**: Dashboard with bond statistics, map, charts

### 2. Admin Panel
**URL**: https://greenlens-97d0.onrender.com/admin/

**Expected**: Django admin login

**Create superuser if needed**:
```bash
python manage.py createsuperuser
```

### 3. API Documentation
**URL**: https://greenlens-97d0.onrender.com/api/docs/

**Expected**: Swagger API documentation

### 4. AI Predictions
**URL**: https://greenlens-97d0.onrender.com/ai/predictions/

**Expected**: MLP neural network predictions dashboard

### 5. Regulatory Monitor
**URL**: https://greenlens-97d0.onrender.com/ai/regulatory/

**Expected**: Real-time regulatory updates

### 6. Alerts Feed
**URL**: https://greenlens-97d0.onrender.com/ai/alerts/

**Expected**: Regulatory alerts connected to bonds

---

## 📊 What You Should See

After loading data, your website will show:

- ✅ **1,345 green bonds** from IMF/Refinitiv dataset
- ✅ **Interactive map** with bond locations
- ✅ **Risk scores** calculated by XGBoost
- ✅ **Climate predictions** from MLP neural network
- ✅ **Regulatory monitoring** from EU SFDR and SEBI
- ✅ **Pricing analysis** with Yahoo Finance data
- ✅ **Greenwash detection** with satellite imagery
- ✅ **SHAP explainability** for each bond

---

## 🐛 Troubleshooting

### If CSV file not found

```bash
# Check if file exists
ls -la data/

# If not there, wait for deployment to complete
# Render is still deploying the new code
```

### If load command fails

```bash
# Check migrations
python manage.py showmigrations

# Run migrations if needed
python manage.py migrate
```

### If website still blank

```bash
# Check bond count
python manage.py shell -c "from data_ingestion.models import GreenBond; print(GreenBond.objects.count())"

# If 0, run load command again
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

### Check Logs

1. Go to Render Dashboard
2. Click on `greenlens` web service
3. Click **"Logs"** tab
4. Look for any errors

---

## 📝 Summary

**Status**: CSV file deployed ✅

**Next**: Load data in Render Shell

**Time**: 5-10 minutes

**Result**: Fully working website with 1,345 bonds!

---

## 🎯 Quick Commands (Copy-Paste)

```bash
# All commands in one block
ls -la data/green_bonds-21.csv
python manage.py shell -c "from data_ingestion.models import GreenBond; print(f'Before: {GreenBond.objects.count()}')"
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
python manage.py shell -c "from data_ingestion.models import GreenBond; print(f'After: {GreenBond.objects.count()}')"
```

---

**Last Updated**: May 14, 2026  
**Status**: Ready to load data in Render Shell
