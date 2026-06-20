# Nutze eine absolut stabile Version, die perfekt auf ARM/Pi Zero abgestimmt ist
FROM python:3.14-slim

WORKDIR /app

# WICHTIG: Verhindert, dass Python Logs puffert. Fehler erscheinen SOFORT in den Docker-Logs.
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    dbus \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "gardena.py"]