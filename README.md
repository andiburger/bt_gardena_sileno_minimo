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

## 🛠 Notes

- You can adjust the logging level in `gardena.py`.
- The connection runs over BLE – the mower must be in range and active.

## 📄 License

MIT License – see `LICENSE`
