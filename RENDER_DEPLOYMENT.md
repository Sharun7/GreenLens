# GreenLens - Render.com Deployment Guide

## ✅ Production Ready

Your GreenLens project is now configured for production deployment on Render.com!

---

## 📋 What Was Configured

### 1. Updated `greenlens/settings.py`

✅ **Added production imports**:
```python
import os
import dj_database_url
```

✅ **Updated DEBUG setting**:
```python
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
```

✅ **Updated ALLOWED_HOSTS**:
```python
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.onrender.com',
    'greenlens.onrender.com',
]
```

✅ **Updated DATABASE configuration**:
```python
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}
```

✅ **Confirmed STATICFILES_STORAGE**:
```python
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

✅ **Confirmed Security settings** (already in place):
```python
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
```

### 2. Created `build.sh`

```bash
#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py train_mlp_model
```

This script runs during deployment to:
- Install Python dependencies
- Collect static files
- Run database migrations
- Train the MLP prediction model

### 3. Created `render.yaml`

Complete infrastructure-as-code configuration with:
- **Web service**: Django app with Gunicorn
- **Celery worker**: Background task processing
- **Celery beat**: Scheduled task execution
- **PostgreSQL database**: greenlens-db
- **Redis**: For Celery broker and caching

---

## 🚀 Deployment Steps

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Configure for Render.com production deployment"
git push origin main
```

### Step 2: Create Render Account

1. Go to https://render.com
2. Sign up with GitHub account
3. Authorize Render to access your repositories

### Step 3: Deploy from Dashboard

#### Option A: Using render.yaml (Recommended)

1. Click **"New +"** → **"Blueprint"**
2. Connect your GitHub repository: `Sharun7/GreenLens`
3. Render will detect `render.yaml` automatically
4. Click **"Apply"**
5. Render will create:
   - Web service (greenlens)
   - 2 Workers (celery, celery-beat)
   - PostgreSQL database
   - Redis instance

#### Option B: Manual Setup

1. **Create PostgreSQL Database**:
   - Click **"New +"** → **"PostgreSQL"**
   - Name: `greenlens-db`
   - Database: `greenlens`
   - User: `greenlens`
   - Plan: Free (or paid for production)

2. **Create Redis Instance**:
   - Click **"New +"** → **"Redis"**
   - Name: `greenlens-redis`
   - Plan: Free (or paid for production)

3. **Create Web Service**:
   - Click **"New +"** → **"Web Service"**
   - Connect repository: `Sharun7/GreenLens`
   - Name: `greenlens`
   - Environment: `Python 3`
   - Build Command: `./build.sh`
   - Start Command: `gunicorn greenlens.wsgi:application`
   - Plan: Free (or paid for production)

4. **Add Environment Variables** (in Web Service settings):
   ```
   DATABASE_URL = [Copy from greenlens-db Internal Database URL]
   REDIS_URL = [Copy from greenlens-redis Internal Redis URL]
   SECRET_KEY = [Generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"]
   DEBUG = False
   NASA_USERNAME = [Your NASA Earthdata username]
   NASA_PASSWORD = [Your NASA Earthdata password]
   GOOGLE_APPLICATION_CREDENTIALS = /etc/secrets/gee-credentials.json
   EE_SERVICE_ACCOUNT = [Your GEE service account email]
   EE_PROJECT_ID = [Your GEE project ID]
   ```

5. **Create Celery Worker**:
   - Click **"New +"** → **"Background Worker"**
   - Connect repository: `Sharun7/GreenLens`
   - Name: `greenlens-celery`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `celery -A greenlens worker --loglevel=info`
   - Add same environment variables as web service

6. **Create Celery Beat Worker**:
   - Click **"New +"** → **"Background Worker"**
   - Connect repository: `Sharun7/GreenLens`
   - Name: `greenlens-celery-beat`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `celery -A greenlens beat --loglevel=info`
   - Add same environment variables as web service

### Step 4: Configure Secrets (Google Earth Engine)

1. In your web service settings, go to **"Secret Files"**
2. Add a new secret file:
   - **Filename**: `/etc/secrets/gee-credentials.json`
   - **Contents**: Paste your Google Earth Engine service account JSON

### Step 5: Load Initial Data

After deployment completes:

1. Go to your web service → **"Shell"**
2. Run:
   ```bash
   python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
   ```

Or, if you prefer to import your local database:

```bash
# On local machine
pg_dump greenlens_db > greenlens_backup.sql

# Upload to Render (use their database connection string)
psql [RENDER_DATABASE_URL] < greenlens_backup.sql
```

### Step 6: Verify Deployment

1. **Check Web Service**:
   - Visit: `https://greenlens.onrender.com`
   - Should see GreenLens homepage

2. **Check Admin**:
   - Visit: `https://greenlens.onrender.com/admin/`
   - Create superuser if needed:
     ```bash
     python manage.py createsuperuser
     ```

3. **Check Celery Workers**:
   - Go to Render Dashboard
   - Check logs for `greenlens-celery` and `greenlens-celery-beat`
   - Should see "ready" messages

4. **Check Background Tasks**:
   - Visit: `https://greenlens.onrender.com/admin/django_celery_beat/periodictask/`
   - Should see scheduled tasks

---

## 🔧 Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DATABASE_URL` | ✅ Yes | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `REDIS_URL` | ✅ Yes | Redis connection string | `redis://host:6379` |
| `SECRET_KEY` | ✅ Yes | Django secret key | Generate with Django |
| `DEBUG` | ✅ Yes | Debug mode (False in production) | `False` |
| `NASA_USERNAME` | ✅ Yes | NASA Earthdata username | Your username |
| `NASA_PASSWORD` | ✅ Yes | NASA Earthdata password | Your password |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✅ Yes | Path to GEE credentials | `/etc/secrets/gee-credentials.json` |
| `EE_SERVICE_ACCOUNT` | ✅ Yes | GEE service account email | `account@project.iam.gserviceaccount.com` |
| `EE_PROJECT_ID` | ✅ Yes | GEE project ID | `your-project-id` |
| `EARTHDATA_USERNAME` | ⚠️ Optional | Alias for NASA_USERNAME | Same as NASA_USERNAME |
| `EARTHDATA_PASSWORD` | ⚠️ Optional | Alias for NASA_PASSWORD | Same as NASA_PASSWORD |

---

## 📊 Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Render.com Services                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐      ┌──────────────┐                     │
│  │  Web Service │      │  PostgreSQL  │                     │
│  │  (Django +   │─────▶│  Database    │                     │
│  │  Gunicorn)   │      │  greenlens-db│                     │
│  └──────┬───────┘      └──────────────┘                     │
│         │                                                     │
│         │              ┌──────────────┐                     │
│         └─────────────▶│    Redis     │◀────────┐          │
│                        │ greenlens-   │         │          │
│                        │   redis      │         │          │
│                        └──────────────┘         │          │
│                                                  │          │
│  ┌──────────────┐                               │          │
│  │Celery Worker │───────────────────────────────┘          │
│  │(Background   │                                           │
│  │   Tasks)     │                                           │
│  └──────────────┘                                           │
│                                                              │
│  ┌──────────────┐                                           │
│  │Celery Beat   │───────────────────────────────────────────┘
│  │(Scheduled    │
│  │   Tasks)     │
│  └──────────────┘
│
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Monitoring & Logs

### View Logs

1. **Web Service Logs**:
   - Go to Render Dashboard → greenlens → Logs
   - Real-time logs of Django application

2. **Celery Worker Logs**:
   - Go to Render Dashboard → greenlens-celery → Logs
   - See background task execution

3. **Celery Beat Logs**:
   - Go to Render Dashboard → greenlens-celery-beat → Logs
   - See scheduled task triggers

### Monitor Performance

1. **Render Metrics**:
   - CPU usage
   - Memory usage
   - Request count
   - Response time

2. **Django Admin**:
   - Visit `/admin/django_celery_results/taskresult/`
   - See Celery task results

3. **Database Metrics**:
   - Go to greenlens-db → Metrics
   - Connection count, query performance

---

## 🐛 Troubleshooting

### Issue: Build fails with "Permission denied: ./build.sh"

**Solution**: Make build.sh executable:
```bash
git update-index --chmod=+x build.sh
git commit -m "Make build.sh executable"
git push origin main
```

### Issue: "SECRET_KEY not found"

**Solution**: Add SECRET_KEY environment variable in Render dashboard:
```bash
# Generate a new secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Issue: Static files not loading

**Solution**: 
1. Check that `STATICFILES_STORAGE` is set correctly in settings.py ✅
2. Verify `python manage.py collectstatic` runs in build.sh ✅
3. Check WhiteNoise middleware is in MIDDLEWARE ✅

### Issue: Database connection fails

**Solution**:
1. Verify `DATABASE_URL` environment variable is set
2. Check PostgreSQL service is running in Render dashboard
3. Verify database name matches in render.yaml

### Issue: Celery tasks not running

**Solution**:
1. Check `REDIS_URL` environment variable is set
2. Verify Redis service is running
3. Check Celery worker logs for errors
4. Ensure Celery beat is running for scheduled tasks

### Issue: Google Earth Engine authentication fails

**Solution**:
1. Verify GEE credentials JSON is uploaded as secret file
2. Check `GOOGLE_APPLICATION_CREDENTIALS` path is correct
3. Verify `EE_SERVICE_ACCOUNT` and `EE_PROJECT_ID` are set

---

## 🔄 Updating Your Deployment

### Deploy New Changes

```bash
# Make your changes
git add .
git commit -m "Your changes"
git push origin main

# Render will automatically deploy the new version
```

### Manual Deploy

1. Go to Render Dashboard → greenlens
2. Click **"Manual Deploy"** → **"Deploy latest commit"**

### Rollback

1. Go to Render Dashboard → greenlens → Events
2. Find previous successful deploy
3. Click **"Rollback to this version"**

---

## 💰 Pricing

### Free Tier (Good for Testing)

- **Web Service**: Free (spins down after 15 min inactivity)
- **PostgreSQL**: Free (90 days, then $7/month)
- **Redis**: Free (90 days, then $7/month)
- **Workers**: Free (750 hours/month)

**Total**: Free for 90 days, then ~$14/month

### Starter Tier (Recommended for Production)

- **Web Service**: $7/month (always on)
- **PostgreSQL**: $7/month (1 GB storage)
- **Redis**: $7/month (25 MB)
- **Workers**: $7/month each × 2 = $14/month

**Total**: ~$35/month

### Pro Tier (High Traffic)

- **Web Service**: $25/month (2 GB RAM)
- **PostgreSQL**: $20/month (10 GB storage)
- **Redis**: $20/month (1 GB)
- **Workers**: $25/month each × 2 = $50/month

**Total**: ~$115/month

---

## 📚 Additional Resources

- **Render Documentation**: https://render.com/docs
- **Django Deployment Checklist**: https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/
- **Celery Documentation**: https://docs.celeryproject.org/
- **GreenLens Documentation**: See `DEPLOYMENT_GUIDE.md`

---

## ✅ Deployment Checklist

Before deploying to production:

- [ ] Push all changes to GitHub
- [ ] Create Render account
- [ ] Deploy using render.yaml or manual setup
- [ ] Add all environment variables
- [ ] Upload Google Earth Engine credentials
- [ ] Load initial bond data
- [ ] Create superuser account
- [ ] Verify web service is running
- [ ] Verify Celery workers are running
- [ ] Test API endpoints
- [ ] Test admin interface
- [ ] Monitor logs for errors
- [ ] Set up custom domain (optional)
- [ ] Configure SSL certificate (automatic on Render)

---

## 🎉 Success!

Once deployed, your GreenLens application will be live at:

**URL**: `https://greenlens.onrender.com`

**Features**:
- ✅ Real-time climate risk scoring
- ✅ Satellite greenwash detection
- ✅ MLP neural network predictions
- ✅ Regulatory monitoring
- ✅ Automatic API health checks
- ✅ Background task processing
- ✅ Scheduled data updates

---

**Last Updated**: May 13, 2026  
**Version**: 2.0  
**Status**: Production Ready ✅
