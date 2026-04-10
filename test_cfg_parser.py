import pytest
from unittest.mock import patch
from cfg_parser import GardenaCfg


def test_gardena_cfg_parse_success():
    """
    Tests if the GardenaCfg parser correctly extracts all required
    values from a simulated config file.
    """
    # 1. Instantiate the parser
    cfg_parser = GardenaCfg()

    # 2. We populate the internal ConfigParser with "fake" data,
    # as if it had just read a perfect cfg.ini.
    cfg_parser.config.read_dict(
        {
            "mower": {"address": "AA:BB:CC:DD:EE:FF", "pin": "1234"},
            "mqtt": {
                "broker": "192.168.1.100",
                "port": "1883",
                "topic": "mower/status",
                "topic_cmd": "mower/cmd",
            },
        }
    )

    # 3. We mock the actual .read("cfg.ini") function so it doesn't
    # try to look for the real file on the hard drive.
    with patch.object(cfg_parser.config, "read") as mock_read:
        # Execute the method
        result = cfg_parser.parse()

        # Check if the read method was called with the correct filename
        mock_read.assert_called_once_with("cfg.ini")

        # 4. Check if the returned dictionary exactly matches our expectations
        assert result["mower"]["address"] == "AA:BB:CC:DD:EE:FF"
        assert result["mower"]["pin"] == "1234"

        assert result["mqtt"]["broker"] == "192.168.1.100"
        assert result["mqtt"]["port"] == "1883"
        assert result["mqtt"]["topic"] == "mower/status"
        assert result["mqtt"]["topic_cmd"] == "mower/cmd"


def test_gardena_cfg_uses_defaults():
    """
    Tests if the parser applies the correct default fallback values
    when keys are completely missing in the configuration file.
    """
    cfg_parser = GardenaCfg()

    # We simulate a completely empty configuration!
    cfg_parser.config.read_dict({})

    with patch.object(cfg_parser.config, "read"):
        # Execute the parse method
        result = cfg_parser.parse()

        # Now we assert that the fallbacks successfully kicked in!
        assert result["mower"]["address"] == "00:00:00:00:00:00"
        assert result["mower"]["pin"] == "0000"

        assert result["mqtt"]["broker"] == "127.0.0.1"
        assert result["mqtt"]["port"] == "1883"
        assert result["mqtt"]["topic"] == "gardena/automower/status"
        assert result["mqtt"]["topic_cmd"] == "gardena/automower/cmd"

        assert result["system"]["log_level"] == "INFO"
