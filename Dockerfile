# Dockerfile for Gardena BLE Automower MQTT Bridge
FROM python:3.13-alpine

# Set working directory
WORKDIR /app

# Install system dependencies needed for Bluetooth and DBus
RUN apk add --no-cache \
    bluez \
    bluez-deprecated \
    bluez-libs \
    dbus \
    dbus-glib \
    build-base \
    glib \
    linux-headers \
    libffi-dev \
    openssl-dev \
    libusb-dev

# Optional: für einige Python-Builds (z. B. protobuf)
RUN apk add --no-cache py3-pip


# Copy project files
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Set default command
CMD ["python", "gardena.py"]