# Gardena BLE to MQTT Bridge (Sileno Minimo)

[![Code Formatting (Black)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/black.yml/badge.svg)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/black.yml)
[![Pylint](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/pylint.yml/badge.svg)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/pylint.yml)
[![Python application](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/python-app.yml/badge.svg)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/python-app.yml)
[![Security Scanner (Bandit)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/bandit.yml/badge.svg)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/bandit.yml)
[![Docker Build & Publish](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/docker-publish.yml)

A robust, highly optimized, and fully object-oriented Python service to bridge Gardena Automowers (like the Sileno Minimo) via Bluetooth Low Energy (BLE) to an MQTT broker. Fully integrated with **Home Assistant Auto-Discovery**.

Based on the [AutoMower-BLE](https://github.com/alistair23/AutoMower-BLE) library by alistair23.

## ✨ Key Features
* **Multi-Mower Ready:** Control multiple Gardena mowers simultaneously from a single Raspberry Pi/Docker container. The script perfectly queues Bluetooth commands to prevent hardware crashes.
* **Home Assistant Auto-Discovery:** Connects once, and your mowers automatically appear in HA with all sensors (Battery, Activity, Next Start, Statistics) and controls (Start, Pause, Park).
* **Preemptive Smart Polling:** To protect the mower's battery, the script does NOT keep a constant connection open. It calculates the exact next start time and wakes up automatically 60 seconds before the mower leaves the dock. (60s intervals while mowing, up to 15m while parked).
* **Auto-Recovery:** Catches `BlueZ` zombie connections and library crashes gracefully without bringing down the service.
* **Fully Dockerized:** Includes a highly optimized, lightweight Debian-slim Dockerfile.

## ⚙️ Configuration (`cfg.ini`)
Create a file named `cfg.ini` in the root directory (you can use `cfg.example.ini` as a template). You can add as many `[mower_x]` sections as you have physical mowers.

```ini
[mqtt]
broker = 192.168.1.100          # MQTT Broker IP
port = 1883
topic_base = gardena/automower  # Base topic (creates .../mower_1/status, etc.)

[system]
log_level = INFO                # DEBUG, INFO, WARNING, ERROR
poll_active = 60                # Polling interval while mowing (seconds)
poll_idle = 900                 # Polling interval while parked (seconds)
poll_error = 30                 # Timeout after a Bluetooth error (seconds)

[mower_1]
name = Minimo Front
address = 84:72:93:94:B6:4C     # Your mower's Bluetooth MAC address
pin = 1234                      # Your Gardena PIN

[mower_2]
name = Minimo Back
address = 11:22:33:44:55:66
pin = 5678
```
## 🐳 Installation (Docker - Recommended)
Since the container needs access to the host's Bluetooth hardware, you must mount the dbus and run it in privileged/host-network mode.
```bash
docker build -t gardena-mqtt-bridge .

docker run -d \
  --name gardena_mower \
  --net=host \
  --privileged \
  -v /var/run/dbus:/var/run/dbus \
  -v $(pwd)/cfg.ini:/app/cfg.ini \
  gardena-mqtt-bridge
  ```
  (Tip: We mount cfg.ini externally so you can change settings without rebuilding the container).

  ## 🐍 Installation (Bare Metal / systemd)

  ```bash
  git clone <your-repo-url>
cd bt_gardena_sileno_minimo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python gardena.py
```

## 🛠 Troubleshooting: Bluetooth Pairing
Gardena mowers require an OS-level confirmation for the very first pairing.

1. Turn off Bluetooth on your smartphone.

2. Restart your mower (OFF for 5s, then ON). It is now in pairing mode for 3 minutes.

3. Open a terminal on your Pi and run sudo bluetoothctl.

4. Type: power on -> agent NoInputNoOutput -> default-agent.

5. Leave this terminal open! Start the python script in a second terminal. The agent will auto-accept the pairing request.

## 📄 License

MIT License – see LICENSE
