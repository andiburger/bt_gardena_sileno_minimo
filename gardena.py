"""
Gardena Sileno Minimo BLE to MQTT Bridge
Optimized for Home Assistant Auto-Discovery with Smart Polling (Connect-on-Demand)
and Secure Transactions.
Author: __ABu__ / Refactored
"""

from automower_ble import mower
from bleak import BleakScanner
from datetime import datetime
import asyncio
import random
import json
from paho.mqtt import client as mqtt_client
from cfg_parser import GardenaCfg
import logging

# --- Configuration & Logging ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Global Variables ---
loop = None
broker = None
address = None
# m = None
port = None
pin = None
error_counter = 0

# Flags and Locks for the Smart Polling Architecture
discovery_sent = False
mower_static_info = {}
ble_lock = asyncio.Lock()  # Prevents simultaneous Bluetooth commands/polling


class GardenaMQTTBridge:
    """
    Main class for the Gardena MQTT Bridge. Handles MQTT connection, command processing,
    and mower data polling.
    """

    def __init__(self, config: dict):
        self.config = config
        self.broker = config["mqtt"]["broker"]
        self.port = int(config["mqtt"]["port"])
        self.client_id = f"publish-{random.randint(0, 1000)}"
        self.mowers = {}
        self.client = None

    def add_mower(self, mower_id, mower_object):
        self.mowers[mower_id] = mower_object
        base = self.config["mqtt"]["topic_base"]
        mower_object.topic_status = f"{base}/{mower_id}/status"
        mower_object.topic_cmd = f"{base}/{mower_id}/cmd"

    def connect_mqtt(self):
        """
        Connects to the MQTT broker and sets up callbacks.
        """

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                logger.info("Connected to MQTT Broker!")
                for m_id, mower_obj in self.mowers.items():
                    if hasattr(mower_obj, "topic_cmd"):
                        client.subscribe(mower_obj.topic_cmd)
                        logger.info(
                            f"Subscribed to command topic: {mower_obj.topic_cmd}"
                        )
            else:
                logger.error(f"Failed to connect, return code {reason_code}")

        def on_message(client, userdata, incoming_msg):
            payload = incoming_msg.payload.decode("utf-8")
            incoming_topic = incoming_msg.topic
            logger.info(f"Command received on {incoming_topic}: {payload}")

            for m_id, mower_obj in self.mowers.items():
                if (
                    hasattr(mower_obj, "topic_cmd")
                    and incoming_topic == mower_obj.topic_cmd
                ):
                    if loop is not None:
                        asyncio.run_coroutine_threadsafe(
                            mower_obj.process_command(payload), loop
                        )
                    else:
                        logger.error(
                            "Critical: Asyncio loop not initialized. Cannot process command."
                        )
                    break

        self.client = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2, client_id=self.client_id
        )
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        if broker is None or port is None:
            raise ValueError(
                "MQTT broker address and port must be set before connecting."
            )
        self.client.connect(broker, port)
        self.client.loop_start()  # Start the MQTT client loop in a separate thread

    def stop(self):
        """Stops the MQTT client loop and disconnects."""
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic, msg_payload):
        """Publishes a message to the MQTT state topic."""
        if topic is None:
            raise ValueError("MQTT topic must be set before publishing.")
        # Using retain=True so Home Assistant always has the latest state upon reboot
        result = self.client.publish(
            topic, json.dumps(msg_payload, indent=4), retain=True
        )
        status = result[0]
        if status == 0:
            logger.info(f"Sent state payload to topic `{topic}`")
        else:
            logger.error(f"Failed to send message to topic {topic}")

    def publish_discovery(
        self,
        serial_number,
        model,
        manufacturer,
        state_topic,
        cmd_topic,
    ):
        """
        Publishes Home Assistant Auto-Discovery configuration messages for the Gardena mower.
        """
        device_info = {
            "identifiers": [f"gardena_{serial_number}"],
            "name": "Sileno Minimo",
            "manufacturer": manufacturer,
            "model": model,
        }

        discovery_messages = [
            # 1. Lawn Mower Entity
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
                    "device": device_info,
                },
            ),
            # 2. Detailed Status Sensor
            (
                "sensor/gardena_minimo/detailstatus/config",
                {
                    "name": "Detailstatus",
                    "unique_id": f"g_status_{serial_number}",
                    "state_topic": state_topic,
                    "value_template": "{% if value_json.MowerActivity == '2' %} Fährt los {% elif value_json.MowerActivity == '3' %} Mäht {% elif value_json.MowerActivity == '4' %} Sucht Station {% elif value_json.MowerActivity == '5' %} Geparkt {% elif value_json.MowerActivity == '7' %} Fehler {% else %} Unbekannt ({{ value_json.MowerActivity }}) {% endif %}",
                    "icon": "mdi:information-outline",
                    "device": device_info,
                },
            ),
            # 3. Battery Level Sensor
            (
                "sensor/gardena_minimo/battery/config",
                {
                    "name": "Akkustand",
                    "unique_id": f"g_bat_{serial_number}",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.BatteryLevel | int }}",
                    "device_class": "battery",
                    "unit_of_measurement": "%",
                    "device": device_info,
                },
            ),
            # 4. Charging Status Sensor
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
                    "device": device_info,
                },
            ),
            # 5. Next Start Sensor
            (
                "sensor/gardena_minimo/next_start/config",
                {
                    "name": "Nächster Start",
                    "unique_id": f"g_nextstart_{serial_number}",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json['Next start time'] }}",
                    "icon": "mdi:calendar-clock",
                    "device": device_info,
                },
            ),
            # 6. Blade Usage Sensor
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
                    "device": device_info,
                },
            ),
            # 7. Total Running Time Sensor
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
                    "device": device_info,
                },
            ),
            # 8. Pure Mowing Time Sensor
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
                    "device": device_info,
                },
            ),
            # 9. Searching Time Sensor
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
                    "device": device_info,
                },
            ),
            # 10. Total Charging Time Sensor
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
                    "device": device_info,
                },
            ),
            # 11. Charge Cycles Sensor
            (
                "sensor/gardena_minimo/charge_cycles/config",
                {
                    "name": "Ladezyklen",
                    "unique_id": f"g_cycles_{serial_number}",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.numberOfChargingCycles | int }}",
                    "state_class": "total_increasing",
                    "icon": "mdi:battery-sync",
                    "device": device_info,
                },
            ),
            # 12. Collisions Sensor
            (
                "sensor/gardena_minimo/collisions/config",
                {
                    "name": "Kollisionen",
                    "unique_id": f"g_collisions_{serial_number}",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.numberOfCollisions | int }}",
                    "state_class": "total_increasing",
                    "icon": "mdi:car-bumper",
                    "device": device_info,
                },
            ),
            # 13. Gardena Activity Raw Sensor
            (
                "sensor/gardena_minimo/activity_raw/config",
                {
                    "name": "Activity Raw",
                    "unique_id": f"g_act_raw_{serial_number}",
                    "state_topic": state_topic,
                    "value_template": "{{ value_json.MowerActivity | replace('MowerActivity.', '') }}",
                    "icon": "mdi:code-json",
                    "device": device_info,
                },
            ),
        ]

        for topic_suffix, payload in discovery_messages:
            full_topic = f"homeassistant/{topic_suffix}"
            self.client.publish(full_topic, json.dumps(payload), retain=True)

        logger.info("Auto-Discovery Setup successfully sent to Home Assistant!")


class LawnMowerEntity:
    """
    Represents the main Lawn Mower entity in Home Assistant. This class is responsible for
    processing commands and updating the mower's state based on the received MQTT messages.
    """

    def __init__(self, name, address, pin, bridge: GardenaMQTTBridge, config):
        """
        Initializes the Lawn Mower entity with the given parameters.
        param name: The name of the mower entity.
        param address: The Bluetooth address of the mower.
        param pin: The PIN code for Bluetooth pairing.
        param bridge: The MQTT bridge instance for communication.
        param config: The configuration dictionary for the system.
        """
        self.name = name
        self.address = address
        self.pin = pin
        self.bridge = bridge
        self.config = config
        self.msg_state = {}
        self.static_info = {}
        self.discovery_sent = False
        self.error_counter = 0
        self.topic_status = None
        self.topic_cmd = None
        # instance of the mower will be created on demand in the command processing to ensure a clean state for each connection
        self.m = mower.Mower(random.randint(100000000, 999999999), address, pin)

    async def process_command(self, payload):
        """
        Safely processes incoming commands (Start, Pause, Park, Schedule).
        Implements Connect-on-Demand to avoid interrupting the deep sleep.
        """
        if payload.startswith("ADD_TASK:"):
            try:
                _, params = payload.split(":")
                p = params.split(",")
                day_idx, h, m_start, dur = int(p[0]), int(p[1]), int(p[2]), int(p[3])
                if (
                    not (0 <= day_idx <= 6)
                    or not (0 <= h <= 23)
                    or not (0 <= m_start <= 59)
                    or dur <= 0
                ):
                    logger.error(
                        f"Invalid parameters for schedule: Day={day_idx}, Time={h}:{m_start}, Duration={dur}. Aborting!"
                    )
                    return
            except ValueError:
                logger.error(
                    f"Invalid payload format (non-numeric values detected): {payload}"
                )
                return

        # Request the Bluetooth lock to ensure no polling interferes
        async with ble_lock:
            try:
                logger.info("Command execution: Scanning for mower...")
                device = await BleakScanner.find_device_by_address(self.address)
                if not device:
                    logger.error("Command failed: Mower not found in Bluetooth range.")
                    return

                await asyncio.wait_for(self.m.connect(device), timeout=15.0)
                await asyncio.sleep(
                    1.0
                )  # Short delay to ensure connection stability before sending commands

                if payload == "START":
                    logger.info("Sending Override (Immediate start for 3 hours)...")
                    await self.m.mower_override()
                elif payload == "PAUSE":
                    logger.info("Sending Pause command...")
                    await self.m.command("Pause")
                elif payload == "PARK":
                    logger.info("Sending Park command (Until next schedule)...")
                    await self.m.mower_park()
                elif payload == "CLEAR_ALL_SCHEDULES":
                    logger.info("Starting transaction to clear all tasks...")
                    transaction_open = False
                    try:
                        await asyncio.wait_for(
                            self.m.command("StartTaskTransaction"), timeout=10.0
                        )
                        transaction_open = True
                        await asyncio.wait_for(
                            self.m.command("DeleteAllTasks"), timeout=10.0
                        )
                        await asyncio.wait_for(
                            self.m.command("CommitTaskTransaction"), timeout=15.0
                        )
                        transaction_open = False
                        logger.info("All tasks deleted and transaction committed.")
                    except asyncio.TimeoutError:
                        if transaction_open:
                            logger.warning(
                                "CRITICAL: Timeout with an open transaction! Mower might block briefly."
                            )
                elif payload.startswith("ADD_TASK:"):
                    logger.info(
                        f"Adding Task: Day {day_idx} at {h}:{m_start} for {dur} min"
                    )
                    transaction_open = False
                    try:
                        await asyncio.wait_for(
                            self.m.command("StartTaskTransaction"), timeout=10.0
                        )
                        transaction_open = True
                        await asyncio.wait_for(
                            self.m.command(
                                "AddTask",
                                day=day_idx,
                                start_h=h,
                                start_m=m_start,
                                duration_m=dur,
                            ),
                            timeout=10.0,
                        )
                        await asyncio.wait_for(
                            self.m.command("CommitTaskTransaction"), timeout=15.0
                        )
                        transaction_open = False
                        logger.info(
                            "Task added and transaction committed successfully."
                        )
                    except asyncio.TimeoutError:
                        if transaction_open:
                            logger.warning(
                                "CRITICAL: Timeout during an open transaction! Subsequent commands might fail temporarily."
                            )

            except Exception as e:
                logger.error(f"Error processing command {payload}: {e}")
            finally:
                if hasattr(self.m, "disconnect"):
                    try:
                        # Always disconnect after polling to free up BlueZ, even if errors occur
                        await asyncio.wait_for(self.m.disconnect(), timeout=5.0)
                    except Exception as clean_err:
                        logger.debug(
                            f"Ignored cleanup error in poll_mower_data: {clean_err}"
                        )

    async def poll_mower_data(self):
        """
        Connects to the mower, reads all data matching the exact Home Assistant
        JSON schema, sends the payload, and disconnects immediately.
        """
        # Request the Bluetooth lock to ensure no commands interfere
        async with ble_lock:
            device = await BleakScanner.find_device_by_address(self.m.address)
            if device is None:
                return "NOT_FOUND"

            try:
                await asyncio.wait_for(self.m.connect(device), timeout=15.0)
                await asyncio.sleep(
                    1.0
                )  # Short delay to ensure connection stability before sending commands

                # 1. Fetch Static Info & Run HA Discovery (Only Once!)
                if not self.static_info:
                    model = await self.m.get_model()
                    manufacturer = await self.m.get_manufacturer()
                    serial_num = await self.m.command("GetSerialNumber")

                    self.static_info = {
                        "Model": str(model),
                        "Manufacturer": str(manufacturer),
                        "SerialNumber": (
                            int(serial_num)
                            if str(serial_num).isdigit()
                            else str(serial_num)
                        ),
                    }

                    if not self.discovery_sent:
                        self.bridge.publish_discovery(
                            serial_num,
                            str(model),
                            manufacturer,
                            self.topic_status,
                            self.topic_cmd,
                        )
                        self.discovery_sent = True

                # Clear previous dynamic data and load static info
                self.msg_state.clear()
                self.msg_state.update(self.static_info)

                # 2. Fetch Core Operational Data
                activity = await self.m.mower_activity()
                state = await self.m.mower_state()
                battery = await self.m.battery_level()
                is_charging = await self.m.is_charging()  # Using your native function!

                self.msg_state.update(
                    {
                        "MowerActivity": str(activity),
                        "MowerStateResponse": str(state),
                        "IsCharging": is_charging,
                        "BatteryLevel": battery,
                    }
                )

                # 3. Fetch Next Scheduled Start Time
                try:
                    next_start_time = (
                        await self.m.mower_next_start_time()
                    )  # Using your native function!
                    if next_start_time:
                        self.msg_state.update(
                            {
                                "Next start time": next_start_time.strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                            }
                        )
                    else:
                        self.msg_state.update({"Next start time": "None"})
                except Exception as time_err:
                    logger.debug(f"Could not fetch next start time: {time_err}")

async def main_loop(config: dict):
    """
    Supervisor loop handling the Smart Polling logic and BlueZ crash recovery.
    """
    global error_counter, m

    while True:
        try:
            # Create a new mower instance for each connection attempt to ensure a clean state
            m = mower.Mower(random.randint(100000000, 999999999), address, pin)

            # Execute one clean Poll-Cycle (Connect -> Read -> Disconnect)
            activity = await poll_mower_data(m, client)
            error_counter = 0  # Reset error counter after a successful cycle
            # --- Smart Polling Interval Logic ---
            if activity in ["1", "2", "3", "MOWING", "SEARCHING", "LEAVING"]:
                sleep_time = config["system"]["poll_active"]
                logger.info(f"Mower is ACTIVE. Sleeping for {sleep_time} seconds.")
            elif activity == "NOT_FOUND":
                sleep_time = 120
                logger.info("Mower NOT FOUND. Sleeping for 120 seconds.")
            else:
                # Default to idle sleep time
                sleep_time = config["system"]["poll_idle"]

                # check if we have a valid next start time to potentially shorten the sleep interval
                next_start_str = msg.get("Next start time", "None")
                if next_start_str != "None":
                    try:
                        # Parse the next start time from the payload
                        next_start = datetime.strptime(
                            next_start_str, "%Y-%m-%d %H:%M:%S"
                        )
                        now = datetime.now()

                        # Calculate the time difference in seconds
                        time_to_start = (next_start - now).total_seconds()

                        # If the mower is scheduled to start within the next 'sleep_time' seconds, we adjust the sleep time to wake up shortly before the mower starts.
                        if 0 < time_to_start < sleep_time:
                            # We want to wake up a bit before the mower starts to ensure we catch the active state as soon as it happens, but we also don't want to wake up too early.
                            # Here we choose to wake up 60 seconds before the scheduled start time, or at the configured active poll interval, whichever is longer, to ensure we are in the right state to catch the mower starting.
                            sleep_time = max(
                                time_to_start - 60, config["system"]["poll_active"]
                            )
                            logger.info(
                                f"Mower starts soon. Adjusting sleep to {sleep_time:.0f} seconds to wake up preemptively."
                            )
                        else:
                            logger.info(
                                f"Mower is IDLE/PARKED. Sleeping for {sleep_time} seconds."
                            )

                    except Exception as e:
                        logger.debug(f"Could not calculate preemptive wakeup: {e}")
                        logger.info(
                            f"Mower is IDLE/PARKED. Sleeping for {sleep_time} seconds."
                        )
                else:
                    logger.info(
                        f"Mower is IDLE/PARKED. Sleeping for {sleep_time} seconds."
                    )
            await asyncio.sleep(sleep_time)

            except Exception as e:
                self.error_counter += 1
                logger.error(f"Main connection loop crashed: {e}")

                logger.info(
                    "Waiting 30 seconds for BlueZ cleanup before reconnecting..."
                )
                await asyncio.sleep(30)


if __name__ == "__main__":
    import signal
    import sys

    cfg_parser = GardenaCfg()
    result = cfg_parser.parse()
    log_level_str = result["system"]["log_level"]
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(numeric_level)
    logging.getLogger().setLevel(numeric_level)

    logger.info(f"Starting Gardena BLE to MQTT Bridge (Log Level: {log_level_str})...")

    bridge = GardenaMQTTBridge(result)

    mower_entities = []
    for mower_cfg in result["mowers"]:
        m = LawnMowerEntity(
            name=mower_cfg["name"],
            address=mower_cfg["address"],
            pin=int(mower_cfg["pin"]),
            bridge=bridge,
            config=result,
        )
        bridge.add_mower(mower_cfg["id"], m)
        mower_entities.append(m)

    bridge.connect_mqtt()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown_handler(sig, frame):
        logger.info("Received stop signal. Shutting down safely...")
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    async def run_all_mowers():
        tasks = [mower.main_loop() for mower in mower_entities]
        await asyncio.gather(*tasks)

    try:
        loop.run_until_complete(run_all_mowers())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        bridge.stop()
        if not loop.is_closed():
            loop.close()
