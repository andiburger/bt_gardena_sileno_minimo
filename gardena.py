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

def publish(client, msg):
    result = client.publish(topic,json.dumps(msg))
    status = result[0]
    if status == 0:
        print(f"Send `{msg}` to topic `{topic}`")
    else:
        print(f"Failed to send message to topic {topic}")

async def connect(m: mower.Mower):
    device = await BleakScanner.find_device_by_address(m.address)

    if device is None:
        print("Unable to connect to device address: " + m.address)
        print(
            "Please make sure the device address is correct, the device is powered on and nearby"
        )
        return

    await m.connect(device)
    print("connected ...")
    manufacturer = await m.get_manufacturer()
    msg.update({'manufacturer':manufacturer})
    print("Mower manufacturer: " + manufacturer)

    model = await m.get_model()
    msg.update({'model':model})
    print("Mower model: " + model)

    charging = await m.is_charging()
    if charging:
        msg.update({'isCharging':1})
        print("Mower is charging")
    else:
        msg.update({'isCharging':0})
        print("Mower is not charging")

    battery_level = await m.battery_level()
    msg.update({'batteryLevel':battery_level})
    print("Battery is: " + str(battery_level) + "%")

    state = await m.mower_state()
    if state is not None:
        msg.update({'state':state.name})
        print("Mower state: " + state.name)

    activity = await m.mower_activity()
    if activity is not None:
        msg.update({'activity':activity.name})
        print("Mower activity: " + activity.name)

    next_start_time = await m.mower_next_start_time()
    if next_start_time:
        msg.update({'nextStartTime':next_start_time.strftime("%Y-%m-%d %H:%M:%S")})
        print("Next start time: " + next_start_time.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        print("No next start time")

    statuses = await m.command("GetAllStatistics")
    for status, value in statuses.items():
        msg.update({str(status):value})
        print(status, value)

    serial_number = await m.command("GetSerialNumber")
    msg.update({'serialNumber':str(serial_number)})
    print("Serial number: " + str(serial_number))

    mower_name = await m.command("GetUserMowerNameAsAsciiString")
    msg.update({'name':mower_name})
    print("Mower name: " + mower_name)
    await m.disconnect()

if __name__ == "__main__":
    client = connect_mqtt()
    client.loop_start()
    while True:
        try:
            m = mower.Mower(1197489078, address,1432)
            asyncio.run(connect(m))
            print('publish')
            publish(client,msg)
        except Exception as e:
            print(e)
            msg.update({"Error":str(e)})
            publish(client,msg)
        time.sleep(60*5) #sleep for 5 minutes and than try to retrieve data again
    client.loop_stop()
