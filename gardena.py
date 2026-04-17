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
m = None
port = None
topic = None
topic_cmd = None
pin = None
error_counter = 0

# Generate a Client ID
# client_id = f"publish-{random.randint(0, 1000)}"
msg = {}

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
        self.topic = config["mqtt"]["topic"]
        self.topic_cmd = config["mqtt"]["topic_cmd"]
        self.client_id = f"publish-{random.randint(0, 1000)}"

    def connect_mqtt(self):
        """
        Connects to the MQTT broker and sets up callbacks for connection and message handling.
        """

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code == 0:
                logger.info("Connected to MQTT Broker!")
                if self.topic_cmd:
                    client.subscribe(self.topic_cmd)
                    logger.info(f"Subscribed to command topic: {self.topic_cmd}")
            else:
                logger.error(f"Failed to connect, return code {reason_code}")

        def on_message(client, userdata, incoming_msg):
            payload = incoming_msg.payload.decode("utf-8")
            logger.info(f"MQTT Command received: {payload}")
            if loop and m:
                # execute the command in the event loop to avoid blocking the MQTT thread
                asyncio.run_coroutine_threadsafe(process_command(payload), loop)

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

    def publish(self, client: mqtt_client.Client, msg_payload):
        """Publishes a message to the MQTT state topic."""
        if self.topic is None:
            raise ValueError("MQTT topic must be set before publishing.")
        # Using retain=True so Home Assistant always has the latest state upon reboot
        result = client.publish(
            self.topic, json.dumps(msg_payload, indent=4), retain=True
        )
        status = result[0]
        if status == 0:
            logger.info(f"Sent state payload to topic `{self.topic}`")
        else:
            logger.error(f"Failed to send message to topic {self.topic}")

    def publish_discovery(
        self,
        client: mqtt_client.Client,
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
            client.publish(full_topic, json.dumps(payload), retain=True)

        logger.info("Auto-Discovery Setup successfully sent to Home Assistant!")


async def process_command(payload):
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
            device = await BleakScanner.find_device_by_address(address)
            if not device:
                logger.error("Command failed: Mower not found in Bluetooth range.")
                return

            await asyncio.wait_for(m.connect(device), timeout=15.0)
            await asyncio.sleep(
                1.0
            )  # Short delay to ensure connection stability before sending commands

            if payload == "START":
                logger.info("Sending Override (Immediate start for 3 hours)...")
                await m.mower_override()
            elif payload == "PAUSE":
                logger.info("Sending Pause command...")
                await m.command("Pause")
            elif payload == "PARK":
                logger.info("Sending Park command (Until next schedule)...")
                await m.mower_park()
            elif payload == "CLEAR_ALL_SCHEDULES":
                logger.info("Starting transaction to clear all tasks...")
                transaction_open = False
                try:
                    await asyncio.wait_for(
                        m.command("StartTaskTransaction"), timeout=10.0
                    )
                    transaction_open = True
                    await asyncio.wait_for(m.command("DeleteAllTasks"), timeout=10.0)
                    await asyncio.wait_for(
                        m.command("CommitTaskTransaction"), timeout=15.0
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
                        m.command("StartTaskTransaction"), timeout=10.0
                    )
                    transaction_open = True
                    await asyncio.wait_for(
                        m.command(
                            "AddTask",
                            day=day_idx,
                            start_h=h,
                            start_m=m_start,
                            duration_m=dur,
                        ),
                        timeout=10.0,
                    )
                    await asyncio.wait_for(
                        m.command("CommitTaskTransaction"), timeout=15.0
                    )
                    transaction_open = False
                    logger.info("Task added and transaction committed successfully.")
                except asyncio.TimeoutError:
                    if transaction_open:
                        logger.warning(
                            "CRITICAL: Timeout during an open transaction! Subsequent commands might fail temporarily."
                        )

        except Exception as e:
            logger.error(f"Error processing command {payload}: {e}")
        finally:
            # Always disconnect after a command to free up BlueZ
            if hasattr(m, "disconnect"):
                try:
                    await m.disconnect()
                except Exception as clean_err:
                    logger.debug(
                        f"Ignored cleanup error in process_command: {clean_err}"
                    )


async def poll_mower_data(m: mower.Mower, client: mqtt_client.Client):
    """
    Connects to the mower, reads all data matching the exact Home Assistant
    JSON schema, sends the payload, and disconnects immediately.
    """
    global discovery_sent, mower_static_info

    # Request the Bluetooth lock to ensure no commands interfere
    async with ble_lock:
        device = await BleakScanner.find_device_by_address(m.address)
        if device is None:
            return "NOT_FOUND"

        try:
            await asyncio.wait_for(m.connect(device), timeout=15.0)
            await asyncio.sleep(
                1.0
            )  # Short delay to ensure connection stability before sending commands

            # 1. Fetch Static Info & Run HA Discovery (Only Once!)
            if not mower_static_info:
                model = await m.get_model()
                manufacturer = await m.get_manufacturer()
                serial_num = await m.command("GetSerialNumber")

                mower_static_info = {
                    "Model": str(model),
                    "Manufacturer": str(manufacturer),
                    "SerialNumber": (
                        int(serial_num)
                        if str(serial_num).isdigit()
                        else str(serial_num)
                    ),
                }

                if not discovery_sent:
                    publish_discovery(
                        client, serial_num, str(model), manufacturer, topic, topic_cmd
                    )
                    discovery_sent = True

            # Clear previous dynamic data and load static info
            msg.clear()
            msg.update(mower_static_info)

            # 2. Fetch Core Operational Data
            activity = await m.mower_activity()
            state = await m.mower_state()
            battery = await m.battery_level()
            is_charging = await m.is_charging()  # Using your native function!

            msg.update(
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
                    await m.mower_next_start_time()
                )  # Using your native function!
                if next_start_time:
                    msg.update(
                        {
                            "Next start time": next_start_time.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        }
                    )
                else:
                    msg.update({"Next start time": "None"})
            except Exception as time_err:
                logger.debug(f"Could not fetch next start time: {time_err}")

            # 4. Fetch All Statistics (Running Time, Collisions, etc.)
            try:
                statuses = await m.command("GetAllStatistics")
                if isinstance(statuses, dict):
                    # We inject the exact keys like 'totalRunningTime' into our payload
                    for status, value in statuses.items():
                        msg.update({str(status): value})
            except Exception as stat_err:
                logger.warning(f"Could not fetch extended statistics: {stat_err}")

            # Send exactly formatted JSON to MQTT
            publish(client, msg)

            return str(activity)

        finally:
            if hasattr(m, "disconnect"):
                try:
                    await m.disconnect()
                except Exception as clean_err:
                    logger.debug(
                        f"Ignored cleanup error in poll_mower_data: {clean_err}"
                    )


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
            error_counter += 1
            logger.error(f"Main connection loop crashed: {e}")

            logger.info("Waiting 30 seconds for BlueZ cleanup before reconnecting...")
            await asyncio.sleep(30)


if __name__ == "__main__":
    """
    Main entry point.
    """
    import signal
    import sys

    cfg_parser = GardenaCfg()
    result = cfg_parser.parse()
    log_level_str = result["system"]["log_level"]
    # Convert log level string to numeric value
    numeric_level = getattr(logging, log_level_str, logging.INFO)

    # Set log level for our logger
    logger.setLevel(numeric_level)
    # Also set the root logger level to ensure all messages are captured according to the configured level
    logging.getLogger().setLevel(numeric_level)

    logger.info(f"Starting Gardena BLE to MQTT Bridge (Log Level: {log_level_str})...")
    broker = result["mqtt"]["broker"]
    port = int(result["mqtt"]["port"])
    topic = result["mqtt"]["topic"]
    topic_cmd = result["mqtt"]["topic_cmd"]
    address = result["mower"]["address"]
    pin = int(result["mower"]["pin"])

    bridge = GardenaMQTTBridge(result)
    bridge.connect_mqtt()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown_handler(sig, frame):
        logger.info("Received stop signal (SIGTERM/SIGINT). Shutting down safely...")
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)  # Handle Ctrl+C gracefully
    signal.signal(
        signal.SIGTERM, shutdown_handler
    )  # Handle docker stop or system shutdown gracefully

    try:
        loop.run_until_complete(main_loop(result["system"]))
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        # Fallback Cleanup
        bridge.stop()
        if not loop.is_closed():
            loop.close()
