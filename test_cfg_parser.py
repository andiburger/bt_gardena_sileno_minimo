import os
import pytest
from cryptography.fernet import Fernet
from unittest.mock import patch
from cfg_parser import GardenaCfg
import secrets_crypto
from secrets_crypto import (
    SecretError,
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
    load_key,
)


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


# --- ENCRYPTION & SECRET HANDLING TESTS ---


def test_encrypt_and_decrypt_secret_roundtrip():
    key = Fernet.generate_key()
    encrypted = encrypt_secret("1234", key)

    assert is_encrypted(encrypted)
    assert encrypted.startswith("enc:")
    assert "1234" not in encrypted
    assert decrypt_secret(encrypted, key) == "1234"


def test_encrypt_empty_secret_raises():
    key = Fernet.generate_key()
    with pytest.raises(ValueError):
        encrypt_secret("", key)


def test_decrypt_plaintext_returns_unchanged():
    assert decrypt_secret("1234") == "1234"
    assert decrypt_secret(None) is None


def test_decrypt_wrong_key_raises_secret_error():
    key1 = Fernet.generate_key()
    key2 = Fernet.generate_key()
    token = encrypt_secret("1234", key1)

    with pytest.raises(SecretError):
        decrypt_secret(token, key2)


def test_decrypt_corrupted_token_raises_secret_error():
    key = Fernet.generate_key()
    with pytest.raises(SecretError):
        decrypt_secret("enc:not-a-valid-fernet-token", key)


def test_decrypt_loads_key_automatically(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv("GARDENA_SECRET_KEY", key.decode())
    token = encrypt_secret("9876", key)

    assert decrypt_secret(token) == "9876"


def test_load_key_creates_and_reloads_file_with_0600(tmp_path, monkeypatch):
    monkeypatch.delenv("GARDENA_SECRET_KEY", raising=False)
    key_file = tmp_path / ".gardena.key"
    monkeypatch.setenv("GARDENA_KEY_FILE", str(key_file))

    created_key = load_key(create=True)
    assert key_file.exists()
    assert (key_file.stat().st_mode & 0o777) == 0o600
    assert load_key(create=False) == created_key


def test_load_key_warns_on_permissive_file_mode(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("GARDENA_SECRET_KEY", raising=False)
    key_file = tmp_path / ".gardena.key"
    key_file.write_bytes(Fernet.generate_key())
    os.chmod(key_file, 0o644)
    monkeypatch.setenv("GARDENA_KEY_FILE", str(key_file))

    load_key(create=False)
    assert "readable by other users" in caplog.text


def test_load_key_missing_raises_secret_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GARDENA_SECRET_KEY", raising=False)
    monkeypatch.setenv("GARDENA_KEY_FILE", str(tmp_path / "missing.key"))

    with pytest.raises(SecretError):
        load_key(create=False)


def test_gardena_cfg_decrypts_encrypted_pins_and_mqtt_password(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv("GARDENA_SECRET_KEY", key.decode())
    enc_pin_1 = encrypt_secret("1234", key)
    enc_pin_2 = encrypt_secret("5678", key)
    enc_pw = encrypt_secret("my-mqtt-pass", key)

    result = _parse_dict(
        {
            "mower_1": {
                "name": "Front",
                "address": "AA:BB:CC:DD:EE:FF",
                "pin": enc_pin_1,
            },
            "mower_2": {
                "name": "Back",
                "address": "11:22:33:44:55:66",
                "pin": enc_pin_2,
            },
            "mqtt": {
                "broker": "192.168.1.100",
                "username": "gardena_user",
                "password": enc_pw,
                "tls": "true",
                "ca_certs": "/etc/ssl/cert.pem",
            },
        }
    )

    assert result["mowers"][0]["pin"] == "1234"
    assert result["mowers"][1]["pin"] == "5678"
    assert result["mqtt"]["username"] == "gardena_user"
    assert result["mqtt"]["password"] == "my-mqtt-pass"
    assert result["mqtt"]["tls"] is True
    assert result["mqtt"]["ca_certs"] == "/etc/ssl/cert.pem"


def test_secrets_crypto_cli_main(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GARDENA_SECRET_KEY", raising=False)
    key_file = tmp_path / ".gardena.key"
    monkeypatch.setenv("GARDENA_KEY_FILE", str(key_file))
    monkeypatch.setattr("secrets_crypto.getpass.getpass", lambda _: "4321")

    rc = secrets_crypto.main()
    captured = capsys.readouterr()

    assert rc == 0
    token = captured.out.strip()
    assert token.startswith("enc:")
    assert decrypt_secret(token) == "4321"


def test_secrets_crypto_cli_empty_input_aborts(monkeypatch):
    monkeypatch.setattr("secrets_crypto.getpass.getpass", lambda _: "")
    assert secrets_crypto.main() == 1


def test_gardena_cfg_warns_on_permissive_cfg_ini_mode(monkeypatch, caplog):
    monkeypatch.setattr("cfg_parser.os.path.exists", lambda p: p == "cfg.ini")
    fake_stat = type("Stat", (), {"st_mode": 0o100644})()
    monkeypatch.setattr("cfg_parser.os.stat", lambda p: fake_stat)

    _parse_dict({})

    assert "cfg.ini is readable by other users" in caplog.text
