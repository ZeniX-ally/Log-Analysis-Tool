# -*- coding: utf-8 -*-
"""
Mock Machine Agent

当前没有真实机台时，用这个脚本模拟 3 台 FCT 机台每 2 秒推送 telemetry。

启动：
cd /d D:\\Log-Analysis-Tool
python tools/mock_machine_agent.py
"""

import json
import random
import socket
import time
from datetime import datetime
from urllib import request


SERVER_URL = "http://127.0.0.1:5000/api/telemetry/push"
PUSH_INTERVAL_SECONDS = 2


MOCK_MACHINES = [
    {
        "machine_id": "PEU_G49_FCT6_01",
        "station": "FCT6",
        "line": "PEU_G49",
        "model": "E3002781",
        "test_mode": "Online",
    },
    {
        "machine_id": "PEU_G49_FCT6_02",
        "station": "FCT6",
        "line": "PEU_G49",
        "model": "E3002624",
        "test_mode": "Online",
    },
    {
        "machine_id": "PEU_G49_FCT6_03",
        "station": "FCT6",
        "line": "PEU_G49",
        "model": "E3002781",
        "test_mode": "Offline",
    },
]


STEPS = [
    "Idle",
    "Barcode Scan",
    "Power On",
    "DMM Voltage Check",
    "CAN Communication",
    "Relay Driver Test",
    "XCP Variable Read",
    "Result Upload",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(req, timeout=5) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        return json.loads(body) if body else {}


def random_sn(model: str) -> str:
    tail = "".join(random.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(20))
    return f"{model}{tail}"


def build_payload(machine: dict) -> dict:
    model = machine["model"]

    state = random.choices(
        ["IDLE", "RUNNING", "RUNNING", "RUNNING", "FINISHED"],
        weights=[1, 5, 5, 5, 1],
        k=1,
    )[0]

    current_sn = "" if state == "IDLE" else random_sn(model)
    step = "Idle" if state == "IDLE" else random.choice(STEPS)

    dmm_online = random.random() > 0.04
    power_online = random.random() > 0.03
    eload_online = random.random() > 0.05

    can_online = random.random() > 0.03
    lin_online = random.random() > 0.04
    eth_online = random.random() > 0.04
    relay_online = random.random() > 0.03

    vin = round(random.uniform(11.8, 12.3), 3)
    iin = round(random.uniform(0.15, 1.8), 3)
    vout = round(random.uniform(4.9, 5.1), 3)
    iout = round(random.uniform(0.1, 1.2), 3)

    alarms = []
    if not eload_online:
        alarms.append({"code": "ELOAD_OFFLINE", "message": "电子负载离线"})
    if vin < 11.9:
        alarms.append({"code": "VIN_LOW", "message": "VIN 偏低"})

    return {
        "machine_id": machine["machine_id"],
        "station": machine["station"],
        "line": machine["line"],
        "host_name": socket.gethostname(),
        "ip": "127.0.0.1",
        "model": model,
        "test_mode": machine["test_mode"],
        "timestamp": now_text(),
        "machine_state": state,
        "current_sn": current_sn,
        "current_step": step,
        "instruments": {
            "dmm": {
                "online": dmm_online,
                "status": "ONLINE" if dmm_online else "OFFLINE",
                "device": "DMM / 34461A or GDM-9061",
            },
            "power_supply": {
                "online": power_online,
                "status": "ONLINE" if power_online else "OFFLINE",
                "device": "Power Supply",
            },
            "eload": {
                "online": eload_online,
                "status": "ONLINE" if eload_online else "OFFLINE",
                "device": "Electronic Load",
            },
        },
        "measurements": {
            "vin_voltage": vin,
            "vin_current": iin,
            "vout_voltage": vout,
            "vout_current": iout,
            "dmm_voltage": round(random.uniform(0.0, 5.0), 4),
            "temperature": round(random.uniform(25, 45), 1),
        },
        "communication": {
            "can_online": can_online,
            "lin_online": lin_online,
            "ethernet_online": eth_online,
            "relay_board_online": relay_online,
        },
        "alarms": alarms,
    }


def main():
    print("=" * 80)
    print("Mock Machine Agent Started")
    print(f"Server URL: {SERVER_URL}")
    print("Press Ctrl+C to stop")
    print("=" * 80)

    while True:
        for machine in MOCK_MACHINES:
            payload = build_payload(machine)
            try:
                resp = post_json(SERVER_URL, payload)
                print(f"[{now_text()}] pushed {payload['machine_id']} -> {resp.get('ok')}")
            except Exception as e:
                print(f"[{now_text()}] push failed {payload['machine_id']}: {e}")

        time.sleep(PUSH_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()