FROM python:3.12-slim

# tesseract-ocr: required for reading job numbers off packing slips/tickets
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy everything
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r server/requirements.txt

EXPOSE 5000

# Change to server directory and run gunicorn
WORKDIR /app/server
CMD exec gunicorn -w 2 -b 0.0.0.0:5000 --timeout 120 app:app
