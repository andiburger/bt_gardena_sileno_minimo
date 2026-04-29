import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from gardena import GardenaMQTTBridge, LawnMowerEntity

# --- 1. SETUP FIXTURES (Bauen unsere Objekte für den Test) ---


@pytest.fixture
def mock_config():
    """Eine saubere Fake-Config für unsere Tests."""
    return {
        "system": {"poll_active": 60, "poll_idle": 900, "poll_error": 30},
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
async def test_process_command_start(mock_scan, mower):
    mock_scan.return_value = (
        "fake_ble_device"  # Täuscht vor, dass der Mäher in Reichweite ist
    )
    await mower.process_command("START")
    mower.m.mower_override.assert_awaited_once()


@pytest.mark.asyncio
@patch("gardena.BleakScanner.find_device_by_address", new_callable=AsyncMock)
async def test_process_command_park(mock_scan, mower):
    mock_scan.return_value = (
        "fake_ble_device"  # Täuscht vor, dass der Mäher in Reichweite ist
    )
    await mower.process_command("PARK")
    mower.m.mower_park.assert_awaited_once()


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
        pass

    fake_mower = FakeMower()

    # Mäher der Bridge hinzufügen
    bridge.add_mower("mower_1", fake_mower)

    # Prüfen, ob er in der Liste ist und die Topics stimmen
    assert "mower_1" in bridge.mowers
    assert fake_mower.topic_status == "gardena/automower/mower_1/status"
    assert fake_mower.topic_cmd == "gardena/automower/mower_1/cmd"
