from automower_ble import protocol, mower
from bleak import BleakScanner
import asyncio
import random
import time
import json
from asyncio_paho import AsyncioPahoClient
from GardenaCfg import GardenaCfg

global broker
global address
global port 
global topic
global topic_cmd
global sleep_interval
error_counter = 0
# Generate a Client ID with the publish prefix.
client_id = f'publish-{random.randint(0, 1000)}'
# msg to be published on mqtt
msg = {}

async def connect_mqtt():
    """def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)"""
    client = AsyncioPahoClient()
    #client = mqtt_client.Client(client_id)

    # client.username_pw_set(username, password)
    #client.on_connect = on_connect
    await client.asyncio_connect(broker, port)
    #client.connect(broker, port)
    return client

async def publish(client: mqtt_client, msg):
    await result = client.asyncio_publish(topic,json.dumps(msg, indent = 4))
    status = result[0]
    if status == 0:
        print(f"Send `{msg}` to topic `{topic}`")
    else:
        print(f"Failed to send message to topic {topic}")

def sleep(sleep_time:int):
    for i in range(sleep_time):
        time.sleep(1)
        #TODO check if new command available
    return True

async def exec_cmd(client, userdata, msg):
    userdata = m
    cmd = msg.payload.decode()["cmd"]
    if (cmd == 'start') or (cmd == "start_mowing"):
        # actually start mowing for 30 minutes
        print("--------------")
        print("start setting mode to manual")
        await m.set_mode_of_operation(ModeOfOperation.MANUAL)
        print("Mode of operation set to manual")
        print("--------------")

        print("Overriding mow to 30 mins")
        await m.set_mower_override_duration_in_seconds(
            30 * 60
        )  # 30 minutes override mow
        print("override mow finished ")
        print("--------------")

        start_trigger = await m.start_trigger_request()
        print(f"Start trigger response : {start_trigger}")

    elif (cmd == 'stop') or (cmd == 'park'):
        print("Must stop mowing. Send Park command to mower")
        await m.set_mode_of_operation(ModeOfOperation.MANUAL)
        print(
            "Finished setting mode of operation to manual. Sending park command"
        )
        await m.mower_park()
        print("Finished sending park command")
        start_trigger = await m.start_trigger_request()
        print(f"Start trigger response : {start_trigger}")

    elif (cmd == 'pause'):
        print("Must stop mowing. Send pause command to mower")
        await m.set_mode_of_operation(ModeOfOperation.MANUAL)
        print(
            "Finished setting mode of operation to manual. Sending pause command"
        )
        await m.mower_pause()
        print("Finished sending pause command")
        start_trigger = await m.start_trigger_request()
        print(f"Start trigger response : {start_trigger}")

    elif (cmd == 'resume'):
        print("Must stop mowing. Send resume command to mower")
        await m.set_mode_of_operation(ModeOfOperation.MANUAL)
        print(
            "Finished setting mode of operation to manual. Sending resume command"
        )
        await m.mower_resume()
        print("Finished sending resume command")
        start_trigger = await m.start_trigger_request()
        print(f"Start trigger response : {start_trigger}")

async def subscribe(client: mqtt_client):
    await client.asyncio_subscribe(topic_cmd)
    client.asyncio_listeners.add_on_message(exec_cmd)

async def connect(m: mower.Mower, client: mqtt_client):
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
        client.user_data_set(m)
        await subscribe(client)
        
        model = await m.get_model()
        print(f"Model : {model} ")
        msg.update({"Model" : str(model)})

        manufacturer = await m.get_manufacturer()
        print(f"Manufacturer {manufacturer}")
        msg.update({"Manufacturer":manufacturer})
        
        while True:
            print("Start sending keep Alive")
            keepalive_response = await m.send_keepalive()
            if not keepalive_response:
                logger.error(f"Error sending keepalive request {keepalive_response}")

            enterOperatorPinRequestResult = await m.send_operator_pin_request(m.pin)
            print(
                f"Enter Operator Pin Request Result {enterOperatorPinRequestResult}"
            )

            success = await m.get_startupsequence_required_request()
            print(f"Startupsequence is required response {success}")

            operator_is_logged_in = await m.is_operator_loggedin()
            print(f"Operator is logged in {operator_is_logged_in}")

            activity = await m.mower_activity()
            print(f"Mower activity : {activity}")
            msg.update({"MowerActivity" : str(activity)})

            mode = await m.get_mode_of_operation()
            print(f"Mower mode : {mode}")
            msg.update({"MowerMode": str(mode)})

            serial_number = await m.get_serial_number()
            print(f"Serial number : {serial_number}")
            msg.update({"SerialNumber": serial_number})

            statuses = await m.get_parameter("getStatuses")
            for status, value in statuses.items():
                print(status, value)
                msg.update({str(status):value})

            is_charging = await m.is_charging()
            print(f"Is charging {is_charging}")
            msg.update({"IsCharging":is_charging})

            print("Start sending keep Alive")
            keepalive_response = await m.send_keepalive()
            if not keepalive_response:
                logger.error(f"Error sending keepalive request {keepalive_response}")

            battery_level = await m.battery_level()
            print(f"Battery level {battery_level}")
            msg.update({"BatteryLevel":battery_level})

            restriction_reason = await m.get_restriction_reason()
            print(f"Restriction Reason : {restriction_reason}")
            msg.update({"RestrictionReason" : str(restriction_reason)})

            next_start_time = await m.mower_next_start_time()
            if next_start_time:
                print(
                    "Next start time: " + next_start_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                msg.update({"NextStartTime":  next_start_time.strftime("%Y-%m-%d %H:%M:%S")})
            else:
                print("No next start time")

            number_of_tasks = await m.get_number_of_tasks()
            print(f"number of tasks : {number_of_tasks}")
            msg.update({"NoOfTasks" : number_of_tasks})

            keepalive_response = await m.send_keepalive()

            mower_state = await m.mower_state()
            print(f"Mower state response {mower_state}")
            msg.update({"MowerStateResponse":str(mower_state)})

            mower_activity = await m.mower_activity()
            print(f"MowerActivity : {mower_activity}")

            get_mode_response = await m.get_mode_of_operation()
            print(f"Mode : {get_mode_response}")
            keepalive_response = await m.send_keepalive()
            print('publish')
            await publish(client,msg)
            time.sleep(sleep_interval*60) 
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
    sleep_interval = int(result["mower"]["sleep_interval"])
    client = connect_mqtt()
    client.loop_start()
    try:
        m = mower.Mower(random.randint(100000000, 999999999), address,int(pin))
        asyncio.run(connect(m,client))
    except Exception as e:
        error_counter += 1
        print(e)
        msg.update({"Error":str(e)})
        msg.update({"Error Counter":error_counter})
        publish(client,msg)
    client.loop_stop()
