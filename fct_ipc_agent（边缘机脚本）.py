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

# --- 终极护盾：在操作系统环境变量层面直接禁用代理，彻底避开代理模块 ---
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['NO_PROXY'] = '*'

# ==========================================
# ⚙️ 产线工控机配置区
# ==========================================
SERVER_IP = "10.222.126.115"  # 你的办公室服务器 IP
SERVER_PORT = "5000"
MACHINE_ID = "PEU_G49_FCT6_01"

LOCAL_LOG_DIR = r"D:\FTS\Logs\XML"
ARCHIVE_DIR = r"D:\FTS\Logs\Uploaded_Archive"
POLL_INTERVAL = 5
# ==========================================

URL_UPLOAD = f"http://{SERVER_IP}:{SERVER_PORT}/api/upload_log"
URL_TELEMETRY = f"http://{SERVER_IP}:{SERVER_PORT}/api/telemetry/push"

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
             G4.9 产线边缘采集与遥测节点 (Ultra-Lite Edge Agent)
=========================================================================================
"""
    print(banner)

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def get_all_xml_files(base_dir, exclude_dir):
    xml_files = []
    exclude_norm = os.path.normpath(exclude_dir).lower()
    for root, dirs, files in os.walk(base_dir):
        if exclude_norm in os.path.normpath(root).lower():
            continue
        for file in files:
            if file.lower().endswith(".xml"):
                xml_files.append(os.path.join(root, file))
    return xml_files

# --- 纯底层核心：极致降级的无代理表单上传 ---
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
    
    # 环境变量已阻断代理，直接调用最基础的 urlopen 规避报错
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode('utf-8'))

def push_telemetry_builtin(url, payload):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('Content-Type', 'application/json')
    
    urllib.request.urlopen(req, timeout=3)

def main():
    print_banner()
    print(f" [*] 纯净版采集引擎已就绪 (防爆降级模式)")
    print(f" [📡] 目标中枢服务器: {URL_UPLOAD}")
    print(f" [📁] 本地监控根目录: {LOCAL_LOG_DIR}")
    print(f" [📦] 传输后归档路径: {ARCHIVE_DIR}")
    print("=========================================================================================\n")

    ensure_dir(LOCAL_LOG_DIR)
    ensure_dir(ARCHIVE_DIR)

    last_file_time = 0

    while True:
        try:
            xml_files = get_all_xml_files(LOCAL_LOG_DIR, ARCHIVE_DIR)
            files_uploaded = 0
            
            for file_path in xml_files:
                filename = os.path.basename(file_path)
                try:
                    if os.path.getsize(file_path) == 0:
                        print(f"[{now_text()}] ⏳ 文件生成中(0KB)，等待写入完成: {filename}")
                        continue
                    
                    try:
                        with open(file_path, 'rb') as f:
                            file_content = f.read()
                    except PermissionError:
                        print(f"[{now_text()}] 🔒 文件正被独占占用，等待释放: {filename}")
                        continue

                    # 调用底层降级版无依赖上传
                    resp_data = upload_file_builtin(URL_UPLOAD, MACHINE_ID, filename, file_content)
                    
                    if resp_data.get("ok"):
                        print(f"[{now_text()}] ✅ 成功上传: {filename}")
                        dest_path = os.path.join(ARCHIVE_DIR, filename)
                        if os.path.exists(dest_path): 
                            os.remove(dest_path)
                        shutil.move(file_path, ARCHIVE_DIR)
                        files_uploaded += 1
                        last_file_time = time.time()
                    else:
                        print(f"[{now_text()}] ❌ 上传被拒绝 {filename}: {resp_data.get('error', '未知错误')}")
                        
                except urllib.error.URLError as e:
                    print(f"[{now_text()}] ⚠️ 无法连接服务器(检查IP或端口): {str(e.reason)}")
                except Exception as e:
                    print(f"[{now_text()}] ⚠️ 传输中断 {filename}: {str(e)}")

            current_state = "RUNNING" if (time.time() - last_file_time < 60) else "IDLE"
            telemetry_payload = {
                "machine_id": MACHINE_ID,
                "timestamp": now_text(),
                "machine_state": current_state,
                "host_name": socket.gethostname(),
                "ip": socket.gethostbyname(socket.gethostname()),
            }

            try:
                push_telemetry_builtin(URL_TELEMETRY, telemetry_payload)
            except Exception:
                pass 
            
            if files_uploaded == 0:
                print(f"[{now_text()}] 💤 递归监听中... 机台状态: {current_state}", end="\r")

        except KeyboardInterrupt:
            print("\n🛑 采集器已手动停止。")
            break
        except Exception as e:
            print(f"\n[{now_text()}] 💥 发生严重异常: {str(e)}")
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()


#如果以后你的领导让你修复这个项目，快跑，不要回头！因为这个项目的代码质量实在是太差了，因为这我自己写的我心里能没数吗