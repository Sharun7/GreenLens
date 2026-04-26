-- ============================================================
-- GreenLens — PostgreSQL + PostGIS database setup
-- Run as a superuser: psql -U postgres -f setup_db.sql
-- ============================================================

-- 1. Create role
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'greenlens_user') THEN
    CREATE ROLE greenlens_user WITH LOGIN PASSWORD 'Deadpool7@';
  END IF;
END
$$;

-- 2. Create database
SELECT 'CREATE DATABASE greenlens_db OWNER greenlens_user'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'greenlens_db')\gexec

-- 3. Grant privileges
GRANT ALL PRIVILEGES ON DATABASE greenlens_db TO greenlens_user;

-- 4. Connect and enable extensions
\connect greenlens_db

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;

-- Grant schema usage to app user
GRANT ALL ON SCHEMA public TO greenlens_user;
GRANT ALL ON SCHEMA topology TO greenlens_user;

-- 5. Verify
SELECT PostGIS_Full_Version();
