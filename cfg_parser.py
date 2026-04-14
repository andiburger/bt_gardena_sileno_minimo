"""
Author: __ABu__
"""

import configparser


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
        return

    def parse(self):
        """
        Parses the configuration file (cfg.ini) and extracts the necessary information.
        If keys are missing, safe fallback defaults are provided to prevent crashes.
        """
        # Wir lesen die Datei (falls sie nicht existiert, bleibt config leer, aber das Skript stürzt dank der Fallbacks nicht ab!)
        self.config.read("cfg.ini")

        result = {"mower": {}, "mqtt": {}, "system": {}}

        # --- MOWER SETTINGS (mit Fallbacks) ---
        result["mower"].update(
            {
                # Fallback auf Dummy-Mac, falls vergessen
                "address": self.config.get(
                    "mower", "address", fallback="00:00:00:00:00:00"
                ),
                # Standard Gardena PIN
                "pin": self.config.get("mower", "pin", fallback="0000"),
            }
        )

        # --- MQTT SETTINGS (mit Fallbacks) ---
        result["mqtt"].update(
            {
                # Fallback auf localhost, falls der Broker auf dem gleichen Pi läuft
                "broker": self.config.get("mqtt", "broker", fallback="127.0.0.1"),
                # Standard MQTT Port
                "port": self.config.get("mqtt", "port", fallback="1883"),
                # Standard Topics, damit Home Assistant sie auf jeden Fall findet
                "topic": self.config.get(
                    "mqtt", "topic", fallback="gardena/automower/status"
                ),
                "topic_cmd": self.config.get(
                    "mqtt", "topic_cmd", fallback="gardena/automower/cmd"
                ),
            }
        )

        # --- SYSTEM SETTINGS (mit Fallbacks) ---
        result["system"].update(
            {
                "log_level": self.config.get(
                    "system", "log_level", fallback="INFO"
                ).upper(),
                # NEU: Konfigurierbare Polling-Zeiten (in Sekunden)
                "poll_active": int(
                    self.config.get("system", "poll_active", fallback="60")
                ),
                "poll_idle": int(
                    self.config.get("system", "poll_idle", fallback="900")
                ),
                "poll_error": int(
                    self.config.get("system", "poll_error", fallback="30")
                ),
            }
        )

        return result


# just for test purposes
if __name__ == "__main__":
    gardenaCfg = GardenaCfg()
    res = gardenaCfg.parse()
    print("Parsed Config with Defaults:")
    print(res)
