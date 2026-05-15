# -*- coding: utf-8 -*-
"""
NEXUS FCT 本地模拟代理 — 模拟边缘机上传 + 心跳
==============================================
用法:  python tools/simulate_agent.py [机台号]

机台号: 1~6 (默认 1)
先启动服务器，再开此脚本模拟 FCT 机台上传日志和心跳。
每 5 秒生成一份新 XML 并上传到服务器，文件会出现在 data/logs/ 中。
"""

import os
import sys
import time
import json
import random
import urllib.request
import urllib.error

SERVER_URL = "http://localhost:59488"
MACHINE_IDS = [
    "PEU_G49_FCT1_01", "PEU_G49_FCT2_01", "PEU_G49_FCT3_01",
    "PEU_G49_FCT4_01", "PEU_G49_FCT5_01", "PEU_G49_FCT6_01",
]
MACHINE_IPS = [
    "172.28.55.11", "172.28.55.12", "172.28.55.13",
    "172.28.55.14", "172.28.55.15", "172.28.55.16",
]

TEST_ITEMS_POOL = [
    ("Voltage_1", "V", 3.3, 3.0, 3.6),
    ("Voltage_2", "V", 5.0, 4.75, 5.25),
    ("Current_1", "mA", 150, 100, 200),
    ("Current_2", "mA", 50, 30, 70),
    ("Resistance_1", "ohm", 10.5, 9.0, 12.0),
    ("Resistance_2", "ohm", 100, 95, 105),
    ("Frequency_1", "Hz", 1000, 990, 1010),
    ("Frequency_2", "Hz", 50, 49.5, 50.5),
    ("Temperature_1", "degC", 25.0, 20.0, 30.0),
    ("Temperature_2", "degC", 45.0, 40.0, 50.0),
    ("Pressure_1", "kPa", 101.3, 100.0, 102.5),
    ("Pressure_2", "kPa", 200, 190, 210),
    ("Signal_Strength", "dBm", -65, -80, -50),
    ("Impedance", "ohm", 50, 48, 52),
    ("Capacitance", "uF", 100, 95, 105),
]


def random_sn():
    prefix = random.choice(["G49", "G4.9", "SN"])
    num = random.randint(100000, 999999)
    return f"{prefix}{num}"


def make_test_xml(sn, machine_id, fail_mode=False):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append('<?xml version="1.0" encoding="utf-8"?>')
    lines.append(f'<TestReport MachineID="{machine_id}">')
    lines.append(f'  <BATCH TIMESTAMP="{timestamp}" />')
    lines.append(f'  <PANEL STATUS="PASS" TIMESTAMP="{timestamp}" />')
    lines.append(f'  <DUT ID="{sn}" STATUS="PASS" TIMESTAMP="{timestamp}" />')
    lines.append(f'  <GROUP NAME="Electrical_Test">')

    fail_count = 0
    for name, unit, nominal, lo, hi in TEST_ITEMS_POOL:
        if fail_mode and random.random() < 0.15:
            value = round(random.uniform(lo - 2, lo - 0.1), 3)
            status = "FAIL"
            fail_count += 1
        elif fail_mode and random.random() < 0.05:
            value = 0
            status = "ERROR"
        else:
            value = round(random.uniform(lo + 0.1, hi - 0.1), 3)
            status = "PASS"

        lines.append(f'    <Test NAME="{name}" VALUE="{value}" UNIT="{unit}" '
                     f'LOLIM="{lo}" HILIM="{hi}" STATUS="{status}" />')

    lines.append(f'  </GROUP>')
    lines.append(f'</TestReport>')

    overall = "FAIL" if fail_count > 0 else "PASS"
    return "\n".join(lines), overall


def push_telemetry(machine_id, ip):
    payload = {
        "machine_id": machine_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine_state": random.choice(["RUNNING", "IDLE", "RUNNING", "RUNNING"]),
        "host_name": f"FCT{machine_id[-2]}",
        "ip": ip,
        "current_sn": f"SN{random.randint(100000,999999)}",
        "current_step": random.choice(["Electrical_Test", "Functional_Test", "Final_Check"]),
        "model": random.choice(["G49", "G4.9A", "G4.9B"]),
        "test_mode": "Online",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{SERVER_URL}/api/telemetry/push", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=3) as resp:
        resp.read()


def upload_content(machine_id, filename, content_bytes):
    boundary = f"----Boundary{time.time()}".replace(".", "")
    body = bytearray()
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="machine_id"\r\n\r\n{machine_id}\r\n'.encode())
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/xml\r\n\r\n'.encode())
    body.extend(content_bytes)
    body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())

    req = urllib.request.Request(f"{SERVER_URL}/api/upload_log", data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    idx = int(sys.argv[1]) - 1 if len(sys.argv) > 1 else 0
    idx = max(0, min(idx, 5))
    machine_id = MACHINE_IDS[idx]
    ip = MACHINE_IPS[idx]

    print(f"[SIM] Simulating machine: {machine_id} ({ip})")
    print(f"[SIM] Server: {SERVER_URL}")
    print(f"[SIM] Generating and uploading 1 XML every 5 seconds...")
    print(f"[SIM] Files will appear in: data/logs/")
    print(f"[SIM] Press Ctrl+C to stop")
    print()

    upload_count = 0
    heartbeat_count = 0

    while True:
        try:
            push_telemetry(machine_id, ip)
            heartbeat_count += 1
            if heartbeat_count % 3 == 0:
                print(f"[SIM] [{time.strftime('%H:%M:%S')}] Heartbeat OK ({heartbeat_count})")

            if heartbeat_count % 3 == 0:
                sn = random_sn()
                fail_mode = random.random() < 0.3
                xml_content, result = make_test_xml(sn, machine_id, fail_mode)
                ts = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{ts}_{sn}_{result}.xml"
                content_bytes = xml_content.encode("utf-8")

                try:
                    resp = upload_content(machine_id, filename, content_bytes)
                    if resp.get("ok"):
                        upload_count += 1
                        print(f"[SIM] [{time.strftime('%H:%M:%S')}] [UPLOAD] {filename}  ({result})  uploaded to server")
                    else:
                        print(f"[SIM] [{time.strftime('%H:%M:%S')}] [FAIL] {filename}  rejected: {resp.get('error')}")
                except Exception as e:
                    print(f"[SIM] [{time.strftime('%H:%M:%S')}] [ERROR] {filename}  upload failed: {e}")

            time.sleep(2)

        except KeyboardInterrupt:
            print(f"\n[SIM] Stopped. Total uploaded: {upload_count}")
            break
        except Exception as e:
            print(f"[SIM] Connection error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()