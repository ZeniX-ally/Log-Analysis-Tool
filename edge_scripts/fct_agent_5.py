# -*- coding: utf-8 -*-

import os
import time
import json
import socket
import threading
import traceback
import urllib.request
import urllib.error
from datetime import datetime

os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

SERVER_IP = "172.28.55.66"
SERVER_PORT = "59488"
MACHINE_ID = "PEU_G49_FCT5_01"
MACHINE_IP = "172.28.55.15"
LOCAL_LOG_DIR = r"D:\Results"
POLL_INTERVAL = 5
RETRY_INTERVAL = 10
MAX_RETRY_INTERVAL = 300

LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_registry.txt")

URL_UPLOAD = f"http://{SERVER_IP}:{SERVER_PORT}/api/upload_log"
URL_TELEMETRY = f"http://{SERVER_IP}:{SERVER_PORT}/api/telemetry/push"

global_last_file_time = 0
global_server_reachable = False

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def check_server_connectivity():
    global global_server_reachable
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((SERVER_IP, int(SERVER_PORT)))
        sock.close()
        if result == 0:
            if not global_server_reachable:
                print(f"[{now_text()}] [CONNECT] >>> 服务器 {SERVER_IP}:{SERVER_PORT} 已连通！")
                global_server_reachable = True
            return True
    except Exception:
        pass

    if global_server_reachable:
        print(f"[{now_text()}] [CONNECT] !!! 服务器连接中断，正在重试...")
        global_server_reachable = False
    return False

def load_uploaded_ledger():
    ledger_set = set()
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    ledger_set.add(line.strip())
        except Exception as e:
            print(f"[{now_text()}] [LEDGER] 账本加载异常: {e}")
    return ledger_set

def get_all_xml_files(base_dir):
    xml_files = []
    if not os.path.exists(base_dir):
        return xml_files
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.lower().endswith(".xml"):
                xml_files.append(os.path.join(root, file))
    return xml_files

def upload_file_builtin(url, machine_id, filename, file_content):
    boundary = '----Boundary' + str(time.time()).replace('.', '')
    body = bytearray()
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="machine_id"\r\n\r\n{machine_id}\r\n'.encode('utf-8'))
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/xml\r\n\r\n'.encode('utf-8'))
    body.extend(file_content)
    body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode('utf-8'))
    req = urllib.request.Request(url, data=body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode('utf-8'))

def push_telemetry_builtin(url, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=3) as resp:
        resp.read()

def telemetry_daemon():
    global global_server_reachable
    consecutive_fail = 0

    while True:
        if not check_server_connectivity():
            consecutive_fail += 1
            wait_time = min(RETRY_INTERVAL * consecutive_fail, MAX_RETRY_INTERVAL)
            print(f"[{now_text()}] [HEARTBEAT] 等待服务器上线 ({consecutive_fail}次失败)，{wait_time}秒后重试...", end="\r")
            time.sleep(wait_time)
            continue

        consecutive_fail = 0
        current_state = "RUNNING" if (time.time() - global_last_file_time < 60) else "IDLE"
        telemetry_payload = {
            "machine_id": MACHINE_ID,
            "timestamp": now_text(),
            "machine_state": current_state,
            "host_name": socket.gethostname(),
            "ip": MACHINE_IP,
        }

        try:
            push_telemetry_builtin(URL_TELEMETRY, telemetry_payload)
        except Exception as e:
            global_server_reachable = False
            consecutive_fail = 1

        time.sleep(POLL_INTERVAL)

def print_banner():
    os.system("color 0A")
    print(r"""
    ███████╗ ███████╗ ███╗   ██╗ ██╗ ██╗  ██╗          █████╗  ██╗      ██╗      ██╗   ██╗
    ╚══███╔╝ ██╔════╝ ████╗  ██║ ██║ ╚██╗██╔╝         ██╔══██╗ ██║      ██║      ╚██╗ ██╔╝
      ███╔╝  █████╗   ██╔██╗ ██║ ██║  ╚███╔╝  ███████╗███████║ ██║      ██║       ╚████╔╝
     ███╔╝   ██╔══╝   ██║╚██╗██║ ██║  ██╔██╗  ╚══════╝██╔══██║ ██║      ██║        ╚██╔╝
    ███████╗ ███████╗ ██║ ╚████║ ██║ ██╔╝ ██╗         ██║  ██║ ███████╗ ███████╗    ██║
    ╚══════╝ ╚══════╝ ╚═╝  ╚═══╝ ╚═╝ ╚═╝  ╚═╝         ╚═╝  ╚═╝ ╚══════╝ ╚══════╝    ╚═╝
""")
    print("=" * 80)
    print(f"   FCT5 - 机台ID: {MACHINE_ID}  |  本机IP: {MACHINE_IP}")
    print(f"   服务器: {SERVER_IP}:{SERVER_PORT}")
    print(f"   扫描目录: {LOCAL_LOG_DIR}")
    print(f"   账本文件: {LEDGER_FILE}")
    print("=" * 80)
    print()

def main():
    global global_last_file_time, global_server_reachable

    print_banner()
    print(f"[{now_text()}] [START] FCT5 穿透采集引擎启动中...")
    print(f"[{now_text()}] [CONFIG] 服务器: {URL_UPLOAD}")
    print(f"[{now_text()}] [CONFIG] 扫描目录: {LOCAL_LOG_DIR}")
    print()

    ensure_dir(LOCAL_LOG_DIR)
    uploaded_ledger = load_uploaded_ledger()
    print(f"[{now_text()}] [LEDGER] 已加载 {len(uploaded_ledger)} 条历史传输记录。\n")

    global_last_file_time = 0

    print(f"[{now_text()}] [START] 启动遥测心跳守护线程...")
    heartbeat_thread = threading.Thread(target=telemetry_daemon, daemon=True)
    heartbeat_thread.start()
    print()

    upload_fail_count = 0
    last_status_time = 0

    while True:
        try:
            xml_files = get_all_xml_files(LOCAL_LOG_DIR)
            files_uploaded = 0

            for file_path in xml_files:
                filename = os.path.basename(file_path)
                if filename in uploaded_ledger:
                    continue

                if not check_server_connectivity():
                    current_wait = min((upload_fail_count + 1) * RETRY_INTERVAL, MAX_RETRY_INTERVAL)
                    print(f"\n[{now_text()}] [UPLOAD] 服务器离线，等待重连 ({current_wait}s)...", end="\r")
                    time.sleep(current_wait)
                    upload_fail_count += 1
                    continue

                try:
                    if os.path.getsize(file_path) == 0:
                        print(f"[{now_text()}] [SKIP] 文件生成中(0KB): {filename}", end="\r")
                        continue

                    try:
                        with open(file_path, 'rb') as f:
                            file_content = f.read()
                    except PermissionError:
                        print(f"[{now_text()}] [LOCK] 测控软件正独占: {filename}")
                        continue

                    resp_data = upload_file_builtin(URL_UPLOAD, MACHINE_ID, filename, file_content)

                    if resp_data.get("ok"):
                        print(f"[{now_text()}] [OK] 上传成功: {filename}")
                        uploaded_ledger.add(filename)
                        try:
                            with open(LEDGER_FILE, 'a', encoding='utf-8') as lf:
                                lf.write(filename + '\n')
                        except Exception as e:
                            print(f"[{now_text()}] [WARN] 写入账本失败: {e}")
                        files_uploaded += 1
                        global_last_file_time = time.time()
                        upload_fail_count = 0
                    else:
                        print(f"[{now_text()}] [FAIL] 上传拒绝: {filename} - {resp_data.get('error', '未知错误')}")

                except urllib.error.URLError as e:
                    global_server_reachable = False
                    print(f"\n[{now_text()}] [ERROR] 连接丢失: {str(e.reason)}")
                    upload_fail_count += 1
                except Exception as e:
                    print(f"\n[{now_text()}] [ERROR] 传输异常: {str(e)}")

            if files_uploaded == 0:
                now = time.time()
                if now - last_status_time >= 30:
                    status = "ONLINE" if global_server_reachable else "OFFLINE"
                    print(f"[{now_text()}] [MONITOR] 监听中 | 状态: {status} | 目录: {LOCAL_LOG_DIR}\\*.xml     ", end="\r")
                    last_status_time = now

        except KeyboardInterrupt:
            print(f"\n[{now_text()}] [STOP] 手动停止。")
            break
        except Exception as e:
            print(f"\n[{now_text()}] [FATAL] 严重异常: {str(e)}")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()