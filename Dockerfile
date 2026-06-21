# Nutze eine absolut stabile Version, die perfekt auf ARM/Pi Zero abgestimmt ist
FROM python:3.12-slim

WORKDIR /app

# WICHTIG: Verhindert, dass Python Logs puffert.
ENV PYTHONUNBUFFERED=1

# Das komplette Arsenal an Compilern und Headern für Bluetooth/DBUS auf ARM
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    dbus \
    build-essential \
    python3-dev \
    pkg-config \
    libdbus-1-dev \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "gardena.py"]