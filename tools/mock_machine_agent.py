# -*- coding: utf-8 -*-
"""
Mock Machine Agent (Ironclad Edition - 防闪退装甲版)

当前没有真实机台时，用这个脚本模拟 3 台 FCT 机台每 2 秒推送 telemetry。
已加入：代理旁路直连、全局异常捕获、防闪退挂起。
"""

import json
import random
import socket
import time
import traceback
from datetime import datetime
from urllib import request, error

SERVER_URL = "http://127.0.0.1:5000/api/telemetry/push"
PUSH_INTERVAL_SECONDS = 2

MOCK_MACHINES = [
    {"machine_id": "PEU_G49_FCT6_01", "station": "FCT6", "line": "PEU_G49", "model": "E3002781", "test_mode": "Online"},
    {"machine_id": "PEU_G49_FCT6_02", "station": "FCT6", "line": "PEU_G49", "model": "E3002624", "test_mode": "Online"},
    {"machine_id": "PEU_G49_FCT6_03", "station": "FCT6", "line": "PEU_G49", "model": "E3002781", "test_mode": "Offline"},
]

STEPS = [
    "Idle", "Barcode Scan", "Power On", "DMM Voltage Check",
    "CAN Communication", "Relay Driver Test", "XCP Variable Read", "Result Upload",
]

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    
    # 核心护盾 1：强制绕过 Windows 系统代理，防止 127.0.0.1 被劫持导致连接拒绝
    proxy_handler = request.ProxyHandler({})
    opener = request.build_opener(proxy_handler)
    
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with opener.open(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            # 核心护盾 2：安全解析 JSON，防止后端返回 500 HTML 页面时脚本崩溃
            try:
                return json.loads(body) if body else {}
            except json.JSONDecodeError:
                return {"ok": False, "error": f"Server returned non-JSON response: {body[:50]}..."}
    except error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except error.URLError as e:
        return {"ok": False, "error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"Unknown Error: {str(e)}"}

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
            "dmm": {"online": dmm_online, "status": "ONLINE" if dmm_online else "OFFLINE", "device": "DMM / 34461A or GDM-9061"},
            "power_supply": {"online": power_online, "status": "ONLINE" if power_online else "OFFLINE", "device": "Power Supply"},
            "eload": {"online": eload_online, "status": "ONLINE" if eload_online else "OFFLINE", "device": "Electronic Load"},
        },
        "measurements": {
            "vin_voltage": vin, "vin_current": iin, "vout_voltage": vout, "vout_current": iout,
            "dmm_voltage": round(random.uniform(0.0, 5.0), 4), "temperature": round(random.uniform(25, 45), 1),
        },
        "communication": {
            "can_online": can_online, "lin_online": lin_online, "ethernet_online": eth_online, "relay_board_online": relay_online,
        },
        "alarms": alarms,
    }

def main():
    print("=" * 80)
    print("🚀 Mock Machine Agent (Ironclad Edition) Started")
    print(f"📡 Target Server URL: {SERVER_URL}")
    print("🛑 Press Ctrl+C to stop")
    print("=" * 80)

    consecutive_errors = 0

    while True:
        try:
            for machine in MOCK_MACHINES:
                payload = build_payload(machine)
                resp = post_json(SERVER_URL, payload)
                
                if resp.get("ok"):
                    print(f"[{now_text()}] ✅ Pushed {payload['machine_id']} -> SUCCESS")
                    consecutive_errors = 0
                else:
                    print(f"[{now_text()}] ❌ Push failed {payload['machine_id']} -> {resp.get('error', 'Unknown Error')}")
                    consecutive_errors += 1
            
            # 如果连续失败太多次，稍微放缓请求节奏，防止疯狂刷屏
            sleep_time = PUSH_INTERVAL_SECONDS if consecutive_errors < 10 else 5
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n🛑 Agent manually stopped by user.")
            break
        except Exception as e:
            # 核心护盾 3：捕获循环内的一切未预期异常，防止脚本崩溃
            print(f"\n[{now_text()}] 💥 CRITICAL AGENT ERROR: {str(e)}")
            traceback.print_exc()
            print("Restarting loop in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL CRASH: {str(e)}")
        traceback.print_exc()
        # 核心护盾 4：防闪退。即使发生了最严重的崩溃，窗口也会停住让你看清报错
        input("\nPress ENTER to exit...")