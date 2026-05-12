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

# --- 终极护盾：在操作系统环境变量层面直接禁用代理，彻底避开代理模块 ---
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

# ==========================================
# ⚙️ 产线工控机配置区 (Production Config)
# ==========================================
SERVER_IP = "10.222.126.115"  # 将由 bat 脚本自动替换
SERVER_PORT = "5000"
MACHINE_ID = "PEU_G49_FCT6_01" # 将由 bat 脚本自动替换

LOCAL_LOG_DIR = r"D:\Results"
# [中枢修改批注 1: 移除 ARCHIVE_DIR，新增本地账本文件路径，保存在脚本同级目录]
LEDGER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploaded_registry.txt")

POLL_INTERVAL = 5
# ==========================================

URL_UPLOAD = f"http://{SERVER_IP}:{SERVER_PORT}/api/upload_log"
URL_TELEMETRY = f"http://{SERVER_IP}:{SERVER_PORT}/api/telemetry/push"

global_last_file_time = 0

def print_banner():
    os.system("color 0A")
    banner = r"""
    ███████╗ ██████╗████████╗    ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗██████╗ ██████╗ 
    ██╔════╝██╔════╝╚══██╔══╝    ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
    █████╗  ██║        ██║       ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
    ██╔══╝  ██║        ██║       ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
    ██║     ╚██████╗   ██║       ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
    ╚═╝      ╚═════╝   ╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
                                                                                           
=========================================================================================
        FCT 边缘采集与遥测节点 (Win10 Read-Only Ledger Edition)
=========================================================================================
"""
    print(banner)

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# [中枢新增批注 2: 账本加载机制]
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
            "ip": socket.gethostbyname(socket.gethostname()),
        }

        try:
            push_telemetry_builtin(URL_TELEMETRY, telemetry_payload)
        except Exception as e:
            print(f"\n[{now_text()}] ⚠️ 遥测心跳失败: {str(e)}")
            
        time.sleep(POLL_INTERVAL)

def main():
    global global_last_file_time
    
    print_banner()
    print(f" [*] 纯净版穿透采集引擎已就绪 (绝对只读模式)")
    print(f" [📡] 目标中枢: {URL_UPLOAD}")
    print(f" [📁] 深度扫描目录: {LOCAL_LOG_DIR} (绝对只读，绝不修改)")
    print(f" [📓] 防重传账本: {LEDGER_FILE}")
    print("=========================================================================================\n")

    ensure_dir(LOCAL_LOG_DIR)
    
    # 启动前将历史已传名单加载到内存
    uploaded_ledger = load_uploaded_ledger()
    print(f" [*] 已从本地账本加载 {len(uploaded_ledger)} 条历史传输记录。")

    global_last_file_time = 0

    heartbeat_thread = threading.Thread(target=telemetry_daemon, daemon=True)
    heartbeat_thread.start()

    while True:
        try:
            xml_files = get_all_xml_files(LOCAL_LOG_DIR)
            files_uploaded = 0
            
            for file_path in xml_files:
                filename = os.path.basename(file_path)
                
                # [中枢新增批注 3: O(1) 账本防重拦截，文件若已在内存集合中，直接跳过，连文件大小都不去读]
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
                        print(f"[{now_text()}] ✅ 成功拷贝并上传: {filename}")
                        
                        # [中枢新增批注 4: 上传成功后，不仅更新内存，还要追加写入 txt 账本文件]
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
                print(f"[{now_text()}] 💤 递归监听中 (穿透扫描 D:\\Results\\*)...", end="\r")

        except KeyboardInterrupt:
            print("\n🛑 手动停止。")
            break
        except Exception as e:
            print(f"\n[{now_text()}] 💥 严重异常: {str(e)}")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()