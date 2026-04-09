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
        Parses the cfg file (cfg.ini) and returns values as dict.
    """

    def __init__(self):
        """Initializes the GardenaCfg class by creating a ConfigParser instance and preparing it for parsing."""
        self.config = configparser.ConfigParser()
        self.config.sections()
        return

    def parse(self):
        """ "Parses the configuration file (cfg.ini) and extracts the necessary information for the mower and MQTT settings. The extracted values are organized into a nested dictionary structure for easy access.
        Returns:
            dict: A dictionary containing the mower and MQTT configuration settings.
        """
        self.config.read("cfg.ini")
        result = {"mower": {}, "mqtt": {}}
        result["mower"].update(
            {
                "address": self.config["mower"]["address"],
                "pin": self.config["mower"]["pin"],
            }
        )
        result["mqtt"].update(
            {
                "broker": self.config["mqtt"]["broker"],
                "port": self.config["mqtt"]["port"],
                "topic": self.config["mqtt"]["topic"],
                "topic_cmd": self.config["mqtt"]["topic_cmd"],
            }
        )
        return result


# just for test purposes
if __name__ == "__main__":
    """Test block to verify that the GardenaCfg class correctly parses the configuration
    file and returns the expected dictionary structure. This block will execute when the script is run directly,
    allowing for quick validation of the configuration parsing functionality.
    In a production environment, this block can be removed or replaced with proper unit tests.
    """
    gardenaCfg = GardenaCfg()
    res = gardenaCfg.parse()
    print(res)
