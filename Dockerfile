FROM python:3.11-slim

# System dependencies for GDAL/GeoDjango
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    binutils \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so
ENV GEOS_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgeos_c.so
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations, collect static, then start gunicorn.
# SECRET_KEY and DATABASE_URL must be supplied via --env-file or docker-compose.
CMD sh -c "python manage.py migrate --noinput && \
     python manage.py collectstatic --noinput && \
     gunicorn greenlens.wsgi:application \
       --bind 0.0.0.0:${PORT:-8000} \
       --workers 2 \
       --timeout 120 \
       --access-logfile - \
       --error-logfile -"
