# -*- coding: utf-8 -*-
import os
import time
import json
import shutil
import socket
import traceback
import urllib.request
import urllib.error
from datetime import datetime

os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

# [修改对比批注]
# 原内容: SERVER_IP = "172.28.x.x"
# 修改逻辑: 指向 Ubuntu 服务器。
SERVER_IP = "192.168.x.x"  # <--- 请在此处输入 Ubuntu 服务器的实际 IP [修改点]

SERVER_PORT = "5000"  # 服务器监听端口

MACHINE_ID = "FCT_STATION_16" 

LOCAL_LOG_DIR = r"D:\FTS\Logs\XML"
ARCHIVE_DIR = r"D:\FTS\Logs\Uploaded_Archive"
POLL_INTERVAL = 5

URL_UPLOAD = f"http://{SERVER_IP}:{SERVER_PORT}/api/upload_log"
URL_TELEMETRY = f"http://{SERVER_IP}:{SERVER_PORT}/api/telemetry/push"

# ... (print_banner, now_text 等业务逻辑保持原样) ...

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
        PEU FCT Edge Agent | Machine IP: 172.28.55.16 | ID: PEU_FCT_2
=========================================================================================
""")

def now_text(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path):
    if not os.path.exists(path): os.makedirs(path, exist_ok=True)

def get_all_xml_files(base_dir, exclude_dir):
    xml_files = []
    exclude_norm = os.path.normpath(exclude_dir).lower()
    for root, dirs, files in os.walk(base_dir):
        if exclude_norm in os.path.normpath(root).lower(): continue
        for file in files:
            if file.lower().endswith(".xml"): xml_files.append(os.path.join(root, file))
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
    req = urllib.request.Request(url, data=data)
    req.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req, timeout=3)

def main():
    print_banner()
    ensure_dir(LOCAL_LOG_DIR)
    ensure_dir(ARCHIVE_DIR)
    last_file_time = 0
    print(f" [*] 6号机启动成功，监控目录: {LOCAL_LOG_DIR}\n")

    while True:
        try:
            xml_files = get_all_xml_files(LOCAL_LOG_DIR, ARCHIVE_DIR)
            files_uploaded = 0
            for file_path in xml_files:
                filename = os.path.basename(file_path)
                try:
                    if os.path.getsize(file_path) == 0: continue
                    with open(file_path, 'rb') as f: file_content = f.read()
                    resp_data = upload_file_builtin(URL_UPLOAD, MACHINE_ID, filename, file_content)
                    if resp_data.get("ok"):
                        print(f"[{now_text()}] ✅ 成功上传: {filename}")
                        dest_path = os.path.join(ARCHIVE_DIR, filename)
                        if os.path.exists(dest_path): os.remove(dest_path)
                        shutil.move(file_path, ARCHIVE_DIR)
                        files_uploaded += 1
                        last_file_time = time.time()
                except Exception as e: print(f"[{now_text()}] ⚠️ 传输中断: {str(e)}")

            # 遥测心跳
            current_state = "RUNNING" if (time.time() - last_file_time < 60) else "IDLE"
            payload = {
                "machine_id": MACHINE_ID, "timestamp": now_text(),
                "machine_state": current_state, "ip": "172.28.55.16"
            }
            try: push_telemetry_builtin(URL_TELEMETRY, payload)
            except: pass
            if files_uploaded == 0:
                print(f"[{now_text()}] 💤 监听中... 机台 IP: 172.28.55.16 | 状态: {current_state}", end="\r")
        except Exception as e: print(f"\n[{now_text()}] 💥 异常: {str(e)}")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()