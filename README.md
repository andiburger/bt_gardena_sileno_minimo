# Gardena BLE Automower MQTT Bridge

Library to retrieve all data from Gardena automower via Bluetooth to MQTT.
The Library is based on the AutomowerBLE library https://github.com/alistair23/AutoMower-BLE.



This Python script connects via Bluetooth Low Energy (BLE) to a Husqvarna Gardena Automower and regularly transmits status data via MQTT to a broker (e.g., for Home Assistant or other automation systems).

## 🔧 Requirements

- Python 3.8+
- Bluetooth adapter (e.g., Raspberry Pi with Bluetooth)
- Supported Gardena Automower (with BLE)
- MQTT broker

## 📦 Installation

```bash
git clone https://github.com/dein-benutzer/bt_gardena_sileno_minimo.git
cd bt_gardena_sileno_minimo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## ⚙️ Configuration

Create a configuration file `config.yaml` or adjust it accordingly. It should have a structure like the following:

```yaml
mqtt:
  broker: 192.168.178.10
  port: 1883
  topic: gardena/status
  topic_cmd: gardena/cmd

mower:
  address: 'XX:XX:XX:XX:XX:XX'  # Bluetooth MAC address of the mower
  pin: 1234
```

## ▶️ Running

```bash
python gardena.py
```

The script connects to the mower, regularly reads status data (battery level, activity, charging status, etc.) and sends this as JSON via MQTT.

## 🧪 Example MQTT Message

```json
{
  "Model": "GARDENA SILENO minimo",
  "Manufacturer": "Husqvarna",
  "MowerActivity": "PAUSED",
  "SerialNumber": "123456789",
  "IsCharging": true,
  "BatteryLevel": 85,
  "Next start time": "2025-05-19 18:00:00",
  "MowerStateResponse": "PARKED"
}
```

## Pairing issues

### Troubleshooting: `[org.bluez.Error.AuthenticationFailed]` on Linux (Raspberry Pi)

When running this script on a Linux environment (like a Raspberry Pi), you might encounter the following error during the first connection attempt:
`[org.bluez.Error.AuthenticationFailed] Authentication Failed`

**Why does this happen?**
The `automower-ble` library handles the PIN authentication internally via GATT characteristics. However, the Linux Bluetooth stack (BlueZ) intercepts the initial pairing request and blocks it because it expects an OS-level confirmation (a default agent), which the Python script cannot provide. 

**The Workaround (One-Time Setup)**
We need to temporarily start a background agent that automatically accepts the OS-level pairing request. You will need two SSH/Terminal windows for this.

**Step 1: Clear the Bluetooth cache (Optional but recommended)**
If you already tried connecting and failed, tell Linux to forget the mower first:
```bash
sudo bluetoothctl remove <YOUR_MOWER_MAC_ADDRESS>
```

**Step 2: Start the Auto-Accept Agent (Terminal 1)**
Open your first terminal and start the Bluetooth control tool:

```bash
sudo bluetoothctl
```
Inside the [bluetooth]# prompt, type the following commands:

```bash
power on
agent NoInputNoOutput
default-agent
```
Important: Leave this terminal window open! This agent is now running in the background and will automatically say "Yes" to any OS-level connection requests.

**Step 3: Prepare the Mower**

Turn off Bluetooth on your smartphone to prevent the Gardena App from interfering.

Turn your mower OFF, wait 5 seconds, and turn it ON again.

The mower is now in pairing mode for exactly 3 minutes.

**Step 4: Start the Script (Terminal 2)**
Open a second terminal window, activate your virtual environment, and run the script:

```bash
python gardena.py
```
## 🛠 Notes

- You can adjust the logging level in `gardena.py`.
- The connection runs over BLE – the mower must be in range and active.

## 📄 License

MIT License – see `LICENSE`
