"""
Author: Andi
"""

import configparser


class GardenaCfg():
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
        self.config = configparser.ConfigParser()
        self.config.sections()
        return

    def parse(self):
        self.config.read('cfg.ini')
        result = {"mower":{},"mqtt":{}}
        result["mower"].update({"address":self.config["mower"]["address"], "pin":self.config["mower"]["pin"], "sleep_interval":self.config["mower"]["sleep_interval"]})
        result["mqtt"].update({"broker":self.config["mqtt"]["broker"], "port":self.config["mqtt"]["port"], "topic":self.config["mqtt"]["topic"], "topic_cmd":self.config["mqtt"]["topic_cmd"]})
        return result


# just for test purposes
if __name__ == "__main__":
    gardenaCfg = GardenaCfg()
    res = gardenaCfg.parse()
    print(res)


    
