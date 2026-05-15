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
MACHINE_ID = "PEU_G49_FCT4_01"
MACHINE_IP = "172.28.55.14"
LOCAL_LOG_DIR = r"D:\Results"
POLL_INTERVAL = 5
RETRY_INTERVAL = 10
MAX_RETRY_INTERVAL = 300

LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_registry.txt")

URL_UPLOAD = f"http://{SERVER_IP}:{SERVER_PORT}/api/upload_log"
URL_TELEMETRY = f"http://{SERVER_IP}:{SERVER_PORT}/api/telemetry/push"

global_last_file_time = 0
global_server_reachable = False
pending_buffer = set()
last_known_file_set = set()

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
                print(f"\n[{now_text()}] [CONNECT] >>> 服务器 {SERVER_IP}:{SERVER_PORT} 已连通！")
                global_server_reachable = True
            return True
    except Exception:
        pass

    if global_server_reachable:
        print(f"\n[{now_text()}] [CONNECT] !!! 服务器连接中断，正在重试...")
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
    print(f"   FCT4 - 机台ID: {MACHINE_ID}  |  本机IP: {MACHINE_IP}")
    print(f"   服务器: {SERVER_IP}:{SERVER_PORT}")
    print(f"   扫描目录: {LOCAL_LOG_DIR}")
    print(f"   账本文件: {LEDGER_FILE}")
    print("=" * 80)
    print()

def main():
    global global_last_file_time, global_server_reachable, pending_buffer, last_known_file_set

    print_banner()
    print(f"[{now_text()}] [START] FCT4 穿透采集引擎启动中...")
    print(f"[{now_text()}] [CONFIG] 服务器: {URL_UPLOAD}")
    print(f"[{now_text()}] [CONFIG] 扫描目录: {LOCAL_LOG_DIR}")
    print()

    ensure_dir(LOCAL_LOG_DIR)
    uploaded_ledger = load_uploaded_ledger()
    print(f"[{now_text()}] [LEDGER] 已加载 {len(uploaded_ledger)} 条历史传输记录。")

    all_startup_files = get_all_xml_files(LOCAL_LOG_DIR)
    total_xml = len(all_startup_files)
    last_known_file_set = set(os.path.basename(f) for f in all_startup_files)

    pending_list = []
    for f in all_startup_files:
        fn = os.path.basename(f)
        if fn not in uploaded_ledger:
            pending_list.append(fn)

    pending_buffer = set(pending_list)
    uploaded_count = total_xml - len(pending_list)

    print(f"[{now_text()}] [INVENTORY] 文件夹中共 {total_xml} 个 XML 文件")
    print(f"[{now_text()}] [INVENTORY] \u251c\u2500 已上传: {uploaded_count}")
    print(f"[{now_text()}] [INVENTORY] \u2514\u2500 待上传: {len(pending_list)}")
    if pending_list:
        print(f"[{now_text()}] [INVENTORY] 待上传文件列表:")
        for i, f in enumerate(pending_list[:30], 1):
            print(f"             {i:>3}. {f}")
        if len(pending_list) > 30:
            print(f"             ... 还有 {len(pending_list) - 30} 个文件")
    print()

    global_last_file_time = 0

    print(f"[{now_text()}] [START] 启动遥测心跳守护线程...")
    heartbeat_thread = threading.Thread(target=telemetry_daemon, daemon=True)
    heartbeat_thread.start()
    print()

    upload_fail_count = 0
    last_status_time = 0
    last_total_uploaded = len(uploaded_ledger)

    while True:
        try:
            current_xml_files = get_all_xml_files(LOCAL_LOG_DIR)
            current_file_set = set(os.path.basename(f) for f in current_xml_files)

            new_files = current_file_set - last_known_file_set
            for nf in new_files:
                if nf not in uploaded_ledger and nf not in pending_buffer:
                    pending_buffer.add(nf)
                    print(f"\n[{now_text()}] [NEW] \u2605 发现新日志: {nf}  (待上传: {len(pending_buffer)})")

            last_known_file_set = current_file_set

            files_uploaded = 0

            for filename in list(pending_buffer):
                if not global_server_reachable:
                    break

                file_path = None
                for fp in current_xml_files:
                    if os.path.basename(fp) == filename:
                        file_path = fp
                        break

                if not file_path:
                    pending_buffer.discard(filename)
                    continue

                try:
                    if os.path.getsize(file_path) == 0:
                        continue

                    try:
                        with open(file_path, 'rb') as f:
                            file_content = f.read()
                    except PermissionError:
                        continue

                    resp_data = upload_file_builtin(URL_UPLOAD, MACHINE_ID, filename, file_content)

                    if resp_data.get("ok"):
                        print(f"[{now_text()}] [OK] 上传成功: {filename}")
                        uploaded_ledger.add(filename)
                        pending_buffer.discard(filename)
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
                    break
                except Exception as e:
                    print(f"\n[{now_text()}] [ERROR] 传输异常: {str(e)}")

            if files_uploaded > 0:
                print(f"[{now_text()}] [BATCH] 本轮上传 {files_uploaded} 个，剩余待上传: {len(pending_buffer)}")

            now = time.time()
            if now - last_status_time >= 10:
                status = "ONLINE" if global_server_reachable else "OFFLINE"
                total = len(current_file_set)
                uploaded_c = len(uploaded_ledger)
                pending_c = len(pending_buffer)
                delta = uploaded_c - last_total_uploaded
                last_total_uploaded = uploaded_c
                if delta > 0:
                    print(f"[{now_text()}] [STATUS] \u2502 状态: {status} \u2502 目录XML: {total} \u2502 已上传: {uploaded_c} (+{delta}) \u2502 待上传: {pending_c}     ")
                else:
                    print(f"[{now_text()}] [STATUS] \u2502 状态: {status} \u2502 目录XML: {total} \u2502 已上传: {uploaded_c} \u2502 待上传: {pending_c}     ")
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