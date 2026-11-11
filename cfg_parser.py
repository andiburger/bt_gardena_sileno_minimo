"""
Author: __ABu__
"""

import configparser
import logging

from secrets_crypto import decrypt_secret, is_encrypted, load_key

logger = logging.getLogger(__name__)


class GardenaCfg:
    """
    A class to parse a config file for gardena auto mower service.

    ...

    Attributes
    ----------
    config : ConfigParser
        ConfigParser object

    Methods
    -------
    parse():
        Parses the cfg file (cfg.ini) and returns values as dict with safe defaults.
    """

    def __init__(self):
        """Initializes the GardenaCfg class by creating a ConfigParser instance."""
        self.config = configparser.ConfigParser()
        self._key = None

    def _secret(self, section, option, value):
        """
        Returns the decrypted value of an encrypted secret (enc:...).
        Plaintext secrets are accepted for backwards compatibility, but trigger a warning.
        The key is only loaded once, and only if an encrypted value is actually present.
        """
        if not value:
            return value
        if not is_encrypted(value):
            logger.warning(
                f"[{section}] {option} is stored in plaintext in cfg.ini. "
                f"Encrypt it with: python secrets_crypto.py"
            )
            return value
        if self._key is None:
            self._key = load_key()
        return decrypt_secret(value, self._key)

    def parse(self):
        """
        Parses the configuration file (cfg.ini) and extracts the necessary information.
        If keys are missing, safe fallback defaults are provided to prevent crashes.
        Encrypted secrets (mower PINs, MQTT password) are decrypted here.
        raises SecretError: If an encrypted secret cannot be decrypted.
        """
        self.config.read("cfg.ini")
        result = {"mowers": [], "mqtt": {}, "system": {}}

        # --- MOWER SETTINGS (dynamic) ---
        for section in self.config.sections():
            if section.startswith("mower"):
                result["mowers"].append(
                    {
                        "id": section,
                        "name": self.config.get(section, "name", fallback=section),
                        "address": self.config.get(
                            section, "address", fallback="00:00:00:00:00:00"
                        ),
                        "pin": self._secret(
                            section,
                            "pin",
                            self.config.get(section, "pin", fallback="0000"),
                        ),
                    }
                )
        # fallback for no mowers defined at all - we add a default mower to ensure the rest of the system can still function and be tested without a cfg.ini
        if not result["mowers"]:
            result["mowers"].append(
                {
                    "id": "mower_1",
                    "name": "Default Mower",
                    "address": "00:00:00:00:00:00",
                    "pin": "0000",
                }
            )

        # --- MQTT SETTINGS ---
        result["mqtt"].update(
            {
                "broker": self.config.get("mqtt", "broker", fallback="127.0.0.1"),
                "port": self.config.get("mqtt", "port", fallback="1883"),
                # load topic_base with fallback, and then derive topic and topic_cmd from it
                "topic_base": self.config.get(
                    "mqtt", "topic_base", fallback="gardena/automower"
                ),
                # --- Optional broker authentication & encryption ---
                "username": self.config.get("mqtt", "username", fallback=None),
                "password": self._secret(
                    "mqtt",
                    "password",
                    self.config.get("mqtt", "password", fallback=None),
                ),
                "tls": self.config.getboolean("mqtt", "tls", fallback=False),
                "ca_certs": self.config.get("mqtt", "ca_certs", fallback=None),
            }
        )

        # --- SYSTEM SETTINGS (w/ fallbacks) ---
        result["system"].update(
            {
                "log_level": self.config.get(
                    "system", "log_level", fallback="INFO"
                ).upper(),
                "poll_active": int(
                    self.config.get("system", "poll_active", fallback="60")
                ),
                "poll_idle": int(
                    self.config.get("system", "poll_idle", fallback="900")
                ),
                "poll_error": int(
                    self.config.get("system", "poll_error", fallback="30")
                ),
                "poll_winter": int(
                    self.config.get("system", "poll_winter", fallback="3600")
                ),
            }
        )

        return result


# just for test purposes
if __name__ == "__main__":  # pragma: no cover
    gardenaCfg = GardenaCfg()
    res = gardenaCfg.parse()
    # Never print decrypted secrets
    for mower_cfg in res["mowers"]:
        mower_cfg["pin"] = "****"
    if res["mqtt"]["password"]:
        res["mqtt"]["password"] = "****"
    print("Parsed Config with Defaults:")
    print(res)
