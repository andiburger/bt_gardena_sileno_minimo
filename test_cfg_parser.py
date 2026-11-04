import pytest
from unittest.mock import patch
from cfg_parser import GardenaCfg


def test_gardena_cfg_parse_success():
    """
    Tests if the GardenaCfg parser correctly extracts all required
    values from a simulated config file with MULTIPLE mowers.
    """
    cfg_parser = GardenaCfg()

    cfg_parser.config.read_dict(
        {
            "mower_1": {"name": "Front", "address": "AA:BB:CC:DD:EE:FF", "pin": "1234"},
            "mower_2": {"name": "Back", "address": "11:22:33:44:55:66", "pin": "5678"},
            "mqtt": {
                "broker": "192.168.1.100",
                "port": "1883",
                "topic_base": "gardena/automower",
            },
            "system": {
                "log_level": "DEBUG",
                "poll_active": "30",
            },
        }
    )

    with patch.object(cfg_parser.config, "read") as mock_read:
        result = cfg_parser.parse()

        mock_read.assert_called_once_with("cfg.ini")

        assert len(result["mowers"]) == 2

        assert result["mowers"][0]["id"] == "mower_1"
        assert result["mowers"][0]["name"] == "Front"
        assert result["mowers"][0]["address"] == "AA:BB:CC:DD:EE:FF"
        assert result["mowers"][0]["pin"] == "1234"

        assert result["mowers"][1]["id"] == "mower_2"
        assert result["mowers"][1]["address"] == "11:22:33:44:55:66"

        assert result["mqtt"]["broker"] == "192.168.1.100"
        assert result["mqtt"]["topic_base"] == "gardena/automower"
        assert result["system"]["poll_active"] == 30


def test_gardena_cfg_uses_defaults():
    """
    Tests if the parser applies the correct default fallback values
    when keys are completely missing in the configuration file.
    """
    cfg_parser = GardenaCfg()

    cfg_parser.config.read_dict({})

    with patch.object(cfg_parser.config, "read"):
        result = cfg_parser.parse()

        assert len(result["mowers"]) == 1
        assert result["mowers"][0]["address"] == "00:00:00:00:00:00"
        assert result["mowers"][0]["pin"] == "0000"

        assert result["mqtt"]["broker"] == "127.0.0.1"
        assert result["mqtt"]["topic_base"] == "gardena/automower"
        assert result["system"]["poll_idle"] == 900


def _parse_dict(data):
    """Helper: parses a config given as dict, without touching cfg.ini on disk."""
    cfg_parser = GardenaCfg()
    cfg_parser.config.read_dict(data)
    with patch.object(cfg_parser.config, "read"):
        return cfg_parser.parse()


def test_gardena_cfg_system_defaults_complete():
    """All system settings fall back to their documented defaults."""
    result = _parse_dict({})

    assert result["system"] == {
        "log_level": "INFO",
        "poll_active": 60,
        "poll_idle": 900,
        "poll_error": 30,
        "poll_winter": 3600,
    }
    assert result["mqtt"]["port"] == "1883"


def test_gardena_cfg_custom_system_values():
    """Custom system values (incl. poll_winter) are parsed as integers."""
    result = _parse_dict(
        {
            "system": {
                "poll_active": "45",
                "poll_idle": "600",
                "poll_error": "15",
                "poll_winter": "7200",
            }
        }
    )

    assert result["system"]["poll_active"] == 45
    assert result["system"]["poll_idle"] == 600
    assert result["system"]["poll_error"] == 15
    assert result["system"]["poll_winter"] == 7200


def test_gardena_cfg_log_level_is_uppercased():
    """A lowercase log level is normalized, so getattr(logging, ...) works."""
    result = _parse_dict({"system": {"log_level": "debug"}})

    assert result["system"]["log_level"] == "DEBUG"


def test_gardena_cfg_mower_fallbacks_per_key():
    """Missing keys inside a mower section fall back individually."""
    result = _parse_dict({"mower_front": {"address": "AA:BB:CC:DD:EE:FF"}})

    assert len(result["mowers"]) == 1
    mower = result["mowers"][0]
    assert mower["id"] == "mower_front"
    assert mower["name"] == "mower_front"  # name falls back to the section id
    assert mower["address"] == "AA:BB:CC:DD:EE:FF"
    assert mower["pin"] == "0000"


def test_gardena_cfg_ignores_non_mower_sections():
    """Only sections starting with 'mower' are treated as mowers."""
    result = _parse_dict(
        {
            "mower_1": {"address": "AA:BB:CC:DD:EE:FF"},
            "mqtt": {"broker": "10.0.0.1"},
            "system": {},
            "garden": {"address": "11:22:33:44:55:66"},
        }
    )

    assert [m["id"] for m in result["mowers"]] == ["mower_1"]
    assert result["mqtt"]["broker"] == "10.0.0.1"


def test_gardena_cfg_invalid_integer_raises():
    """Non-numeric poll intervals fail loudly instead of being silently ignored."""
    with pytest.raises(ValueError):
        _parse_dict({"system": {"poll_active": "fast"}})
