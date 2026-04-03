from automower_ble import protocol, mower
from bleak import BleakScanner
import asyncio
import random
import time
import json
from paho.mqtt import client as mqtt_client
from cfg_parser import GardenaCfg
import logging

logging.basicConfig(level=logging.INFO)
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


async def process_command(payload):
    logger.info(f"execute command: {payload}")
    try:
        # Depending on the command, call the appropriate method on the mower instance
        if payload == "START":
            await m.command("Resume")  # starts or resumes mowing on the lawn
        elif payload == "PAUSE":
            await m.command("Pause")  # pauses mowing on the lawn
        elif payload == "PARK":
            await m.command("Park")  # drives back to the charging station
        else:
            logger.warning(f"Unknown command: {payload}")
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
        while True:
            logger.info("Start sending keep Alive")

            activity = await m.mower_activity()
            logger.info(f"Mower activity : {activity}")
            msg.update({"MowerActivity": str(activity)})

            serial_number = await m.command("GetSerialNumber")
            logger.info(f"Serial number : {serial_number}")
            msg.update({"SerialNumber": serial_number})

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
