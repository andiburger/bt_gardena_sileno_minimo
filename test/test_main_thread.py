import logging
import threading
import time
import random
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
        print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")

    client.subscribe(topic_cmd)
    client.on_message = on_message

def sleep(sleep_time:int):
    for i in range(sleep_time):
        time.sleep(1)
        #TODO check if new command available
    return True

def thread_function(name):
    myclient = connect_mqtt()
    subscribe(myclient)
    myclient.loop_start()
    while 1:
        logging.info("Thread %s: starting", name)
        sleep(5)
        logging.info("Thread %s: finishing", name)

if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO,
                        datefmt="%H:%M:%S")

    logging.info("Main    : before creating thread")
    x = threading.Thread(target=thread_function, args=(1,))
    logging.info("Main    : before running thread")
    x.start()
    logging.info("Main    : wait for the thread to finish")
    x.join()
    logging.info("Main    : all done")