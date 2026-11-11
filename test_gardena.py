import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
import gardena
from gardena import GardenaMQTTBridge, LawnMowerEntity

# --- 1. SETUP FIXTURES (Bauen unsere Objekte für den Test) ---


class StopLoop(BaseException):
    """Raised from a mocked asyncio.sleep to break out of the endless main_loop.
    Derives from BaseException so the loop's 'except Exception' does not swallow it."""


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    """Redirects the static info cache to a temporary folder, so tests never write into the repo."""
    cache_dir = tmp_path / ".cache"
    monkeypatch.setattr("gardena.CACHE_DIR", str(cache_dir))
    return cache_dir


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    """Replaces asyncio.sleep so tests don't really wait (e.g. the 1s BLE stabilization delay)."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("gardena.asyncio.sleep", sleep_mock)
    return sleep_mock


@pytest.fixture
def mock_config():
    """Eine saubere Fake-Config für unsere Tests."""
    return {
        "system": {
            "poll_active": 60,
            "poll_idle": 900,
            "poll_error": 30,
            "poll_winter": 3600,
        },
        "mqtt": {
            "broker": "127.0.0.1",
            "port": 1883,
            "topic_base": "gardena/automower",
        },
        "mowers": [
            {
                "id": "mower_1",
                "name": "Minimo",
                "address": "AA:BB:CC:DD:EE:FF",
                "pin": "0000",
            }
        ],
    }


@pytest.fixture
def bridge(mock_config):
    """Erstellt eine MQTT Bridge und mockt den Paho-Client weg."""
    b = GardenaMQTTBridge(mock_config)

    b.client = MagicMock()  # <--- DIESE ZEILE HINZUFÜGEN!

    return b


@pytest.fixture
def mower(mock_config, bridge):
    """Erstellt eine LawnMowerEntity für unsere Tests."""
    m_cfg = mock_config["mowers"][0]
    entity = LawnMowerEntity(
        name=m_cfg["name"],
        address=m_cfg["address"],
        pin=int(m_cfg["pin"]),
        bridge=bridge,
        config=mock_config,
    )
    # Simuliere die Topic-Zuweisung durch die Bridge
    entity.topic_status = "gardena/automower/mower_1/status"
    entity.topic_cmd = "gardena/automower/mower_1/cmd"

    # Wir erzeugen ein Fake-Bluetooth-Objekt und hängen es direkt in die Entity (self.m)
    mock_ble_mower = AsyncMock()
    entity.m = mock_ble_mower
    return entity


# --- 2. COMMAND TESTS ---


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_invalid(mock_scan, mower):  # <-- caplog hier entfernt
    mock_scan.return_value = "fake_ble_device"

    # Bei einem ungültigen Befehl darf das BLE Objekt nicht aufgerufen werden
    await mower.process_command("JUMP")
    mower.m.mower_override.assert_not_called()
    mower.m.mower_park.assert_not_called()
    # Die "assert in caplog.text" Zeile haben wir komplett gelöscht!


# --- 3. POLLING TESTS ---


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_mower_data_success(mock_scan, mower):
    # 1. Simuliere, dass der Scanner den Mäher findet
    mock_scan.return_value = "fake_ble_device"

    # 2. Simuliere die Antworten des Mähers
    mower.m.get_model.return_value = "Sileno Minimo"
    mower.m.get_manufacturer.return_value = "Gardena"
    mower.m.battery_level.return_value = 85
    mower.m.mower_activity.return_value = "3"  # 3 = Mowing
    mower.m.mower_state.return_value = "1"
    mower.m.is_charging.return_value = False
    mower.m.command.return_value = {"totalRunningTime": 3600}

    mower.m.mower_next_start_time.return_value = None

    # 3. Funktion aufrufen (Achtung: Prüfe ob die Methode bei dir poll_mower_data oder poll_data heißt)
    activity = await mower.poll_mower_data()

    # 4. Prüfen, ob die Bridge den Status per MQTT publisht hat
    assert activity == "3"
    mower.bridge.client.publish.assert_called()

    # 5. Prüfen, was genau gesendet wurde
    args, kwargs = mower.bridge.client.publish.call_args
    topic_called = args[0]
    payload_called = args[1]

    assert topic_called == "gardena/automower/mower_1/status"
    assert '"BatteryLevel": 85' in payload_called
    assert '"MowerActivity": "3"' in payload_called


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_mower_data_not_found(mock_scan, mower):
    # Scanner findet nichts
    mock_scan.return_value = None

    activity = await mower.poll_mower_data()

    # Muss NOT_FOUND zurückgeben
    assert activity == "NOT_FOUND"

    # Es sollte kein publish stattgefunden haben (außer vllt. Discovery)
    assert not mower.m.connect.called


# --- 4. BRIDGE ROUTING TESTS ---


def test_bridge_add_mower(mock_config):
    """Testet, ob die Bridge neuen Mähern die korrekten Topics zuweist."""
    bridge = GardenaMQTTBridge(mock_config)

    # Wir erzeugen ein leeres Dummy-Objekt (Fake-Mäher)
    class FakeMower:
        def __init__(self):
            self.topic_status = None
            self.topic_cmd = None

    fake_mower = FakeMower()

    # Mäher der Bridge hinzufügen
    bridge.add_mower("mower_1", fake_mower)

    # Prüfen, ob er in der Liste ist und die Topics stimmen
    assert "mower_1" in bridge.mowers
    assert fake_mower.topic_status == "gardena/automower/mower_1/status"
    assert fake_mower.topic_cmd == "gardena/automower/mower_1/cmd"


# --- 5. COMMAND PROCESSING TESTS (Der fette Brocken für Coverage!) ---


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_start(mock_scan, mower):
    """Testet, ob ein START-Befehl sauber an den Mäher geschickt wird."""
    # 1. Mocking aufbauen (Wir tun so, als wäre der Mäher erreichbar)
    mock_scan.return_value = MagicMock()
    mower.m.connect = AsyncMock()
    mower.m.start = AsyncMock()
    mower.m.disconnect = AsyncMock()

    # 2. Funktion mit "START" Payload aufrufen
    await mower.process_command(b"START")

    # 3. Behauptungen prüfen: Hat er sich verbunden, gestartet und getrennt?
    mower.m.connect.assert_called_once()
    mower.m.mower_override.assert_called_once()
    mower.m.disconnect.assert_called_once()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_park(mock_scan, mower):
    """Testet, ob ein PARK-Befehl sauber verarbeitet wird."""
    mock_scan.return_value = MagicMock()
    mower.m.connect = AsyncMock()
    mower.m.park_until_further_notice = (
        AsyncMock()
    )  # Oder wie die Methode bei dir heißt
    mower.m.disconnect = AsyncMock()

    # Funktion mit "PARK" Payload aufrufen
    await mower.process_command(b"PARK")

    # Prüfen, ob der Bluetooth-Parkbefehl gefeuert wurde
    assert mower.m.connect.called
    mower.m.mower_park.assert_called_once()
    assert mower.m.disconnect.called


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_pause(mock_scan, mower):
    mock_scan.return_value = MagicMock()

    await mower.process_command("PAUSE")

    mower.m.command.assert_called_once_with("Pause")
    mower.m.disconnect.assert_called_once()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_clear_all_schedules(mock_scan, mower):
    """CLEAR_ALL_SCHEDULES runs a complete transaction in the correct order."""
    mock_scan.return_value = MagicMock()

    await mower.process_command("CLEAR_ALL_SCHEDULES")

    called = [c.args[0] for c in mower.m.command.call_args_list]
    assert called == ["StartTaskTransaction", "DeleteAllTasks", "CommitTaskTransaction"]


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_add_task_valid(mock_scan, mower):
    """A valid ADD_TASK payload is parsed and sent inside a transaction."""
    mock_scan.return_value = MagicMock()

    await mower.process_command("ADD_TASK:2,9,30,90")

    called = [c.args[0] for c in mower.m.command.call_args_list]
    assert called == ["StartTaskTransaction", "AddTask", "CommitTaskTransaction"]
    mower.m.command.assert_any_call(
        "AddTask", day=2, start_h=9, start_m=30, duration_m=90
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "ADD_TASK:7,9,30,90",  # day out of range
        "ADD_TASK:2,24,30,90",  # hour out of range
        "ADD_TASK:2,9,60,90",  # minute out of range
        "ADD_TASK:2,9,30,0",  # duration must be > 0
        "ADD_TASK:a,b,c,d",  # non-numeric
        "ADD_TASK:1,2",  # too few parameters
        "ADD_TASK:1,2,3,4,5",  # too many parameters
    ],
)
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_add_task_invalid_never_touches_ble(
    mock_scan, payload, mower
):
    """Invalid schedules are rejected BEFORE any Bluetooth scan happens."""
    await mower.process_command(payload)

    mock_scan.assert_not_called()
    mower.m.connect.assert_not_called()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_mower_not_found(mock_scan, mower):
    mock_scan.return_value = None

    await mower.process_command("START")

    mower.m.connect.assert_not_called()
    mower.m.mower_override.assert_not_called()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_error_still_disconnects(mock_scan, mower):
    """A BLE error must not crash the command handler and must always free the connection."""
    mock_scan.return_value = MagicMock()
    mower.m.mower_override.side_effect = RuntimeError("BLE write failed")

    await mower.process_command("START")  # must not raise

    mower.m.disconnect.assert_called_once()


# --- 6. WINTER MODE TESTS ---


def _published_payloads(bridge, topic):
    """Helper: returns all JSON payloads the bridge published to the given topic."""
    return [
        json.loads(c.args[1])
        for c in bridge.client.publish.call_args_list
        if c.args[0] == topic
    ]


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_winter_on_activates_without_ble(mock_scan, mower):
    mower.static_info = {"SerialNumber": 12345, "Model": "Minimo"}

    await mower.process_command(b"WINTER_ON")

    assert mower.winter_mode is True
    mock_scan.assert_not_called()
    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["MowerActivity"] == "8"
    assert payload["WinterMode"] == "ON"
    assert payload["SerialNumber"] == 12345  # static info is kept for HA


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_winter_off_deactivates_without_ble(mock_scan, mower):
    mower.winter_mode = True

    await mower.process_command("WINTER_OFF")

    assert mower.winter_mode is False
    mock_scan.assert_not_called()
    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["WinterMode"] == "OFF"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", ["START", "PAUSE", "PARK", "CLEAR_ALL_SCHEDULES", "ADD_TASK:1,9,0,60"]
)
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_commands_rejected_in_winter_mode(mock_scan, payload, mower):
    mower.winter_mode = True

    await mower.process_command(payload)

    mock_scan.assert_not_called()
    mower.m.connect.assert_not_called()


# --- 7. STATIC INFO CACHE TESTS ---


def test_cache_path_uses_mac_address(mower, isolated_cache_dir):
    assert mower._cache_path() == str(isolated_cache_dir / "AA_BB_CC_DD_EE_FF.json")


def test_cache_save_and_load_roundtrip(mower, mock_config, bridge):
    mower.static_info = {
        "Model": "Minimo",
        "Manufacturer": "Gardena",
        "SerialNumber": 1,
    }
    mower._save_static_info_cache()

    fresh = LawnMowerEntity("Minimo", "AA:BB:CC:DD:EE:FF", 0, bridge, mock_config)
    assert fresh._load_static_info_cache() is True
    assert fresh.static_info == mower.static_info


def test_cache_load_missing_file_returns_false(mower):
    assert mower._load_static_info_cache() is False
    assert mower.static_info == {}


def test_cache_load_corrupt_file_returns_false(mower, isolated_cache_dir):
    isolated_cache_dir.mkdir()
    (isolated_cache_dir / "AA_BB_CC_DD_EE_FF.json").write_text("{not valid json")

    assert mower._load_static_info_cache() is False


def test_cache_save_failure_does_not_raise(mower, monkeypatch):
    """A read-only filesystem must not crash the bridge."""
    monkeypatch.setattr("gardena.os.makedirs", MagicMock(side_effect=OSError("ro")))
    mower.static_info = {"Model": "Minimo"}

    mower._save_static_info_cache()  # must not raise


# --- 8. POLLING DETAIL TESTS ---


def _setup_reachable_mower(mower, activity="5"):
    """Helper: configures the mocked BLE mower with realistic answers."""
    mower.m.get_model.return_value = "Sileno Minimo"
    mower.m.get_manufacturer.return_value = "Gardena"
    mower.m.battery_level.return_value = 85
    mower.m.mower_activity.return_value = activity
    mower.m.mower_state.return_value = "1"
    mower.m.is_charging.return_value = True
    mower.m.mower_next_start_time.return_value = datetime(2026, 11, 5, 10, 0, 0)
    mower.m.command.side_effect = lambda name, **kw: (
        "12345678" if name == "GetSerialNumber" else {"numberOfCollisions": 7}
    )


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_payload_contents(mock_scan, mower):
    mock_scan.return_value = MagicMock()
    _setup_reachable_mower(mower)

    await mower.poll_mower_data()

    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["SerialNumber"] == 12345678  # numeric serial is stored as int
    assert payload["Next start time"] == "2026-11-05 10:00:00"
    assert payload["numberOfCollisions"] == 7
    assert payload["IsCharging"] is True
    assert payload["WinterMode"] == "OFF"
    mower.m.disconnect.assert_called_once()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_writes_cache_and_sends_discovery_once(
    mock_scan, mower, isolated_cache_dir
):
    mock_scan.return_value = MagicMock()
    _setup_reachable_mower(mower)

    await mower.poll_mower_data()
    await mower.poll_mower_data()

    # Static info is only fetched once, and written to the cache
    mower.m.get_model.assert_called_once()
    cached = json.loads((isolated_cache_dir / "AA_BB_CC_DD_EE_FF.json").read_text())
    assert cached == {
        "Model": "Sileno Minimo",
        "Manufacturer": "Gardena",
        "SerialNumber": 12345678,
    }
    # Discovery (incl. winter switch) is only sent once
    winter_topic = "homeassistant/switch/gardena_minimo/winter_mode/config"
    topics = [c.args[0] for c in mower.bridge.client.publish.call_args_list]
    assert topics.count(winter_topic) == 1


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_error_propagates_but_disconnects(mock_scan, mower):
    """Errors bubble up to main_loop (for recovery), but the BLE connection is always freed."""
    mock_scan.return_value = MagicMock()
    _setup_reachable_mower(mower)
    mower.m.mower_activity.side_effect = RuntimeError("Notify acquired")

    with pytest.raises(RuntimeError):
        await mower.poll_mower_data()

    mower.m.disconnect.assert_called_once()


# --- 9. HOME ASSISTANT DISCOVERY TESTS ---


def test_publish_discovery_sends_all_entities(bridge):
    bridge.publish_discovery("123", "Minimo", "Gardena", "state/t", "cmd/t")

    calls = bridge.client.publish.call_args_list
    assert len(calls) == 14
    assert all(c.args[0].startswith("homeassistant/") for c in calls)
    assert all(c.kwargs.get("retain") is True for c in calls)


def test_publish_discovery_winter_switch(bridge):
    bridge.publish_discovery("123", "Minimo", "Gardena", "state/t", "cmd/t")

    configs = {
        c.args[0]: json.loads(c.args[1]) for c in bridge.client.publish.call_args_list
    }
    switch = configs["homeassistant/switch/gardena_minimo/winter_mode/config"]
    assert switch["unique_id"] == "g_winter_123"
    assert switch["command_topic"] == "cmd/t"
    assert switch["state_topic"] == "state/t"
    assert switch["payload_on"] == "WINTER_ON"
    assert switch["payload_off"] == "WINTER_OFF"
    assert switch["value_template"] == "{{ value_json.WinterMode }}"


# --- 10. MQTT BRIDGE TESTS ---


def test_bridge_requires_broker(mock_config):
    mock_config["mqtt"]["broker"] = ""
    with pytest.raises(ValueError):
        GardenaMQTTBridge(mock_config)


def test_bridge_publish_uses_retain_and_json(bridge):
    bridge.client.publish.return_value = (0, 1)

    bridge.publish("some/topic", {"BatteryLevel": 50})

    args, kwargs = bridge.client.publish.call_args
    assert args[0] == "some/topic"
    assert json.loads(args[1]) == {"BatteryLevel": 50}
    assert kwargs["retain"] is True


def test_bridge_publish_without_topic_raises(bridge):
    with pytest.raises(ValueError):
        bridge.publish(None, {})


def test_bridge_publish_failure_does_not_raise(bridge):
    bridge.client.publish.return_value = (1, 1)  # non-zero = failed
    bridge.publish("some/topic", {})  # must only log, not raise


@pytest.fixture
def connected_bridge(bridge):
    """Runs connect_mqtt with a mocked paho client and returns (bridge, client_mock)."""
    with patch("gardena.mqtt_client.Client") as client_cls:
        bridge.connect_mqtt()
    return bridge, client_cls.return_value


def test_on_connect_subscribes_to_all_command_topics(connected_bridge):
    bridge, client = connected_bridge
    m1, m2 = MagicMock(topic_cmd="t/mower_1/cmd"), MagicMock(topic_cmd="t/mower_2/cmd")
    bridge.mowers = {"mower_1": m1, "mower_2": m2}

    client.on_connect(client, None, None, 0, None)

    client.subscribe.assert_any_call("t/mower_1/cmd")
    client.subscribe.assert_any_call("t/mower_2/cmd")


def test_on_message_routes_command_to_correct_mower(connected_bridge, monkeypatch):
    bridge, client = connected_bridge
    m1, m2 = MagicMock(topic_cmd="t/mower_1/cmd"), MagicMock(topic_cmd="t/mower_2/cmd")
    bridge.mowers = {"mower_1": m1, "mower_2": m2}
    monkeypatch.setattr("gardena.loop", object())
    run_threadsafe = MagicMock()
    monkeypatch.setattr("gardena.asyncio.run_coroutine_threadsafe", run_threadsafe)

    client.on_message(
        client, None, MagicMock(topic="t/mower_2/cmd", payload=b"WINTER_ON")
    )

    m2.process_command.assert_called_once_with("WINTER_ON")
    m1.process_command.assert_not_called()
    run_threadsafe.assert_called_once()


def test_on_message_ignored_without_event_loop(connected_bridge, monkeypatch):
    bridge, client = connected_bridge
    m1 = MagicMock(topic_cmd="t/mower_1/cmd")
    bridge.mowers = {"mower_1": m1}
    monkeypatch.setattr("gardena.loop", None)
    run_threadsafe = MagicMock()
    monkeypatch.setattr("gardena.asyncio.run_coroutine_threadsafe", run_threadsafe)

    client.on_message(client, None, MagicMock(topic="t/mower_1/cmd", payload=b"START"))

    run_threadsafe.assert_not_called()


# --- 11. MAIN LOOP (SMART POLLING & RECOVERY) TESTS ---


async def _run_main_loop_once(mower):
    """Runs main_loop until the mocked asyncio.sleep raises StopLoop."""
    with pytest.raises(StopLoop):
        await mower.main_loop()


@pytest.mark.asyncio
async def test_main_loop_sends_discovery_from_cache_on_startup(
    mower, fast_sleep, isolated_cache_dir
):
    """With a cache file, HA discovery is sent at startup, even if the mower is unreachable."""
    isolated_cache_dir.mkdir()
    (isolated_cache_dir / "AA_BB_CC_DD_EE_FF.json").write_text(
        json.dumps({"Model": "Minimo", "Manufacturer": "Gardena", "SerialNumber": 42})
    )
    mower.poll_mower_data = AsyncMock(return_value="NOT_FOUND")
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    assert mower.discovery_sent is True
    configs = {
        c.args[0]: json.loads(c.args[1])
        for c in mower.bridge.client.publish.call_args_list
        if c.args[0].startswith("homeassistant/")
    }
    switch = configs["homeassistant/switch/gardena_minimo/winter_mode/config"]
    assert switch["unique_id"] == "g_winter_42"


@pytest.mark.asyncio
async def test_main_loop_winter_mode_skips_ble(mower, fast_sleep):
    mower.winter_mode = True
    mower.poll_mower_data = AsyncMock()
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    mower.poll_mower_data.assert_not_called()
    fast_sleep.assert_called_once_with(3600)
    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["MowerActivity"] == "8"


@pytest.mark.asyncio
@pytest.mark.parametrize("activity", ["1", "2", "3"])
async def test_main_loop_active_uses_poll_active(mower, fast_sleep, activity):
    mower.poll_mower_data = AsyncMock(return_value=activity)
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    fast_sleep.assert_called_once_with(60)


@pytest.mark.asyncio
async def test_main_loop_not_found_publishes_error(mower, fast_sleep):
    mower.poll_mower_data = AsyncMock(return_value="NOT_FOUND")
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    fast_sleep.assert_called_once_with(120)
    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["MowerActivity"] == "7"


@pytest.mark.asyncio
async def test_main_loop_idle_without_schedule_uses_poll_idle(mower, fast_sleep):
    mower.poll_mower_data = AsyncMock(return_value="5")
    mower.msg_state = {"Next start time": "None"}
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    fast_sleep.assert_called_once_with(900)


@pytest.mark.asyncio
async def test_main_loop_idle_wakes_up_before_next_start(mower, fast_sleep):
    """If the next start is within poll_idle, the loop wakes up ~60s before it."""
    next_start = datetime.now() + timedelta(seconds=600)
    mower.poll_mower_data = AsyncMock(return_value="5")
    mower.msg_state = {"Next start time": next_start.strftime("%Y-%m-%d %H:%M:%S")}
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    sleep_time = fast_sleep.call_args.args[0]
    assert 60 <= sleep_time < 600 - 50  # ~540s, never below poll_active


@pytest.mark.asyncio
async def test_main_loop_idle_next_start_far_away_uses_poll_idle(mower, fast_sleep):
    next_start = datetime.now() + timedelta(days=2)
    mower.poll_mower_data = AsyncMock(return_value="5")
    mower.msg_state = {"Next start time": next_start.strftime("%Y-%m-%d %H:%M:%S")}
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    fast_sleep.assert_called_once_with(900)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        "[org.bluez.Error.NotPermitted] Notify acquired",
        "('No powered Bluetooth adapters found.', <BleakBluetoothNotAvailableReason.POWERED_OFF: 3>)",
    ],
)
@patch("gardena.subprocess.run")
async def test_main_loop_bluetooth_error_triggers_recovery(
    mock_run, mower, fast_sleep, error
):
    mower.poll_mower_data = AsyncMock(side_effect=Exception(error))
    fast_sleep.side_effect = [None, StopLoop()]  # 10s chip init, then 30s cleanup

    await _run_main_loop_once(mower)

    commands = [c.args[0] for c in mock_run.call_args_list]
    assert commands == [
        ["sudo", "-n", "rfkill", "unblock", "bluetooth"],
        ["sudo", "-n", "systemctl", "restart", "bluetooth"],
        ["sudo", "-n", "hciconfig", "hci0", "up"],
    ]
    assert mower.error_counter == 1
    assert [c.args[0] for c in fast_sleep.call_args_list] == [10, 30]
    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["MowerActivity"] == "7"


@pytest.mark.asyncio
@patch("gardena.subprocess.run")
async def test_main_loop_generic_error_skips_recovery(mock_run, mower, fast_sleep):
    mower.poll_mower_data = AsyncMock(side_effect=TimeoutError("timeout"))
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    mock_run.assert_not_called()
    fast_sleep.assert_called_once_with(30)


@pytest.mark.asyncio
@patch("gardena.subprocess.run")
async def test_main_loop_failed_recovery_does_not_crash(mock_run, mower, fast_sleep):
    """If sudo is not permitted (systemctl fails), the loop keeps running."""
    mock_run.side_effect = [None, Exception("sudo: a password is required"), None]
    mower.poll_mower_data = AsyncMock(side_effect=Exception("NotPermitted"))
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    fast_sleep.assert_called_once_with(30)  # skipped the 10s wait, went to cleanup


@pytest.mark.asyncio
async def test_main_loop_resets_error_counter_after_success(mower, fast_sleep):
    mower.error_counter = 3
    mower.poll_mower_data = AsyncMock(return_value="3")
    fast_sleep.side_effect = StopLoop()

    await _run_main_loop_once(mower)

    assert mower.error_counter == 0


# --- 12. ERROR PATH TESTS (Timeouts, partial failures, cleanup) ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, failing_step",
    [
        ("CLEAR_ALL_SCHEDULES", "DeleteAllTasks"),
        ("ADD_TASK:1,9,0,60", "AddTask"),
    ],
)
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_transaction_timeout_is_handled(mock_scan, payload, failing_step, mower):
    """A timeout inside an open transaction must not commit, crash, or keep the connection."""
    mock_scan.return_value = MagicMock()

    def command(name, **kwargs):
        if name == failing_step:
            raise asyncio.TimeoutError()

    mower.m.command.side_effect = command

    await mower.process_command(payload)  # must not raise

    called = [c.args[0] for c in mower.m.command.call_args_list]
    assert "CommitTaskTransaction" not in called
    mower.m.disconnect.assert_called_once()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_command_disconnect_error_is_ignored(mock_scan, mower):
    mock_scan.return_value = MagicMock()
    mower.m.disconnect.side_effect = RuntimeError("already disconnected")

    await mower.process_command("START")  # must not raise

    mower.m.mower_override.assert_called_once()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_survives_missing_next_start_and_statistics(mock_scan, mower):
    """Optional data failing must not prevent the core status from being published."""
    mock_scan.return_value = MagicMock()
    _setup_reachable_mower(mower)
    mower.m.mower_next_start_time.side_effect = RuntimeError("not supported")

    def command(name, **kwargs):
        if name == "GetAllStatistics":
            raise RuntimeError("stats unavailable")
        return "12345678"

    mower.m.command.side_effect = command

    activity = await mower.poll_mower_data()

    assert activity == "5"
    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["BatteryLevel"] == 85
    assert "Next start time" not in payload
    assert "numberOfCollisions" not in payload


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_next_start_none(mock_scan, mower):
    mock_scan.return_value = MagicMock()
    _setup_reachable_mower(mower)
    mower.m.mower_next_start_time.return_value = None

    await mower.poll_mower_data()

    payload = _published_payloads(mower.bridge, mower.topic_status)[-1]
    assert payload["Next start time"] == "None"


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_poll_disconnect_error_is_ignored(mock_scan, mower):
    mock_scan.return_value = MagicMock()
    _setup_reachable_mower(mower)
    mower.m.disconnect.side_effect = RuntimeError("already disconnected")

    assert await mower.poll_mower_data() == "5"


@pytest.mark.asyncio
async def test_main_loop_winter_mode_keeps_looping(mower, fast_sleep):
    """Winter mode keeps sleeping in poll_winter cycles and never touches BLE."""
    mower.winter_mode = True
    mower.poll_mower_data = AsyncMock()
    fast_sleep.side_effect = [None, None, StopLoop()]

    await _run_main_loop_once(mower)

    assert [c.args[0] for c in fast_sleep.call_args_list] == [3600, 3600, 3600]
    mower.poll_mower_data.assert_not_called()


@pytest.mark.asyncio
async def test_main_loop_resumes_polling_after_winter_off(mower, fast_sleep):
    """After WINTER_OFF arrives during the winter sleep, the next cycle polls again."""
    mower.winter_mode = True
    mower.poll_mower_data = AsyncMock(return_value="5")

    async def sleep(seconds):
        if seconds == 3600:
            await mower.process_command("WINTER_OFF")
            return
        raise StopLoop()

    fast_sleep.side_effect = sleep

    await _run_main_loop_once(mower)

    mower.poll_mower_data.assert_called_once()


def test_on_connect_failure_does_not_subscribe(connected_bridge):
    bridge, client = connected_bridge
    bridge.mowers = {"mower_1": MagicMock(topic_cmd="t/mower_1/cmd")}

    client.on_connect(client, None, None, 5, None)  # 5 = not authorized

    client.subscribe.assert_not_called()


def test_bridge_stop_disconnects(connected_bridge):
    bridge, client = connected_bridge

    bridge.stop()

    client.loop_stop.assert_called_once()
    client.disconnect.assert_called_once()


# --- 13. SECURITY HARDENING TESTS ---


def test_bridge_init_does_not_leak_secrets_to_stdout(mock_config, capsys):
    mock_config["mowers"][0]["pin"] = "9876"
    mock_config["mqtt"]["password"] = "top-secret-pw"

    bridge = GardenaMQTTBridge(mock_config)
    captured = capsys.readouterr()

    assert "9876" not in captured.out
    assert "top-secret-pw" not in captured.out
    assert bridge.client_id.startswith("gardena-bridge-")


def test_connect_mqtt_sets_credentials_and_tls(mock_config):
    mock_config["mqtt"]["username"] = "gardena_user"
    mock_config["mqtt"]["password"] = "secret"
    mock_config["mqtt"]["tls"] = True
    mock_config["mqtt"]["ca_certs"] = "/etc/ssl/ca.pem"
    bridge = GardenaMQTTBridge(mock_config)

    with patch("gardena.mqtt_client.Client") as client_cls:
        bridge.connect_mqtt()
        client = client_cls.return_value

    assert client.suppress_exceptions is True
    client.username_pw_set.assert_called_once_with("gardena_user", "secret")
    client.tls_set.assert_called_once_with(ca_certs="/etc/ssl/ca.pem")


def test_on_message_survives_invalid_utf8_and_callback_errors(
    connected_bridge, monkeypatch
):
    bridge, client = connected_bridge
    m1 = MagicMock(topic_cmd="t/mower_1/cmd")
    bridge.mowers = {"mower_1": m1}
    monkeypatch.setattr("gardena.loop", object())
    run_threadsafe = MagicMock(side_effect=RuntimeError("loop closed"))
    monkeypatch.setattr("gardena.asyncio.run_coroutine_threadsafe", run_threadsafe)

    # Invalid UTF-8 bytes and an exception inside run_coroutine_threadsafe must both be caught
    client.on_message(
        client, None, MagicMock(topic="t/mower_1/cmd", payload=b"\xff\xfeSTART")
    )
    run_threadsafe.assert_called_once()
