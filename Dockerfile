# Dockerfile for Gardena BLE Automower MQTT Bridge
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for Bluetooth and DBus
# apt-get is used for Debian-based images
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    dbus \
    && rm -rf /var/lib/apt/lists/*

# 1. Nur die requirements kopieren (für optimales Docker-Caching)
COPY requirements.txt .

# 2. Python dependencies installieren
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

# 3. Erst jetzt den eigentlichen Code kopieren
COPY . .

# Set default command
CMD ["python", "gardena.py"]