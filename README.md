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
* **❄️ Winter Mode:** When the mowing season is over and the mower is switched off and stored inside, activate Winter Mode via a Home Assistant switch. All Bluetooth polling stops, the mower shows as "Wintermodus" instead of an error, and the state is persisted across restarts until spring.
* **🛡️ Security & Physical Safety Hardening:** Supports encrypted PINs/passwords (`Fernet` AES-128-CBC + HMAC-SHA256), MQTT authentication & TLS, retained-command rejection, stop-command priority over queued starts, and validated schedule parameters.
* **Fully Dockerized:** Includes a highly optimized, lightweight Debian-slim Dockerfile.

## ⚙️ Configuration (`cfg.ini`)
Create a file named `cfg.ini` in the root directory (you can use `cfg.example.ini` as a template). You can add as many `[mower_x]` sections as you have physical mowers.

```ini
[mqtt]
broker = 192.168.1.100          # MQTT Broker IP
port = 1883
topic_base = gardena/automower  # Base topic (creates .../mower_1/status, etc.)
# Optional broker authentication & TLS:
# username = gardena_user
# password = enc:gAAAAAB...     # Encrypted with: python secrets_crypto.py
# tls = false
# ca_certs = /etc/ssl/certs/ca-certificates.crt

[system]
log_level = INFO                # DEBUG, INFO, WARNING, ERROR
poll_active = 60                # Polling interval while mowing (seconds)
poll_idle = 900                 # Polling interval while parked (seconds)
poll_winter = 3600              # Polling interval in winter mode (seconds)
poll_error = 30                 # Timeout after a Bluetooth error (seconds)

[mower_1]
name = Minimo Front
address = 84:72:93:94:B6:4C     # Your mower's Bluetooth MAC address
pin = enc:gAAAAAB...            # Encrypted PIN (or plaintext for backwards compatibility)

[mower_2]
name = Minimo Back
address = 11:22:33:44:55:66
pin = enc:gAAAAAB...
```

### 🔐 Encrypting PINs and MQTT Passwords
To avoid storing mower PINs or MQTT passwords in plaintext inside `cfg.ini`, run the helper script:
```bash
python secrets_crypto.py
```
1. It prompts for your PIN or password (hidden input) and prints an encrypted `enc:...` token to paste into `cfg.ini`.
2. On first run, it generates a key file `.gardena.key` (permissions `0600`, excluded via `.gitignore` and `.dockerignore`). You can also pass the key via the `GARDENA_SECRET_KEY` environment variable.
3. Existing plaintext values in `cfg.ini` continue to work (with a log warning).
4. Restrict permissions on `cfg.ini` as well (`chmod 600 cfg.ini`) — the service logs a warning if `cfg.ini` is readable by group/others.

## 🐳 Installation (Docker - Recommended)
Since the container needs access to the host's Bluetooth hardware, you must mount the dbus and run it in privileged/host-network mode.
```bash
docker build -t gardena-mqtt-bridge .

docker run -d \
  --name gardena_mower \
  --net=host \
  --privileged \
  -v /var/run/dbus:/var/run/dbus \
  -v $(pwd)/cfg.ini:/app/cfg.ini:ro \
  -v $(pwd)/.gardena.key:/app/.gardena.key:ro \
  -v $(pwd)/.cache:/app/.cache \
  gardena-mqtt-bridge
```
(Tip: We mount `cfg.ini` and `.gardena.key` externally so you can change settings without rebuilding the container — or pass `-e GARDENA_SECRET_KEY=...` instead of mounting `.gardena.key`. The `.cache` mount keeps the mower info cache and Winter Mode state across container rebuilds, see [Winter Mode](#️-winter-mode)).

## 🐍 Installation (Bare Metal / systemd)

```bash
git clone <your-repo-url>
cd bt_gardena_sileno_minimo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Systemd Service Setup & Bluetooth Auto-Recovery
After weeks of continuous BLE polling, the Raspberry Pi's Bluetooth adapter (`hci0`) can soft-crash or power down. `bleak` then reports `No powered Bluetooth adapters found ... POWERED_OFF`. The bridge detects this (and other BlueZ stack errors) and tries to revive the adapter automatically:

```bash
sudo -n rfkill unblock bluetooth
sudo -n systemctl restart bluetooth
sudo -n hciconfig hci0 up
```

These commands need **admin privileges**. The `-n` flag makes `sudo` fail immediately instead of waiting for a password, so a missing permission is logged as an error instead of freezing the service. When creating your systemd service (`/etc/systemd/system/gardena.service`), choose one of the following options for the `User=` directive:

**Option A: Run as root (easiest)**
```ini
[Unit]
Description=Gardena BLE to MQTT Bridge
After=bluetooth.target network-online.target

[Service]
User=root
WorkingDirectory=/path/to/bt_gardena_sileno_minimo
ExecStart=/path/to/bt_gardena_sileno_minimo/venv/bin/python gardena.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**Option B: Run as a normal user (more secure)**
Run the service as a standard user (e.g. `User=pi`) and allow that user to run **only** the recovery commands as root without a password. Create a dedicated sudoers file with:
```bash
sudo visudo -f /etc/sudoers.d/gardena_bluetooth
```
and add this line (replace `pi` with your username; check the binary paths on your system with `which systemctl rfkill hciconfig`):
```text
pi ALL=(root) NOPASSWD: /bin/systemctl restart bluetooth, /usr/bin/systemctl restart bluetooth, /usr/sbin/rfkill unblock bluetooth, /bin/hciconfig hci0 up, /usr/bin/hciconfig hci0 up
```
Test it as that user with `sudo -n systemctl restart bluetooth`. If it runs without asking for a password, the setup works.

Then enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gardena
```

> **Manual recovery:** If the adapter is down right now, you can run the three recovery commands above by hand via SSH.

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

> **Note:** Winter Mode state is persisted in `.cache/<MAC>.json`. If the service or Raspberry Pi restarts during winter, the mower stays safely in Winter Mode without triggering Bluetooth scans or error states.

### Mower info cache (Discovery without Bluetooth)
Home Assistant needs the mower's serial number, model and manufacturer to create its entities (including the ❄️ switch). These values can only be read via Bluetooth. To make discovery work even when the mower is switched off, the bridge saves them (along with the current `WinterMode` state) to a small cache file after the **first successful Bluetooth connection**:

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
This persists the Winter Mode flag in `.cache/<MAC>.json` right away. In spring, switch the mower back on and send `WINTER_OFF`. The bridge connects, saves the hardware info to the cache file, and the ❄️ switch appears in Home Assistant. From then on, everything works from Home Assistant, even when the mower is unreachable.

## 🛡️ Security & Physical Safety
Because a robotic lawnmower is a physical machine with rotating blades, the bridge includes several security and physical safety safeguards:

* **Encrypted Secrets (`secrets_crypto.py`):** Mower PINs and MQTT passwords can be stored encrypted (`enc:...` via `Fernet` AES-128-CBC + HMAC-SHA256) using a local `.gardena.key` file (`0600`) or `GARDENA_SECRET_KEY` environment variable.
* **MQTT Authentication & TLS:** Supports optional broker `username`/`password` authentication and TLS encryption (`tls = true`, custom `ca_certs`).
* **Retained Command Protection:** Any MQTT command message arriving with the `retain` flag set (`retain=True`) is rejected and ignored. This guarantees that a stale retained `START` message on the broker can never unexpectedly launch the mower when the service or broker restarts.
* **Stop/Pause Priority (Emergency Abort):** Because BLE operations are serialized via a lock, a `START` command may briefly wait while a status poll finishes. If a `PAUSE`, `PARK`, or `WINTER_ON` command arrives in the meantime, any queued `START` is immediately aborted before it reaches the mower, and only the stop/park command is executed.
* **Persistent Winter Mode:** Activating `WINTER_ON` persists across container/service restarts in `.cache/<MAC>.json`, ensuring the bridge stays silent and blocks movement commands until `WINTER_OFF` is explicitly sent.
* **Schedule Validation (`ADD_TASK`):** Schedule parameters (`ADD_TASK:day:start:duration:use_b`) are validated for exact format and bounded to `1..1440` minutes (max 24 hours).
* **Multi-Mower Discovery Isolation:** When multiple mowers are configured, Home Assistant Auto-Discovery topics are automatically scoped by serial number (`gardena_minimo_<serial>`) so mowers never overwrite each other's entities.

## 🛠 Troubleshooting: Bluetooth Pairing
Gardena mowers require an OS-level confirmation for the very first pairing.

1. Turn off Bluetooth on your smartphone.

2. Restart your mower (OFF for 5s, then ON). It is now in pairing mode for 3 minutes.

3. Open a terminal on your Pi and run sudo bluetoothctl.

4. Type: power on -> agent NoInputNoOutput -> default-agent.

5. Leave this terminal open! Start the python script in a second terminal. The agent will auto-accept the pairing request.

## 📄 License

MIT License – see LICENSE
