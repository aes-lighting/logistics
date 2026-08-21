# AES Logistics server image
# Serves the driver PWA (/), the PM portal (/pm), and the Flask API.
#
# Build:
#   docker build -t aes-logistics .
#
# Run (see docker-compose.yml for the easier way — this is the raw form):
#   docker run -d -p 5000:5000 \
#     --env-file server/.env \
#     -v aes_logistics_data:/app/server/organized \
#     aes-logistics

FROM python:3.12-slim

# tesseract-ocr: required for reading job numbers off packing slips/tickets
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so this layer is cached unless requirements change
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

# App code. driver_app/ and pm_portal/ must sit alongside server/ — app.py
# references them as "../driver_app" and "../pm_portal" relative to itself.
COPY driver_app/ driver_app/
COPY pm_portal/ pm_portal/
COPY server/ server/

WORKDIR /app/server

EXPOSE 5000

# Production WSGI server (gunicorn is already in requirements.txt).
# 2 workers is plenty for a small fleet; raise -w if needed later.
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
