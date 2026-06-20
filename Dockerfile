# Nutze eine absolut stabile Version, die perfekt auf ARM/Pi Zero abgestimmt ist
FROM python:3.12-slim

WORKDIR /app

# WICHTIG: Verhindert, dass Python Logs puffert. Fehler erscheinen SOFORT in den Docker-Logs.
ENV PYTHONUNBUFFERED=1

# Installiere System-Abhängigkeiten UND Bau-Werkzeuge (Compiler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    dbus \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "gardena.py"]