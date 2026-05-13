# GreenLens Deployment Guide

## Overview

This guide explains how to deploy GreenLens to production, including handling of data files and dependencies.

---

## 1. GDAL Library (Windows Development Only)

### What is it?

`GDAL-3.11.4-cp311-cp311-win_amd64.whl` is a pre-compiled GDAL library for Windows Python 3.11.

### Where is it referenced?

- **requirements.txt** (lines 14-17) - Installation instructions only
- **NOT hardcoded in any Python file** ✅

### Important Notes

❌ **DO NOT move this file to the GreenLens folder**  
❌ **DO NOT commit this file to GitHub** (it's 20+ MB and Windows-specific)  
✅ **Keep it in Downloads or a separate folder**

### Local Installation (Windows Only)

```bash
# Install GDAL wheel file
pip install C:\Users\sharu\Downloads\GDAL-3.11.4-cp311-cp311-win_amd64.whl
```

### For Production Hosting

**GDAL is NOT needed for production!** Here's why:

1. ✅ **PostGIS handles spatial data**: Your production database (PostgreSQL + PostGIS) handles all spatial operations
2. ✅ **Django doesn't use GDAL**: Your `settings.py` uses `django.db.backends.postgresql` (NOT `django.contrib.gis`)
3. ✅ **No spatial queries**: Your models don't use `PointField` or other GIS fields that require GDAL

**Conclusion**: GDAL is optional for local development, but **NOT required for production hosting**.

---

## 2. Green Bonds CSV File

### What is it?

`green_bonds-21.csv` contains initial bond data from IMF/Refinitiv dataset.

### Where is it referenced?

- `data_ingestion/management/commands/load_cbi_bonds.py` (line 19, 21, 23, 256)

### Current Usage (Correct Implementation ✅)

```python
# In load_cbi_bonds.py
parser.add_argument("--file", required=True, help="Path to green_bonds-21.csv")
```

**This is CORRECT!** The file path is passed as a command-line argument, not hardcoded.

### Recommended Location

```
GreenLens/
├── data/
│   ├── green_bonds-21.csv    # Place CSV here
│   ├── eurosat_greenlens/
│   └── gee_cache/
├── ai_features/
└── ...
```

### How to Use

```bash
# Load bonds from data folder
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

### For Production Deployment

Choose one of these options:

#### Option A: Load CSV During Deployment (Recommended)

```bash
# 1. Upload CSV to production server (via SCP, FTP, or cloud storage)
scp data/green_bonds-21.csv user@server:/app/data/

# 2. On production server, run the load command once
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

#### Option B: Database Dump/Restore

```bash
# On local machine: Export database
pg_dump greenlens_db > greenlens_backup.sql

# On production server: Import database
psql production_db < greenlens_backup.sql
```

#### Option C: Cloud Storage

```bash
# 1. Upload CSV to AWS S3, Google Cloud Storage, or Azure Blob
aws s3 cp data/green_bonds-21.csv s3://your-bucket/data/

# 2. In deployment script, download and load
aws s3 cp s3://your-bucket/data/green_bonds-21.csv data/
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

---

## 3. Production Deployment Steps

### Prerequisites

1. ✅ PostgreSQL database with PostGIS extension
2. ✅ Redis server (for Celery tasks)
3. ✅ Python 3.11+
4. ✅ Environment variables configured (see `.env.example`)

### Step-by-Step Deployment

#### Step 1: Clone Repository

```bash
git clone https://github.com/Sharun7/GreenLens.git
cd GreenLens
```

#### Step 2: Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python packages
pip install -r requirements.txt
```

**Note**: Skip the GDAL wheel installation on production. It's not needed!

#### Step 3: Configure Environment Variables

```bash
# Copy example file
cp .env.example .env

# Edit .env with your production values
nano .env
```

Required variables:
- `SECRET_KEY` - Django secret key
- `DEBUG=False` - Disable debug mode
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to GEE credentials
- `NASA_USERNAME` and `NASA_PASSWORD` - NASA Earthdata credentials

#### Step 4: Run Database Migrations

```bash
python manage.py migrate
```

#### Step 5: Load Initial Bond Data

```bash
# Upload CSV file to server first, then:
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

#### Step 6: Collect Static Files

```bash
python manage.py collectstatic --noinput
```

#### Step 7: Start Celery Workers (Background Tasks)

```bash
# Terminal 1: Celery worker
celery -A greenlens worker -l info

# Terminal 2: Celery beat (scheduled tasks)
celery -A greenlens beat -l info
```

#### Step 8: Start Django Server

```bash
# Development server
python manage.py runserver 0.0.0.0:8000

# Production server (use Gunicorn)
gunicorn greenlens.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

---

## 4. Platform-Specific Deployment

### Render.com (Recommended)

**Pros**:
- ✅ Free PostgreSQL database with PostGIS
- ✅ Automatic deployments from GitHub
- ✅ No GDAL needed
- ✅ Built-in Redis support

**Setup**:

1. **Create New Web Service**
   - Connect GitHub repository: `https://github.com/Sharun7/GreenLens`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn greenlens.wsgi:application`

2. **Add PostgreSQL Database**
   - Go to Dashboard → New → PostgreSQL
   - Copy `DATABASE_URL` to environment variables

3. **Add Redis Instance**
   - Go to Dashboard → New → Redis
   - Copy `REDIS_URL` to environment variables

4. **Set Environment Variables**
   - Add all variables from `.env.example`
   - Set `DEBUG=False`
   - Set `ALLOWED_HOSTS=your-app.onrender.com`

5. **Run Initial Setup Commands**
   ```bash
   # In Render Shell
   python manage.py migrate
   python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
   python manage.py collectstatic --noinput
   ```

6. **Add Background Workers**
   - Create new Background Worker service
   - Start Command: `celery -A greenlens worker -l info`
   - Create another for Beat: `celery -A greenlens beat -l info`

### Heroku

**Pros**:
- ✅ PostgreSQL with PostGIS addon
- ✅ No GDAL needed
- ✅ Easy deployment

**Setup**:

```bash
# Install Heroku CLI
# https://devcenter.heroku.com/articles/heroku-cli

# Login and create app
heroku login
heroku create greenlens

# Add PostgreSQL with PostGIS
heroku addons:create heroku-postgresql:mini
heroku pg:psql -c "CREATE EXTENSION postgis;"

# Add Redis
heroku addons:create heroku-redis:mini

# Set environment variables
heroku config:set SECRET_KEY=your-secret-key
heroku config:set DEBUG=False
heroku config:set GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
# ... add all other variables from .env.example

# Deploy
git push heroku main

# Run migrations
heroku run python manage.py migrate

# Load bond data (upload CSV first)
heroku run python manage.py load_cbi_bonds --file=data/green_bonds-21.csv

# Start Celery workers
heroku ps:scale worker=1
heroku ps:scale beat=1
```

### AWS / DigitalOcean / VPS

**Pros**:
- ✅ Full control
- ✅ Scalable
- ✅ Custom configuration

**Cons**:
- ⚠️ More setup required
- ⚠️ Need to configure PostgreSQL + PostGIS manually

**Setup**:

1. **Provision Server**
   - Ubuntu 22.04 LTS recommended
   - Minimum: 2 GB RAM, 2 vCPUs

2. **Install Dependencies**
   ```bash
   sudo apt update
   sudo apt install -y python3.11 python3-pip postgresql postgresql-contrib postgis redis-server nginx
   ```

3. **Configure PostgreSQL**
   ```bash
   sudo -u postgres psql
   CREATE DATABASE greenlens_db;
   CREATE USER greenlens WITH PASSWORD 'your-password';
   ALTER ROLE greenlens SET client_encoding TO 'utf8';
   ALTER ROLE greenlens SET default_transaction_isolation TO 'read committed';
   ALTER ROLE greenlens SET timezone TO 'UTC';
   GRANT ALL PRIVILEGES ON DATABASE greenlens_db TO greenlens;
   \c greenlens_db
   CREATE EXTENSION postgis;
   \q
   ```

4. **Deploy Application**
   ```bash
   cd /var/www
   git clone https://github.com/Sharun7/GreenLens.git
   cd GreenLens
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Configure Nginx**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }

       location /static/ {
           alias /var/www/GreenLens/staticfiles/;
       }
   }
   ```

6. **Setup Systemd Services**
   
   Create `/etc/systemd/system/greenlens.service`:
   ```ini
   [Unit]
   Description=GreenLens Django Application
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/GreenLens
   Environment="PATH=/var/www/GreenLens/venv/bin"
   ExecStart=/var/www/GreenLens/venv/bin/gunicorn greenlens.wsgi:application --bind 127.0.0.1:8000 --workers 4

   [Install]
   WantedBy=multi-user.target
   ```

   Create `/etc/systemd/system/greenlens-celery.service`:
   ```ini
   [Unit]
   Description=GreenLens Celery Worker
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/GreenLens
   Environment="PATH=/var/www/GreenLens/venv/bin"
   ExecStart=/var/www/GreenLens/venv/bin/celery -A greenlens worker -l info

   [Install]
   WantedBy=multi-user.target
   ```

   Enable and start services:
   ```bash
   sudo systemctl enable greenlens greenlens-celery
   sudo systemctl start greenlens greenlens-celery
   ```

---

## 5. Post-Deployment Checklist

### Security

- [ ] Set `DEBUG=False` in production
- [ ] Configure `ALLOWED_HOSTS` with your domain
- [ ] Use strong `SECRET_KEY` (generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- [ ] Enable HTTPS/SSL certificate
- [ ] Set secure cookie flags in `settings.py`
- [ ] Configure CORS if needed

### Database

- [ ] Run migrations: `python manage.py migrate`
- [ ] Load bond data: `python manage.py load_cbi_bonds --file=data/green_bonds-21.csv`
- [ ] Create superuser: `python manage.py createsuperuser`
- [ ] Set up database backups

### Background Tasks

- [ ] Start Celery worker
- [ ] Start Celery beat (scheduled tasks)
- [ ] Verify tasks are running: check `/admin/django_celery_beat/`

### Monitoring

- [ ] Set up error tracking (Sentry, Rollbar)
- [ ] Configure logging
- [ ] Set up uptime monitoring
- [ ] Monitor Celery task queue

### Performance

- [ ] Collect static files: `python manage.py collectstatic`
- [ ] Configure CDN for static files (optional)
- [ ] Enable database connection pooling
- [ ] Set up Redis caching

---

## 6. Common Issues & Solutions

### Issue: "GDAL not found" error

**Solution**: GDAL is NOT needed for production. If you see this error:
1. Check that you're using `django.db.backends.postgresql` (not `django.contrib.gis.db.backends.postgis`)
2. Ensure PostGIS extension is enabled in your database
3. Remove any GDAL-specific code from your models

### Issue: CSV file not found during deployment

**Solution**: 
1. Upload CSV file to production server
2. Place it in `data/` folder
3. Run: `python manage.py load_cbi_bonds --file=data/green_bonds-21.csv`

### Issue: Celery tasks not running

**Solution**:
1. Check Redis connection: `redis-cli ping`
2. Verify Celery worker is running: `celery -A greenlens inspect active`
3. Check Celery logs for errors

### Issue: Static files not loading

**Solution**:
1. Run: `python manage.py collectstatic --noinput`
2. Configure web server (Nginx/Apache) to serve `/static/` directory
3. Or use WhiteNoise middleware (already configured in `settings.py`)

---

## 7. Environment Variables Reference

See `.env.example` for complete list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ Yes | Django secret key |
| `DEBUG` | ✅ Yes | Set to `False` in production |
| `DATABASE_URL` | ✅ Yes | PostgreSQL connection string |
| `REDIS_URL` | ✅ Yes | Redis connection string |
| `ALLOWED_HOSTS` | ✅ Yes | Comma-separated list of domains |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✅ Yes | Path to GEE credentials JSON |
| `NASA_USERNAME` | ✅ Yes | NASA Earthdata username |
| `NASA_PASSWORD` | ✅ Yes | NASA Earthdata password |
| `EMAIL_HOST` | ⚠️ Optional | SMTP server for emails |
| `EMAIL_PORT` | ⚠️ Optional | SMTP port (default: 587) |
| `EMAIL_HOST_USER` | ⚠️ Optional | SMTP username |
| `EMAIL_HOST_PASSWORD` | ⚠️ Optional | SMTP password |

---

## 8. Maintenance

### Database Backups

```bash
# Backup database
pg_dump greenlens_db > backup_$(date +%Y%m%d).sql

# Restore database
psql greenlens_db < backup_20260513.sql
```

### Update Application

```bash
# Pull latest code
git pull origin main

# Install new dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Restart services
sudo systemctl restart greenlens greenlens-celery
```

### Monitor Logs

```bash
# Django logs
tail -f logs/django.log

# Celery logs
tail -f logs/celery.log

# Nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

---

## 9. Summary

### Files to Handle

| File | Location | Commit to Git? | Needed for Production? |
|------|----------|----------------|------------------------|
| `GDAL-*.whl` | Downloads | ❌ NO | ❌ NO |
| `green_bonds-21.csv` | `data/` | ⚠️ Optional | ✅ YES (load once) |
| `.env` | Root | ❌ NO | ✅ YES (create on server) |
| `credentials.json` | Root | ❌ NO | ✅ YES (upload to server) |

### Key Points

1. ✅ **GDAL is NOT needed for production** - PostGIS handles spatial data
2. ✅ **CSV file path is NOT hardcoded** - passed as command-line argument
3. ✅ **Load CSV once during deployment** - data persists in database
4. ✅ **Use environment variables** - never hardcode secrets
5. ✅ **Run Celery workers** - required for background tasks

### Quick Start (Production)

```bash
# 1. Clone and install
git clone https://github.com/Sharun7/GreenLens.git
cd GreenLens
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
nano .env  # Edit with your values

# 3. Setup database
python manage.py migrate
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv

# 4. Start services
gunicorn greenlens.wsgi:application --bind 0.0.0.0:8000 --workers 4 &
celery -A greenlens worker -l info &
celery -A greenlens beat -l info &
```

---

## 10. Support

For issues or questions:
- **Email**: sharuntomy7@gmail.com
- **GitHub**: https://github.com/Sharun7/GreenLens/issues
- **LinkedIn**: https://www.linkedin.com/in/sharun-tomy-5ba872271

---

**Last Updated**: May 13, 2026  
**Version**: 2.0
