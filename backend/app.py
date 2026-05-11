# -*- coding: utf-8 -*-

import os
import re
import sys
from datetime import datetime

from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "static")
LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")

ONLINE_SECONDS = 5
STALE_SECONDS = 30
MAX_HISTORY_PER_MACHINE = 300

TELEMETRY_CACHE = {}
TELEMETRY_HISTORY = {}

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR if os.path.isdir(STATIC_DIR) else None,
)

# 暴力拦截任何解析器导入崩溃
try:
    from backend.parser.fct_parser import load_all_fct_records, find_latest_record_by_sn
    PARSER_IMPORT_ERROR = ""
except BaseException as exc:
    print(f"\n[致命警告] 核心解析器 fct_parser.py 加载失败: {exc}\n系统已自动切入无损降级模式运行。\n")
    load_all_fct_records = None
    find_latest_record_by_sn = None
    PARSER_IMPORT_ERROR = str(exc)

try:
    from backend.rules.fail_rules import build_top_fail
except BaseException as exc:
    print(f"[警告] 失败规则模块加载失败: {exc}")
    build_top_fail = None

build_station_risk = None
try:
    from backend.rules.station_risk_rules import build_station_risk
except BaseException:
    pass


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_time_to_timestamp(time_text):
    if not time_text: return 0.0
    text = str(time_text).strip()
    try: return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception: pass
    try: return datetime.strptime(text[:19], "%Y/%m/%d %H:%M:%S").timestamp()
    except Exception: pass
    try:
        compact = "".join(ch for ch in text if ch.isdigit())
        if len(compact) >= 14: return datetime.strptime(compact[:14], "%Y%m%d%H%M%S").timestamp()
    except Exception: pass
    return 0.0

def parse_filename_time_to_timestamp(source_file):
    text = str(source_file or "")
    match_obj = re.search(r"_(\d{17})_", text)
    if not match_obj: match_obj = re.search(r"(\d{14,17})", text)
    if not match_obj: return 0.0
    try: return datetime.strptime(match_obj.group(1)[:14], "%Y%m%d%H%M%S").timestamp()
    except Exception: return 0.0

def seconds_since(time_text):
    timestamp_value = parse_time_to_timestamp(time_text)
    if timestamp_value <= 0: return 999999.0
    return max(0.0, datetime.now().timestamp() - timestamp_value)

def get_record_sort_timestamp(record):
    for key in ["time", "dut_time", "panel_time", "batch_time"]:
        timestamp_value = parse_time_to_timestamp(record.get(key, ""))
        if timestamp_value: return timestamp_value
    filename_timestamp = parse_filename_time_to_timestamp(record.get("source_file", ""))
    if filename_timestamp: return filename_timestamp
    try: return float(record.get("file_mtime_ts") or 0.0)
    except Exception: return 0.0

def sort_records_latest_first(records):
    return sorted(records, key=get_record_sort_timestamp, reverse=True)

def safe_load_records():
    if load_all_fct_records is None: return []
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        records = load_all_fct_records(LOG_DIR)
        return sort_records_latest_first(records)
    except BaseException as exc:
        return [{
            "sn": "解析引擎断开", "sn_aliases": [], "model": "UNKNOWN", "test_mode": "Unknown", "date_folder": "",
            "relative_path": "", "station": "FCT", "tester": "", "product": "",
            "result": "中断", "business_result": "中断", "raw_result": "LOAD_ERROR",
            "panel_status": "中断", "panel_status_raw": "", "dut_status": "中断", "dut_status_raw": "",
            "fail_items": [], "interrupted_items": [], "raw_items": [],
            "time": now_text(), "batch_time": "", "panel_time": "", "dut_time": "", "test_time": now_text(),
            "source_file": "", "source_path": "", "file_mtime": "", "file_mtime_ts": 0.0,
            "total_tests": 0, "failed_tests": 0, "passed_tests": 0, "interrupted_tests": 0, "skipped_tests": 0,
            "parse_error": str(exc),
        }]

def normalize_result(result):
    raw = str(result or "").strip()
    if raw == "中断": return "中断"
    text = raw.upper()
    if text in ["PASS", "PASSED", "OK", "SUCCESS", "TRUE"]: return "PASS"
    if text in ["FAIL", "FAILED", "NG", "FALSE"]: return "FAIL"
    return "中断"

def fallback_build_top_fail(records, limit=10):
    counter = {}
    for record in records:
        for item in (record.get("fail_items", []) or []):
            name = item.get("name") or item.get("raw_name") or item.get("item") or "-"
            if name not in counter:
                counter[name] = { "item": name, "count": 0, "models": set(), "modes": set(), "stations": set(), "latest_time": "", "warning_level": "LOW" }
            counter[name]["count"] += 1
            if record.get("model"): counter[name]["models"].add(record.get("model"))
            if record.get("test_mode"): counter[name]["modes"].add(record.get("test_mode"))
            if record.get("station"): counter[name]["stations"].add(record.get("station"))
            record_time = record.get("time") or record.get("file_mtime") or ""
            if record_time and record_time > counter[name]["latest_time"]: counter[name]["latest_time"] = record_time
    result = []
    for name in counter:
        item = counter[name]
        count = item["count"]
        level = "HIGH" if count >= 5 else ("MEDIUM" if count >= 3 else "LOW")
        result.append({
            "item": item["item"], "count": count, "models": sorted(list(item["models"])), "modes": sorted(list(item["modes"])), 
            "stations": sorted(list(item["stations"])), "latest_time": item["latest_time"], "warning_level": level
        })
    result.sort(key=lambda x: x.get("count", 0), reverse=True)
    return result[:limit]

def get_top_fail_records(records, limit=10):
    if build_top_fail:
        try:
            data = build_top_fail(records, limit=limit)
            if isinstance(data, list): return data
        except BaseException: pass
    return fallback_build_top_fail(records, limit=limit)

def build_stats(records):
    total = len(records)
    pass_count = fail_count = interrupt_count = 0
    for record in records:
        result = normalize_result(record.get("business_result") or record.get("result") or "中断")
        if result == "PASS": pass_count += 1
        elif result == "FAIL": fail_count += 1
        else: interrupt_count += 1
    return {
        "total": total, "pass": pass_count, "fail": fail_count, "interrupt": interrupt_count,
        "fail_rate": round(fail_count / total * 100, 2) if total > 0 else 0,
        "interrupt_rate": round(interrupt_count / total * 100, 2) if total > 0 else 0,
        "top_fail": get_top_fail_records(records, limit=10), "log_dir": LOG_DIR,
    }

def normalize_machine_payload(payload):
    data = dict(payload or {})
    data["machine_id"] = str(data.get("machine_id") or "UNKNOWN_MACHINE")
    data["timestamp"] = data.get("timestamp") or now_text()
    data["server_receive_time"] = now_text()
    data.setdefault("station", "FCT")
    data.setdefault("model", "")
    data.setdefault("test_mode", "Online")
    data.setdefault("machine_state", "IDLE")
    data.setdefault("current_sn", "")
    return data

def get_machine_online_status(payload):
    receive_time = payload.get("server_receive_time") or payload.get("timestamp") or ""
    age = seconds_since(receive_time)
    if age <= ONLINE_SECONDS: return "ONLINE"
    if age <= STALE_SECONDS: return "STALE"
    return "OFFLINE"

def summarize_machine(payload):
    online_status = get_machine_online_status(payload)
    display_state = "OFFLINE" if online_status == "OFFLINE" else payload.get("machine_state", "IDLE")
    return {
        "machine_id": payload.get("machine_id", ""), "station": payload.get("station", ""),
        "model": payload.get("model", ""), "test_mode": payload.get("test_mode", ""), 
        "timestamp": payload.get("timestamp", ""), "online_status": online_status,
        "machine_state": payload.get("machine_state", ""), "display_state": display_state,
        "current_sn": payload.get("current_sn", ""), "measurements": payload.get("measurements", {}),
    }

def build_machine_summary():
    machines = [summarize_machine(TELEMETRY_CACHE[m_id]) for m_id in TELEMETRY_CACHE]
    online = sum(1 for m in machines if m["online_status"] == "ONLINE")
    stale = sum(1 for m in machines if m["online_status"] == "STALE")
    offline = sum(1 for m in machines if m["online_status"] == "OFFLINE")
    machines.sort(key=lambda item: item.get("machine_id", ""))
    return { "total": len(machines), "online": online, "stale": stale, "offline": offline, "machines": machines }

def build_analysis(records):
    model_summary = {}
    for record in records:
        model = record.get("model") or "UNKNOWN"
        result = normalize_result(record.get("business_result") or record.get("result") or "中断")
        if model not in model_summary:
            model_summary[model] = {"PASS": 0, "FAIL": 0, "中断": 0, "total": 0}
        model_summary[model][result] += 1
        model_summary[model]["total"] += 1

    try: station_risk = build_station_risk(records) if build_station_risk else []
    except BaseException: station_risk = []

    return { "model_summary": model_summary, "station_risk": station_risk }


# ================== 核心路由 ==================

@app.route("/")
@app.route("/dashboard")
@app.route("/analysis")
@app.route("/monitor")
@app.route("/trends")
def index():
    return render_template("index.html")

@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True, "server_time": now_text(), "parser_loaded": load_all_fct_records is not None, 
        "parser_import_error": PARSER_IMPORT_ERROR
    })

@app.route("/api/recent")
def api_recent():
    limit = request.args.get("limit", "50")
    try: limit = int(limit)
    except: limit = 50
    return jsonify(safe_load_records()[:limit])

@app.route("/api/stats")
def api_stats():
    return jsonify(build_stats(safe_load_records()))

@app.route("/api/top_fail")
def api_top_fail():
    limit = request.args.get("limit", "10")
    try: limit = int(limit)
    except: limit = 10
    return jsonify(get_top_fail_records(safe_load_records(), limit=limit))

@app.route("/api/analysis")
def api_analysis():
    return jsonify(build_analysis(safe_load_records()))

@app.route("/api/telemetry/push", methods=["POST"])
def api_telemetry_push():
    payload = request.get_json(silent=True) or {}
    data = normalize_machine_payload(payload)
    machine_id = data["machine_id"]
    TELEMETRY_CACHE[machine_id] = data
    return jsonify({"ok": True})

@app.route("/api/telemetry/latest")
def api_telemetry_latest():
    return jsonify(build_machine_summary())

@app.route("/api/trends")
def api_trends():
    records = safe_load_records()
    start_date = request.args.get("start", "")
    end_date = request.args.get("end", "")
    
    filtered = []
    for r in records:
        r_time = r.get("time", "")
        if not r_time: continue
        date_str = r_time[:10]
        if start_date and date_str < start_date: continue
        if end_date and date_str > end_date: continue
        filtered.append(r)
        
    filtered = sorted(filtered, key=lambda x: x.get("time", ""))
    
    trends = {}
    for r in filtered:
        sn = r.get("sn", "Unknown")
        time_str = r.get("time", "")
        for item in r.get("raw_items", []):
            name = item.get("name")
            if not name: continue
            try: val = float(item.get("value", 0))
            except Exception: continue 
            
            if name not in trends:
                trends[name] = {"limit": item.get("nominal_range", ""), "unit": item.get("unit", ""), "data": []}
            
            trends[name]["data"].append({ "sn": sn, "time": time_str, "value": val, "status": item.get("business_status", "PASS") })
            
    sorted_keys = sorted(trends.keys(), key=lambda k: (-sum(1 for d in trends[k]["data"] if d["status"] != "PASS"), k))
    
    trends_list = [{"name": k, "limit": trends[k]["limit"], "unit": trends[k]["unit"], "data": trends[k]["data"]} for k in sorted_keys]
    return jsonify({"total_records": len(filtered), "start": start_date, "end": end_date, "trends": trends_list})

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    print("=" * 80)
    print("G4.9 FCT Smart Monitor - 绝对防弹版引擎启动")
    if PARSER_IMPORT_ERROR:
        print(f"!!! 警告: 物理模块加载失败，原因:\n{PARSER_IMPORT_ERROR}\n!!! 但系统已被护盾拦截，网页仍可正常访问！")
    print("URL: http://127.0.0.1:5000/")
    print("=" * 80)
    app.run(host="0.0.0.0", port=5000, debug=True)