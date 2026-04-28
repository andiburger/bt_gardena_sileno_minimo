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
                        "pin": self.config.get(section, "pin", fallback="0000"),
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
            }
        )

        return result


# just for test purposes
if __name__ == "__main__":
    gardenaCfg = GardenaCfg()
    res = gardenaCfg.parse()
    print("Parsed Config with Defaults:")
    print(res)
