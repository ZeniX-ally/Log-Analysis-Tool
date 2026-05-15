# -*- coding: utf-8 -*-
"""
NEXUS FCT Server Web Dashboard — 服务器状态网页监控
====================================================
用法:  python tools/server_dashboard.py [--target-host IP] [--target-port PORT]

启动一个独立的 Web 服务 (端口 54188)，
从主服务器 (默认 localhost:59488) 拉取状态数据并展示为网页。
"""

import os
import sys
import json
import time
import argparse
import threading
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

try:
    from flask import Flask, jsonify, render_template, Response
except ImportError:
    print("[ERROR] Flask is required. Install with: pip install flask")
    sys.exit(1)

DASHBOARD_PORT = 54188
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)

CACHE = {"data": None, "timestamp": 0, "error": None}
CACHE_TTL = 1.5
TARGET_HOST = "localhost"
TARGET_PORT = 59488


def fetch_server_status():
    url = f"http://{TARGET_HOST}:{TARGET_PORT}/api/server/status"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except URLError as e:
        return None, f"Connection failed: {e.reason}"
    except Exception as e:
        return None, str(e)


def get_cached_data():
    now = time.time()
    if CACHE["data"] is not None and now - CACHE["timestamp"] < CACHE_TTL:
        return CACHE["data"], CACHE["error"]
    data, error = fetch_server_status()
    CACHE["data"] = data
    CACHE["timestamp"] = now
    CACHE["error"] = error
    return data, error


@app.route("/")
def index():
    return render_template("server_dashboard.html", target_host=TARGET_HOST, target_port=TARGET_PORT)


@app.route("/api/status")
def api_status():
    data, error = get_cached_data()
    if error:
        return jsonify({"ok": False, "error": error})
    return jsonify({"ok": True, "data": data})


@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "server": f"http://{TARGET_HOST}:{TARGET_PORT}",
        "dashboard_port": DASHBOARD_PORT,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXUS FCT Web Dashboard")
    parser.add_argument("--target-host", default="localhost", help="Main server host (default: localhost)")
    parser.add_argument("--target-port", type=int, default=59488, help="Main server port (default: 59488)")
    parser.add_argument("--port", type=int, default=DASHBOARD_PORT, help="Dashboard port (default: 54188)")
    args = parser.parse_args()

    TARGET_HOST = args.target_host
    TARGET_PORT = args.target_port
    DASHBOARD_PORT = args.port

    os.makedirs(TEMPLATE_DIR, exist_ok=True)

    print(f"[DASHBOARD] Web Dashboard starting...")
    print(f"[DASHBOARD] Target server: http://{TARGET_HOST}:{TARGET_PORT}")
    print(f"[DASHBOARD] Dashboard URL: http://localhost:{DASHBOARD_PORT}")
    print(f"[DASHBOARD] Press Ctrl+C to stop")

    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False, threaded=True)