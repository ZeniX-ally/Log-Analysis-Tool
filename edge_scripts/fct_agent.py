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

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    default_config = {
        "server_ip": "172.28.55.66",
        "server_port": "59488",
        "machine_id": "PEU_G49_FCT1_01",
        "machine_ip": "172.28.55.11",
        "log_dir": "D:\\Results",
        "poll_interval": 5
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k in default_config:
                if k not in cfg:
                    cfg[k] = default_config[k]
            return cfg
        except Exception as e:
            print(f"[{now_text()}] ⚠️ 配置文件加载失败: {e}，使用默认配置")
    return default_config

CONFIG = load_config()

SERVER_IP = CONFIG["server_ip"]
SERVER_PORT = CONFIG["server_port"]
MACHINE_ID = CONFIG["machine_id"]
MACHINE_IP = CONFIG["machine_ip"]
LOCAL_LOG_DIR = CONFIG["log_dir"]
POLL_INTERVAL = CONFIG["poll_interval"]

LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_registry.txt")

URL_UPLOAD = f"http://{SERVER_IP}:{SERVER_PORT}/api/upload_log"
URL_TELEMETRY = f"http://{SERVER_IP}:{SERVER_PORT}/api/telemetry/push"

global_last_file_time = 0

def print_banner():
    os.system("color 0A")
    print(r"""
    ███████╗ ███████╗ ███╗   ██╗ ██╗ ██╗  ██╗          █████╗  ██╗      ██╗      ██╗   ██╗
    ╚══███╔╝ ██╔════╝ ████╗  ██║ ██║ ╚██╗██╔╝         ██╔══██╗ ██║      ██║      ╚██╗ ██╔╝
      ███╔╝  █████╗   ██╔██╗ ██║ ██║  ╚███╔╝  ███████╗███████║ ██║      ██║       ╚████╔╝ 
     ███╔╝   ██╔══╝   ██║╚██╗██║ ██║  ██╔██╗  ╚══════╝██╔══██║ ██║      ██║        ╚██╔╝  
    ███████╗ ███████╗ ██║ ╚████║ ██║ ██╔╝ ██╗         ██║  ██║ ███████╗ ███████╗    ██║   
    ╚══════╝ ╚══════╝ ╚═╝  ╚═══╝ ╚═╝ ╚═╝  ╚═╝         ╚═╝  ╚═╝ ╚══════╝ ╚══════╝    ╚═╝   
=========================================================================================
        PEU FCT Edge Agent | Machine IP: """ + MACHINE_IP + """ | ID: """ + MACHINE_ID + """
=========================================================================================
""")

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def load_uploaded_ledger():
    ledger_set = set()
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    ledger_set.add(line.strip())
        except Exception as e:
            print(f"[{now_text()}] ⚠️ 账本加载异常: {e}")
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
    while True:
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
            print(f"\n[{now_text()}] ⚠️ 遥测心跳失败: {str(e)}")
        time.sleep(POLL_INTERVAL)

def main():
    global global_last_file_time

    print_banner()
    print(f" [*] 穿透采集引擎已就绪 (绝对只读模式)")
    print(f" [>>] 服务器: {URL_UPLOAD}")
    print(f" [>>] 扫描目录: {LOCAL_LOG_DIR} (绝不修改原始文件)")
    print(f" [>>] 防重传账本: {LEDGER_FILE}")
    print(f" [>>] 轮询间隔: {POLL_INTERVAL}秒")
    print("=========================================================================================\n")

    ensure_dir(LOCAL_LOG_DIR)
    uploaded_ledger = load_uploaded_ledger()
    print(f" [*] 已加载 {len(uploaded_ledger)} 条历史传输记录。\n")

    global_last_file_time = 0

    heartbeat_thread = threading.Thread(target=telemetry_daemon, daemon=True)
    heartbeat_thread.start()

    while True:
        try:
            xml_files = get_all_xml_files(LOCAL_LOG_DIR)
            files_uploaded = 0

            for file_path in xml_files:
                filename = os.path.basename(file_path)
                if filename in uploaded_ledger:
                    continue

                try:
                    if os.path.getsize(file_path) == 0:
                        print(f"[{now_text()}] ⏳ 文件生成中(0KB): {filename}")
                        continue

                    try:
                        with open(file_path, 'rb') as f:
                            file_content = f.read()
                    except PermissionError:
                        print(f"[{now_text()}] 🔒 测控软件正独占占用: {filename}")
                        continue

                    resp_data = upload_file_builtin(URL_UPLOAD, MACHINE_ID, filename, file_content)

                    if resp_data.get("ok"):
                        print(f"[{now_text()}] >>> 成功上传: {filename}")
                        uploaded_ledger.add(filename)
                        try:
                            with open(LEDGER_FILE, 'a', encoding='utf-8') as lf:
                                lf.write(filename + '\n')
                        except Exception as e:
                            print(f"[{now_text()}] ⚠️ 写入账本失败: {e}")
                        files_uploaded += 1
                        global_last_file_time = time.time()
                    else:
                        print(f"[{now_text()}] ❌ 上传拒绝 {filename}: {resp_data.get('error', '未知错误')}")

                except urllib.error.URLError as e:
                    print(f"[{now_text()}] ⚠️ 连接丢失: {str(e.reason)}")
                except Exception as e:
                    print(f"[{now_text()}] ⚠️ 传输出错 {filename}: {str(e)}")

            if files_uploaded == 0:
                print(f"[{now_text()}] 💤 监听中 ({LOCAL_LOG_DIR}\\*.xml)...", end="\r")

        except KeyboardInterrupt:
            print("\n 手动停止。")
            break
        except Exception as e:
            print(f"\n[{now_text()}] 💥 严重异常: {str(e)}")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()