from automower_ble import protocol, mower
from bleak import BleakScanner
import asyncio
import random
import time
import json
from paho.mqtt import client as mqtt_client
from cfg_parser import GardenaCfg
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
loop = None  # Global variable to hold the event loop, if needed for future use
broker = None
address = None
port = None
topic = None
topic_cmd = None
error_counter = 0
# Generate a Client ID with the publish prefix.
client_id = f"publish-{random.randint(0, 1000)}"
# msg to be published on mqtt
msg = {}


def connect_mqtt():
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to MQTT Broker!")
            # subscribe to command topic after successful connection
            if topic_cmd:
                client.subscribe(topic_cmd)
                logger.info(f"Subscribed to command topic: {topic_cmd}")
        else:
            logger.error(f"Failed to connect, return code {reason_code}")

    # supports MQTT v5.0 for better callback handling
    def on_message(client, userdata, msg):
        payload = msg.payload.decode('utf-8')
        logger.info(f"MQTT Command empfangen: {payload}")
        if loop and m:
            # execute the command in the event loop to avoid blocking the MQTT thread
            asyncio.run_coroutine_threadsafe(process_command(payload), loop)

    client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.on_connect = on_connect
    client.on_message = on_message
    if broker is None or port is None:
        raise ValueError("MQTT broker address and port must be set before connecting.")
    client.connect(broker, port)
    return client

def publish(client: mqtt_client.Client, msg):
    if topic is None:
        raise ValueError("MQTT topic must be set before publishing.")
    result = client.publish(topic, json.dumps(msg, indent=4))
    status = result[0]
    if status == 0:
        logger.info(f"Send `{msg}` to topic `{topic}`")
    else:
        logger.error(f"Failed to send message to topic {topic}")

def publish_discovery(client: mqtt_client.Client, serial_number, model, manufacturer, state_topic, cmd_topic):
    # Das fasst alle Sensoren zu EINEM Gerät in Home Assistant zusammen
    device_info = {
        "identifiers": [f"gardena_{serial_number}"],
        "name": "Sileno Minimo",
        "manufacturer": manufacturer,
        "model": model
    }

    # list of all values to be published for Home Assistant Auto-Discovery
    discovery_messages = [
        # 1. the lawn mower entity itself, which can be used to show the current activity and send commands to the mower
        (
            "lawn_mower/gardena_minimo/mower/config",
            {
                "name": "Sileno Minimo",
                "unique_id": f"gardena_mower_{serial_number}",
                "activity_state_topic": state_topic,
                "activity_value_template": "{% if value_json.MowerActivity in ['2', '3', '4'] %} mowing {% elif value_json.MowerActivity == '5' %} docked {% elif value_json.MowerActivity == '7' %} error {% else %} paused {% endif %}",
                "start_mowing_command_topic": cmd_topic,
                "start_mowing_command_template": "START",
                "pause_command_topic": cmd_topic,
                "pause_command_template": "PAUSE",
                "dock_command_topic": cmd_topic,
                "dock_command_template": "PARK",
                "device": device_info
            }
        ),
        # 2. detailed status sensor, which shows the raw activity code as well as a human readable status (e.g. mowing, searching, etc.)
        (
            "sensor/gardena_minimo/detailstatus/config",
            {
                "name": "Detailstatus",
                "unique_id": f"g_status_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{% if value_json.MowerActivity == '2' %} Fährt los {% elif value_json.MowerActivity == '3' %} Mäht {% elif value_json.MowerActivity == '4' %} Sucht Station {% elif value_json.MowerActivity == '5' %} Geparkt {% elif value_json.MowerActivity == '7' %} Fehler {% else %} Unbekannt ({{ value_json.MowerActivity }}) {% endif %}",
                "icon": "mdi:information-outline",
                "device": device_info
            }
        ),
        # 3. battery level sensor
        (
            "sensor/gardena_minimo/battery/config",
            {
                "name": "Akkustand",
                "unique_id": f"g_bat_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ value_json.BatteryLevel | int }}",
                "device_class": "battery",
                "unit_of_measurement": "%",
                "device": device_info
            }
        ),
        # 4. charging status sensor
        (
            "binary_sensor/gardena_minimo/is_charging/config",
            {
                "name": "Ladestatus",
                "unique_id": f"g_charging_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ value_json.IsCharging }}",
                "payload_on": "True",
                "payload_off": "False",
                "device_class": "battery_charging",
                "device": device_info
            }
        ),
        # 5. next start sensor
        (
            "sensor/gardena_minimo/next_start/config",
            {
                "name": "Nächster Start",
                "unique_id": f"g_nextstart_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ value_json['Next start time'] }}",
                "icon": "mdi:calendar-clock",
                "device": device_info
            }
        ),
        # 6. blade usage sensor
        (
            "sensor/gardena_minimo/blade_usage/config",
            {
                "name": "Messerlaufzeit",
                "unique_id": f"g_blade_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ (value_json.cuttingBladeUsageTime / 3600) | round(2) }}",
                "unit_of_measurement": "h",
                "state_class": "total_increasing",
                "icon": "mdi:saw-blade",
                "device": device_info
            }
        ),
        # 7. total running time sensor
        (
            "sensor/gardena_minimo/total_running/config",
            {
                "name": "Gesamte Betriebszeit",
                "unique_id": f"g_running_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ (value_json.totalRunningTime / 3600) | round(2) }}",
                "unit_of_measurement": "h",
                "state_class": "total_increasing",
                "icon": "mdi:clock-outline",
                "device": device_info
            }
        ),
        # 8. pure mowing time sensor
        (
            "sensor/gardena_minimo/total_cutting/config",
            {
                "name": "Reine Mähzeit",
                "unique_id": f"g_cutting_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ (value_json.totalCuttingTime / 3600) | round(2) }}",
                "unit_of_measurement": "h",
                "state_class": "total_increasing",
                "icon": "mdi:grass",
                "device": device_info
            }
        ),
        # 9. searching time sensor
        (
            "sensor/gardena_minimo/total_searching/config",
            {
                "name": "Suchzeit",
                "unique_id": f"g_searching_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ (value_json.totalSearchingTime / 3600) | round(2) }}",
                "unit_of_measurement": "h",
                "state_class": "total_increasing",
                "icon": "mdi:radar",
                "device": device_info
            }
        ),
        # 10. total charging time sensor
        (
            "sensor/gardena_minimo/total_charging/config",
            {
                "name": "Gesamte Ladezeit",
                "unique_id": f"g_totalcharge_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ (value_json.totalChargingTime / 3600) | round(2) }}",
                "unit_of_measurement": "h",
                "state_class": "total_increasing",
                "icon": "mdi:battery-clock",
                "device": device_info
            }
        ),
        # 11. charge cycles sensor
        (
            "sensor/gardena_minimo/charge_cycles/config",
            {
                "name": "Ladezyklen",
                "unique_id": f"g_cycles_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ value_json.numberOfChargingCycles | int }}",
                "state_class": "total_increasing",
                "icon": "mdi:battery-sync",
                "device": device_info
            }
        ),
        # 12. collisions sensor
        (
            "sensor/gardena_minimo/collisions/config",
            {
                "name": "Kollisionen",
                "unique_id": f"g_collisions_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ value_json.numberOfCollisions | int }}",
                "state_class": "total_increasing",
                "icon": "mdi:car-bumper",
                "device": device_info
            }
        ),
        # 13. gardena activity raw sensor, which shows the raw activity code without any interpretation, can be used for debugging or to create custom automations based on the raw activity code
        (
            "sensor/gardena_minimo/activity_raw/config",
            {
                "name": "Activity Raw",
                "unique_id": f"g_act_raw_{serial_number}",
                "state_topic": state_topic,
                "value_template": "{{ value_json.MowerActivity | replace('MowerActivity.', '') }}",
                "icon": "mdi:code-json",
                "device": device_info
            }
        )
    ]

    for topic_suffix, payload in discovery_messages:
        full_topic = f"homeassistant/{topic_suffix}"
        client.publish(full_topic, json.dumps(payload), retain=True)
        
    logger.info("Auto-Discovery Setup erfolgreich an Home Assistant gesendet!")

async def process_command(payload):
    logger.info(f"Executing command: {payload}")
    try:
        if payload == "START":
            # Forces the mower to start immediately by overriding the schedule.
            # Uses the built-in library function which sets Mode to AUTO,
            # defines the duration (default 3h), and sends the StartTrigger.
            logger.info("Sending Override (Immediate start for 3 hours)...")
            await m.mower_override()
        elif payload == "PAUSE":
            # Immediately pauses the mower at its current location.
            logger.info("Sending Pause command...")
            await m.command("Pause")
        elif payload == "PARK":
            # Sends the mower back to the charging station.
            # It will stay there until the next scheduled task begins.
            logger.info("Sending Park command (Until next schedule)...")
            await m.mower_park()
        else:
            logger.warning(f"Unknown command received: {payload}")
    except Exception as e:
        logger.error(f"Error occurred while sending command {payload}: {e}")


async def connect(m: mower.Mower, client: mqtt_client.Client):
    global loop
    # Store the event loop reference for use in MQTT callbacks
    loop = asyncio.get_running_loop() 
    try:
        logger.info("Start test mower")
        device = await BleakScanner.find_device_by_address(m.address)
        if device is None:
            logger.error("Unable to connect to device address: " + m.address)
            logger.error(
                "Please make sure the device address is correct, the device is powered on and nearby"
            )
            return
        logger.info(f"Device found. Start connecting to device {m.address}")
        await m.connect(device)
        logger.info(f"Connected to device with address {m.address}")
        logger.info(f"Mower : {m}")

        model = await m.get_model()
        logger.info(f"Model : {model} ")
        msg.update({"Model": str(model)})

        manufacturer = await m.get_manufacturer()
        logger.info(f"Manufacturer {manufacturer}")
        msg.update({"Manufacturer": manufacturer})
        
        serial_number = await m.command("GetSerialNumber")
        logger.info(f"Serial number : {serial_number}")
        msg.update({"SerialNumber": serial_number})

        publish_discovery(client, serial_number, str(model), manufacturer, topic, topic_cmd)
        while True:
            logger.info("Start sending keep Alive")

            activity = await m.mower_activity()
            logger.info(f"Mower activity : {activity}")
            msg.update({"MowerActivity": str(activity)})

            statuses = await m.command("GetAllStatistics")
            if isinstance(statuses, dict):
                for status, value in statuses.items():
                    logger.info(f"{status} {value}")
                    msg.update({str(status): value})
            else:
                logger.warning(
                    f"Unexpected type for statuses: {type(statuses)} - {statuses}"
                )

            is_charging = await m.is_charging()
            logger.info(f"Is charging {is_charging}")
            msg.update({"IsCharging": is_charging})

            battery_level = await m.battery_level()
            logger.info(f"Battery level {battery_level}")
            msg.update({"BatteryLevel": battery_level})

            next_start_time = await m.mower_next_start_time()
            if next_start_time:
                logger.info(
                    "Next start time: " + next_start_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                msg.update(
                    {"Next start time": next_start_time.strftime("%Y-%m-%d %H:%M:%S")}
                )
            else:
                logger.info("No next start time")

            mower_state = await m.mower_state()
            logger.info(f"Mower state response {mower_state}")
            msg.update({"MowerStateResponse": str(mower_state)})

            mower_activity = await m.mower_activity()
            logger.info(f"MowerActivity : {mower_activity}")

            logger.info("publish")
            publish(client, msg)
            await asyncio.sleep(
                60
            )  # sleep for 1 minute and than try to retrieve data again
    except Exception as e:
        logger.error("There was an issue communicating with the device")
        raise e


if __name__ == "__main__":
    cfg_parser = GardenaCfg()
    result = cfg_parser.parse()
    broker = result["mqtt"]["broker"]
    port = int(result["mqtt"]["port"])
    topic = result["mqtt"]["topic"]
    topic_cmd = result["mqtt"]["topic_cmd"]
    address = result["mower"]["address"]
    pin = int(result["mower"]["pin"])

    client = connect_mqtt()
    client.loop_start()
    try:
        m = mower.Mower(random.randint(100000000, 999999999), address, pin)
        asyncio.run(connect(m, client))
    except Exception as e:
        error_counter += 1
        logger.error(e)
        msg.update({"Error": str(e)})
        msg.update({"Error Counter": error_counter})
        publish(client, msg)
    client.loop_stop()
    client.disconnect()
