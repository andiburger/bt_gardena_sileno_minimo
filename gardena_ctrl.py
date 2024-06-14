from automower_ble import protocol, mower
from bleak import BleakScanner
import asyncio
import random
import time
import json
from paho.mqtt import client as mqtt_client

broker = '192.168.178.160'
address = "84:72:93:94:B6:4C"
port = 1883
topic = "gardena/automower"
topic_cmd = "gardena/automower/cmd"
error_counter = 0
# Generate a Client ID with the publish prefix.
client_id = f'publish-{random.randint(0, 1000)}'
# msg to be published on mqtt
msg = {}

def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)
    client = mqtt_client.Client(client_id)

    # client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        cmd_str = msg.payload.decode()
        m = mower.Mower(random.randint(100000000, 999999999), address,1432)
        asyncio.run(execute_cmd(cmd_str,m))
        
        print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")

    client.subscribe(topic_cmd)
    client.on_message = on_message

async def execute_cmd(m, cmd_str):
    device = await BleakScanner.find_device_by_address(m.address)

    if device is None:
        print("Unable to connect to device address: " + m.address)
        print(
            "Please make sure the device address is correct, the device is powered on and nearby"
        )
        return

    await m.connect(device)
    match cmd_str:
        case "park":
            print("command=park")
            cmd_result = await m.mower_park()
        case "pause":
            print("command=pause")
            cmd_result = await m.mower_pause()
        case "resume":
            print("command=resume")
            cmd_result = await m.mower_resume()
        case "override":
            print("command=override")
            cmd_result = await m.mower_override()
        case _:
            print("command=??? (Unknown command: " + args.command + ")")
    print("command result = " + str(cmd_result))
    await m.disconnect()
