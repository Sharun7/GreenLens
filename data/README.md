# Data Folder

This folder contains data files used by GreenLens.

## Files

### green_bonds-21.csv (Required for Initial Setup)

**Purpose**: Initial bond data to load into the database

**Source**: IMF/Refinitiv green bond dataset

**Size**: ~1-5 MB (varies by version)

**Usage**:
```bash
python manage.py load_cbi_bonds --file=data/green_bonds-21.csv
```

**Note**: This file is excluded from Git (see `.gitignore`). You need to:
1. Download or obtain the CSV file separately
2. Place it in this `data/` folder
3. Run the management command above to load it into your database

### Other Subdirectories

- `eurosat_greenlens/` - Satellite imagery cache
- `gee_cache/` - Google Earth Engine data cache

## For Production Deployment

When deploying to production:

1. **Option A**: Upload CSV file to your server and run the load command once
2. **Option B**: Export your local database and import to production
3. **Option C**: Store CSV in cloud storage (S3, GCS) and download during deployment

See `DEPLOYMENT_GUIDE.md` in the root folder for detailed instructions.
