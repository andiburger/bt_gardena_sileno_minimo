from automower_ble import protocol, mower
from bleak import BleakScanner
import asyncio
import random
import time
import json
from paho.mqtt import client as mqtt_client
from cfg_parser import GardenaCfg

broker = None
address = None
port = None
topic = None
topic_cmd = None
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
    client = mqtt_client.Client(client_id=client_id)

    # client.username_pw_set(username, password)
    client.on_connect = on_connect
    if broker is None or port is None:
        raise ValueError("MQTT broker address and port must be set before connecting.")
    client.connect(broker, port)
    return client

def publish(client: mqtt_client.Client, msg):
    if topic is None:
        raise ValueError("MQTT topic must be set before publishing.")
    result = client.publish(topic, json.dumps(msg, indent=4))
    status = result[0]
    if status == 0:
        print(f"Send `{msg}` to topic `{topic}`")
    else:
        print(f"Failed to send message to topic {topic}")

async def connect(m: mower.Mower, client: mqtt_client.Client):
    try:
        print("Start test mower")
        device = await BleakScanner.find_device_by_address(m.address)
        if device is None:
            print("Unable to connect to device address: " + m.address)
            print(
                "Please make sure the device address is correct, the device is powered on and nearby"
            )
            return
        print(f"Device found. Start connecting to device {m.address}")
        await m.connect(device)
        print(f"Connected to device with address {m.address}")
        print(f"Mower : {m}")

        model = await m.get_model()
        print(f"Model : {model} ")
        msg.update({"Model" : str(model)})

        manufacturer = await m.get_manufacturer()
        print(f"Manufacturer {manufacturer}")
        msg.update({"Manufacturer":manufacturer})
        while True:
            print("Start sending keep Alive")
            
            activity = await m.mower_activity()
            print(f"Mower activity : {activity}")
            msg.update({"MowerActivity" : str(activity)})

            serial_number = await m.command("GetSerialNumber")
            print(f"Serial number : {serial_number}")
            msg.update({"SerialNumber": serial_number})
        
            statuses = await m.command("GetAllStatistics")
            if isinstance(statuses, dict):
                for status, value in statuses.items():
                    print(status, value)
                    msg.update({str(status): value})
            else:
                print(f"Unexpected type for statuses: {type(statuses)} - {statuses}")

            is_charging = await m.is_charging()
            print(f"Is charging {is_charging}")
            msg.update({"IsCharging":is_charging})


            battery_level = await m.battery_level()
            print(f"Battery level {battery_level}")
            msg.update({"BatteryLevel":battery_level})


            next_start_time = await m.mower_next_start_time()
            if next_start_time:
                print(
                    "Next start time: " + next_start_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                msg.update({"Next start time":  next_start_time.strftime("%Y-%m-%d %H:%M:%S")})
            else:
                print("No next start time")

            mower_state = await m.mower_state()
            print(f"Mower state response {mower_state}")
            msg.update({"MowerStateResponse":str(mower_state)})

            mower_activity = await m.mower_activity()
            print(f"MowerActivity : {mower_activity}")

            print('publish')
            publish(client,msg)
            time.sleep(60) #sleep for 1 minute and than try to retrieve data again
    except Exception as e:
        print("There was an issue communicating with the device")
        raise e

if __name__ == "__main__":
    cfg_parser = GardenaCfg()
    result = cfg_parser.parse()
    broker = result["mqtt"]["broker"]
    port = int(result["mqtt"]["port"])
    topic = result["mqtt"]["topic"]
    topic_cmd = result["mqtt"]["topic_cmd"]
    address = result["mower"]["address"]
    pin = result["mower"]["pin"]

    client = connect_mqtt()
    client.loop_start()
    try:
        m = mower.Mower(random.randint(100000000, 999999999), address, pin)
        asyncio.run(connect(m,client))
    except Exception as e:
        error_counter += 1
        print(e)
        msg.update({"Error":str(e)})
        msg.update({"Error Counter":error_counter})
        publish(client,msg)
    client.loop_stop()
