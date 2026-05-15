# -*- coding: utf-8 -*-
"""
NEXUS FCT 测试数据生成器 — 生成模拟 XML 日志供本地测试
======================================================
用法:  python tools/generate_test_data.py [数量]

默认生成 20 份模拟日志到 data/logs/ 目录，
包含 PASS / FAIL / 中断 三种结果，模拟 6 台 FCT 机台数据。
"""

import os
import sys
import random
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")

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

MACHINES = [
    ("PEU_G49_FCT1_01", "FCT1"),
    ("PEU_G49_FCT2_01", "FCT2"),
    ("PEU_G49_FCT3_01", "FCT3"),
    ("PEU_G49_FCT4_01", "FCT4"),
    ("PEU_G49_FCT5_01", "FCT5"),
    ("PEU_G49_FCT6_01", "FCT6"),
]

MODELS = ["G49", "G4.9", "G4.9A", "G4.9B"]
STATIONS = ["FCT"]


def random_sn():
    prefix = random.choice(["G49", "G4.9", "SN"])
    num = random.randint(100000, 999999)
    return f"{prefix}{num}"


def make_test_xml(sn, model, station, machine_id, fail_mode=False):
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
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

    if fail_count > 0:
        overall = "FAIL"
    else:
        overall = "PASS"

    return "\n".join(lines), overall


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    os.makedirs(LOG_DIR, exist_ok=True)
    print(f"[TEST] 生成 {count} 份模拟测试日志到: {LOG_DIR}")
    print()

    generated = 0
    for i in range(count):
        machine_id, short = random.choice(MACHINES)
        model = random.choice(MODELS)
        sn = random_sn()
        station = random.choice(STATIONS)
        fail_mode = random.random() < 0.3

        xml_content, result = make_test_xml(sn, model, station, machine_id, fail_mode)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{i:03d}"
        filename = f"{timestamp}_{sn}_{result}.xml"
        filepath = os.path.join(LOG_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(xml_content)

        result_icon = "PASS" if result == "PASS" else "FAIL"
        print(f"  [{result_icon:4s}] {filename}  ({machine_id})")
        generated += 1

    print()
    print(f"[TEST] 完成！共生成 {generated} 个 XML 文件")
    print(f"[TEST] 启动服务器后访问 http://localhost:59488 查看数据")


if __name__ == "__main__":
    main()