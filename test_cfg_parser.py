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
