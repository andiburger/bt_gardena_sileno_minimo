```json
[
    {
        "id": "group_gardena",
        "type": "group",
        "name": "Gardena Minimo MQTT Bridge",
        "style": {
            "stroke": "#009900",
            "fill": "#e3f2fd",
            "fill-opacity": "0.5"
        },
        "nodes": [
            "mqtt_in_status",
            "json_parser",
            "debug_all",
            "mqtt_out_cmd",
            "btn_start",
            "btn_park",
            "btn_pause",
            "switch_data",
            "debug_battery",
            "debug_activity"
        ],
        "x": 114,
        "y": 79,
        "w": 652,
        "h": 342
    },
    {
        "id": "mqtt_in_status",
        "type": "mqtt in",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "Receive Mower Status",
        "topic": "gardena/automower/status",
        "qos": "0",
        "datatype": "auto-detect",
        "broker": "",
        "nl": false,
        "rap": true,
        "rh": 0,
        "inputs": 0,
        "x": 220,
        "y": 120,
        "wires": [
            [
                "json_parser"
            ]
        ]
    },
    {
        "id": "json_parser",
        "type": "json",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "Parse JSON",
        "property": "payload",
        "action": "obj",
        "pretty": false,
        "x": 430,
        "y": 120,
        "wires": [
            [
                "debug_all",
                "switch_data"
            ]
        ]
    },
    {
        "id": "debug_all",
        "type": "debug",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "Show Complete JSON",
        "active": false,
        "tosidebar": true,
        "console": false,
        "tostatus": false,
        "complete": "payload",
        "targetType": "msg",
        "statusVal": "",
        "statusType": "auto",
        "x": 620,
        "y": 80,
        "wires": []
    },
    {
        "id": "mqtt_out_cmd",
        "type": "mqtt out",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "Send Command",
        "topic": "gardena/automower/cmd",
        "qos": "0",
        "retain": "false",
        "respTopic": "",
        "contentType": "",
        "userProps": "",
        "correl": "",
        "expiry": "",
        "broker": "",
        "x": 590,
        "y": 300,
        "wires": []
    },
    {
        "id": "btn_start",
        "type": "inject",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "START",
        "props": [
            {
                "p": "payload"
            }
        ],
        "repeat": "",
        "crontab": "",
        "once": false,
        "onceDelay": 0.1,
        "topic": "",
        "payload": "START",
        "payloadType": "str",
        "x": 190,
        "y": 260,
        "wires": [
            [
                "mqtt_out_cmd"
            ]
        ]
    },
    {
        "id": "btn_park",
        "type": "inject",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "PARK",
        "props": [
            {
                "p": "payload"
            }
        ],
        "repeat": "",
        "crontab": "",
        "once": false,
        "onceDelay": 0.1,
        "topic": "",
        "payload": "PARK",
        "payloadType": "str",
        "x": 190,
        "y": 300,
        "wires": [
            [
                "mqtt_out_cmd"
            ]
        ]
    },
    {
        "id": "btn_pause",
        "type": "inject",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "PAUSE",
        "props": [
            {
                "p": "payload"
            }
        ],
        "repeat": "",
        "crontab": "",
        "once": false,
        "onceDelay": 0.1,
        "topic": "",
        "payload": "PAUSE",
        "payloadType": "str",
        "x": 190,
        "y": 340,
        "wires": [
            [
                "mqtt_out_cmd"
            ]
        ]
    },
    {
        "id": "switch_data",
        "type": "change",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "Extract Values",
        "rules": [
            {
                "t": "set",
                "p": "battery",
                "pt": "msg",
                "to": "payload.BatteryLevel",
                "tot": "msg"
            },
            {
                "t": "set",
                "p": "activity",
                "pt": "msg",
                "to": "payload.MowerActivity",
                "tot": "msg"
            }
        ],
        "action": "",
        "property": "",
        "from": "",
        "to": "",
        "reg": false,
        "x": 410,
        "y": 160,
        "wires": [
            [
                "debug_battery",
                "debug_activity"
            ]
        ]
    },
    {
        "id": "debug_battery",
        "type": "debug",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "Show Battery",
        "active": true,
        "tosidebar": true,
        "console": false,
        "tostatus": false,
        "complete": "battery",
        "targetType": "msg",
        "statusVal": "",
        "statusType": "auto",
        "x": 610,
        "y": 140,
        "wires": []
    },
    {
        "id": "debug_activity",
        "type": "debug",
        "z": "your_flow_id",
        "g": "group_gardena",
        "name": "Show Activity",
        "active": true,
        "tosidebar": true,
        "console": false,
        "tostatus": false,
        "complete": "activity",
        "targetType": "msg",
        "statusVal": "",
        "statusType": "auto",
        "x": 620,
        "y": 180,
        "wires": []
    }
]```