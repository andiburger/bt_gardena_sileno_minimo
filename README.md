# Gardena BLE to MQTT Bridge (Sileno Minimo)

[![CI Pipeline](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/ci-pipeline.yml/badge.svg)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/ci-pipeline.yml)
[![Docker Build & Publish](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/docker-publish.yml/badge.svg?event=release)](https://github.com/andiburger/bt_gardena_sileno_minimo/actions/workflows/docker-publish.yml)
[![codecov](https://codecov.io/gh/andiburger/bt_gardena_sileno_minimo/graph/badge.svg?token=DEIN_CODECOV_TOKEN)](https://codecov.io/gh/andiburger/bt_gardena_sileno_minimo)

A robust, highly optimized, and fully object-oriented Python service to bridge Gardena Automowers (like the Sileno Minimo) via Bluetooth Low Energy (BLE) to an MQTT broker. Fully integrated with **Home Assistant Auto-Discovery**.

Based on the [AutoMower-BLE](https://github.com/alistair23/AutoMower-BLE) library by alistair23.

## ✨ Key Features
* **Multi-Mower Ready:** Control multiple Gardena mowers simultaneously from a single Raspberry Pi/Docker container. The script perfectly queues Bluetooth commands to prevent hardware crashes.
* **Home Assistant Auto-Discovery:** Connects once, and your mowers automatically appear in HA with all sensors (Battery, Activity, Next Start, Statistics) and controls (Start, Pause, Park).
* **Preemptive Smart Polling:** To protect the mower's battery, the script does NOT keep a constant connection open. It calculates the exact next start time and wakes up automatically 60 seconds before the mower leaves the dock. (60s intervals while mowing, up to 15m while parked).
* **Auto-Recovery:** Catches `BlueZ` zombie connections and library crashes gracefully without bringing down the service.
* **❄️ Winter Mode:** When the mowing season is over and the mower is switched off and stored inside, activate Winter Mode via a Home Assistant switch. All Bluetooth polling stops, the mower shows as "Wintermodus" instead of an error, and the service idles quietly until spring.
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
poll_winter = 3600              # Polling interval in winter mode (seconds)
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
  -v $(pwd)/.cache:/app/.cache \
  gardena-mqtt-bridge
  ```
  (Tip: We mount cfg.ini externally so you can change settings without rebuilding the container. The `.cache` mount keeps the mower info cache across container rebuilds, see [Winter Mode](#️-winter-mode)).

  ## 🐍 Installation (Bare Metal / systemd)

  ```bash
  git clone <your-repo-url>
cd bt_gardena_sileno_minimo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python gardena.py
```

## ❄️ Winter Mode
When the mowing season is over and you switch off your mower and bring it inside for storage, you can activate **Winter Mode** to prevent the bridge from endlessly scanning for a mower that is no longer in Bluetooth range.

### What it does
| Normal Mode | Winter Mode |
|---|---|
| BLE scan every 60s–15min | All BLE scanning **stops** |
| HA status: Mäht / Geparkt / Fehler | HA status: **Wintermodus** |
| Commands (Start, Pause, Park) accepted | Commands **rejected** with a log warning |
| Sleep interval: `poll_active` / `poll_idle` | Sleep interval: `poll_winter` (default: 1 hour) |

### How to use it
A ❄️ **Wintermodus** toggle switch automatically appears on your mower's device card in Home Assistant (via Auto-Discovery).

1. **Activate:** Flip the switch **ON** in Home Assistant (or publish `WINTER_ON` to the mower's command topic).
2. **Deactivate:** Flip the switch **OFF** in spring (or publish `WINTER_OFF`). Normal BLE polling resumes immediately.

You can also control it via MQTT manually:
```bash
# Activate winter mode for mower_1
mosquitto_pub -h <broker_ip> -t "gardena/automower/mower_1/cmd" -m "WINTER_ON"

# Deactivate winter mode
mosquitto_pub -h <broker_ip> -t "gardena/automower/mower_1/cmd" -m "WINTER_OFF"
```

> **Note:** Winter Mode state is held in memory. If the service restarts, it defaults back to normal mode. This is intentional — if your Pi reboots in spring, it will automatically resume polling without manual intervention.

### Mower info cache (Discovery without Bluetooth)
Home Assistant needs the mower's serial number, model and manufacturer to create its entities (including the ❄️ switch). These values can only be read via Bluetooth. To make discovery work even when the mower is switched off, the bridge saves them to a small cache file after the **first successful Bluetooth connection**:

```
.cache/
├── 84_72_93_94_B6_4C.json    ← one file per mower, named after its MAC address
└── 11_22_33_44_55_66.json
```

On every startup, the bridge loads these files and sends the Home Assistant discovery immediately, without needing Bluetooth. If no cache file exists yet (fresh install), the bridge works as before and creates the file on the first successful connection. The `.cache/` folder is excluded via `.gitignore`.

### ⚠️ One-time migration: updating while the mower is already stored
If you update to this version while your mower is **already switched off** (e.g. stored for winter), no cache file exists yet and the bridge cannot reach the mower. The ❄️ switch will therefore **not** appear in Home Assistant until the mower has been reached via Bluetooth once.

In this case, activate Winter Mode manually once after the update:
```bash
mosquitto_pub -h <broker_ip> -t "gardena/automower/mower_1/cmd" -m "WINTER_ON"
```
In spring, switch the mower back on and send `WINTER_OFF` (or simply restart the service). The bridge connects, creates the cache file, and the ❄️ switch appears in Home Assistant. From then on, everything works from Home Assistant, even when the mower is unreachable.

## 🛠 Troubleshooting: Bluetooth Pairing
Gardena mowers require an OS-level confirmation for the very first pairing.

1. Turn off Bluetooth on your smartphone.

2. Restart your mower (OFF for 5s, then ON). It is now in pairing mode for 3 minutes.

3. Open a terminal on your Pi and run sudo bluetoothctl.

4. Type: power on -> agent NoInputNoOutput -> default-agent.

5. Leave this terminal open! Start the python script in a second terminal. The agent will auto-accept the pairing request.

## 📄 License

MIT License – see LICENSE
