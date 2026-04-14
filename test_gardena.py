import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import gardena  # Imports your script


# --- NEW: Setup global variables ---
# process_command needs 'gardena.address' to scan for the device.
# We set a dummy address here so it doesn't fail on 'None'.
@pytest.fixture(autouse=True)
def set_globals():
    gardena.address = "00:11:22:33:44:55"
    yield


# --- NEW: Mock the Bluetooth Scanner ---
# We simulate BleakScanner so it always "finds" a fake device
# instead of actually searching your house for Bluetooth signals.
@pytest.fixture(autouse=True)
def mock_scanner():
    with patch(
        "gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock
    ) as mock_scan:
        mock_scan.return_value = "fake_device_object"
        yield mock_scan


# This fixture simulates the mower before each test
@pytest.fixture
def mock_mower():
    # We intercept the global 'm' object in gardena.py
    with patch("gardena.m", create=True) as mock_m:
        mock_m.mower_override = AsyncMock()
        mock_m.mower_park = AsyncMock()
        mock_m.connect = AsyncMock()
        mock_m.disconnect = AsyncMock()

        # --- NEW MOCKS FOR POLLING ---
        mock_m.get_model = AsyncMock(return_value="Sileno Minimo")
        mock_m.get_manufacturer = AsyncMock(return_value="Gardena")
        mock_m.mower_activity = AsyncMock(return_value="3")  # "3" = Mowing
        mock_m.mower_state = AsyncMock(return_value="2")
        mock_m.battery_level = AsyncMock(return_value=85)
        mock_m.is_charging = AsyncMock(return_value=False)
        mock_m.mower_next_start_time = AsyncMock(return_value=None)

        # The 'command' function needs to return different data based on the command string
        async def command_side_effect(cmd, **kwargs):
            if cmd == "GetSerialNumber":
                return "123456789"
            if cmd == "GetAllStatistics":
                return {"totalRunningTime": 3600, "numberOfCollisions": 5}
            return None

        mock_m.command = AsyncMock(side_effect=command_side_effect)

        yield mock_m


# 1. Test: START command
@pytest.mark.asyncio
async def test_process_command_start(mock_mower):
    await gardena.process_command("START")

    # Check if connected, commanded, and cleanly disconnected
    mock_mower.connect.assert_awaited_once()
    mock_mower.mower_override.assert_awaited_once()
    mock_mower.disconnect.assert_awaited_once()


# 2. Test: PARK command
@pytest.mark.asyncio
async def test_process_command_park(mock_mower):
    await gardena.process_command("PARK")

    mock_mower.connect.assert_awaited_once()
    mock_mower.mower_park.assert_awaited_once()
    mock_mower.disconnect.assert_awaited_once()


# 3. Test: Successful task transaction (ADD_TASK)
@pytest.mark.asyncio
async def test_process_command_add_task_valid(mock_mower):
    # Simulate MQTT Payload: Monday, 08:30 AM, 120 minutes
    await gardena.process_command("ADD_TASK:0,8,30,120")

    mock_mower.connect.assert_awaited_once()

    # Check if exactly 3 Bluetooth commands were transmitted
    assert mock_mower.command.await_count == 3
    mock_mower.command.assert_any_await("StartTaskTransaction")
    mock_mower.command.assert_any_await(
        "AddTask", day=0, start_h=8, start_m=30, duration_m=120
    )
    mock_mower.command.assert_any_await("CommitTaskTransaction")

    mock_mower.disconnect.assert_awaited_once()


# 4. Test: Invalid values (Pre-Validation Check)
@pytest.mark.asyncio
async def test_process_command_add_task_invalid_day(mock_mower):
    # Day 9 does not exist!
    await gardena.process_command("ADD_TASK:9,8,30,120")

    # The code must abort BEFORE connecting to Bluetooth
    mock_mower.connect.assert_not_awaited()
    mock_mower.command.assert_not_awaited()


# 5. Test: Invalid format (Strings instead of numbers)
@pytest.mark.asyncio
async def test_process_command_add_task_invalid_format(mock_mower):
    # Pass text instead of numbers
    await gardena.process_command("ADD_TASK:Monday,A,B,C")

    # The ValueError must catch this; no Bluetooth connection should be established
    mock_mower.connect.assert_not_awaited()
    mock_mower.command.assert_not_awaited()


# 6. Test: Bluetooth Timeout Robustness
@pytest.mark.asyncio
async def test_process_command_bluetooth_timeout(mock_mower):
    # We force the mock to run into a timeout when sending the first command
    mock_mower.command.side_effect = asyncio.TimeoutError()

    # The script must not crash here, but catch the error in the log
    try:
        await gardena.process_command("CLEAR_ALL_SCHEDULES")
    except Exception:
        pytest.fail("process_command threw an Exception instead of catching it!")

    mock_mower.command.assert_awaited_once_with("StartTaskTransaction")

    # NEW: We must ensure that EVEN THOUGH it crashed, it still cleanly disconnected!
    mock_mower.disconnect.assert_awaited_once()


# 7. Test: Polling success (Read data & Publish JSON)
@pytest.mark.asyncio
@patch("gardena.publish")  # We mock 'publish' so we don't need a real MQTT broker
@patch("gardena.publish_discovery")  # Prevent sending HA discovery configs
async def test_poll_mower_data_success(mock_pub_discovery, mock_publish, mock_mower):
    dummy_client = "dummy_mqtt_client"

    # Reset the global flags to simulate a fresh start
    gardena.discovery_sent = False
    gardena.mower_static_info = {}

    # Run the polling function
    activity = await gardena.poll_mower_data(mock_mower, dummy_client)

    # Check if connected and disconnected cleanly
    mock_mower.connect.assert_awaited_once()
    mock_mower.disconnect.assert_awaited_once()

    # Check if publish was called successfully
    mock_publish.assert_called_once()

    # Extract the dictionary that was sent to publish()
    published_msg = mock_publish.call_args[0][1]

    # Verify the JSON payload matches our exact expectations
    assert published_msg["Model"] == "Sileno Minimo"
    assert published_msg["BatteryLevel"] == 85
    assert published_msg["MowerActivity"] == "3"
    assert published_msg["totalRunningTime"] == 3600  # Fetched from GetAllStatistics
    assert published_msg["IsCharging"] is False

    # The function must return the activity string for the Smart Sleep logic
    assert activity == "3"


# 8. Test: Polling when mower is out of range
@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_mower_data_not_found(mock_scan, mock_mower):
    # We forcefully overwrite the scanner to NOT find the device
    mock_scan.return_value = None

    dummy_client = "dummy_mqtt_client"
    activity = await gardena.poll_mower_data(mock_mower, dummy_client)

    # It must return NOT_FOUND immediately
    assert activity == "NOT_FOUND"

    # CRITICAL: It must NEVER try to connect to a None-Device (prevents crashes)
    mock_mower.connect.assert_not_awaited()
