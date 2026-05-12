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

try:
    from backend.parser.fct_parser import load_all_fct_records
    from backend.parser.fct_parser import find_latest_record_by_sn
except Exception as exc:
    load_all_fct_records = None
    find_latest_record_by_sn = None
    PARSER_IMPORT_ERROR = str(exc)
else:
    PARSER_IMPORT_ERROR = ""

try:
    from backend.rules.fail_rules import build_top_fail
except Exception:
    build_top_fail = None

try:
    from backend.rules.station_risk_rules import build_station_risk
except Exception:
    build_station_risk = None


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_time_to_timestamp(time_text):
    if not time_text:
        return 0.0
    text = str(time_text).strip()
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        pass
    try:
        return datetime.strptime(text[:19], "%Y/%m/%d %H:%M:%S").timestamp()
    except Exception:
        pass
    try:
        compact = "".join([ch for ch in text if ch.isdigit()])
        if len(compact) >= 14:
            return datetime.strptime(compact[:14], "%Y%m%d%H%M%S").timestamp()
    except Exception:
        pass
    return 0.0


def parse_filename_time_to_timestamp(source_file):
    text = str(source_file or "")
    match_obj = re.search(r"_(\d{17})_", text)
    if not match_obj:
        match_obj = re.search(r"(\d{14,17})", text)
    if not match_obj:
        return 0.0
    try:
        return datetime.strptime(match_obj.group(1)[:14], "%Y%m%d%H%M%S").timestamp()
    except Exception:
        return 0.0


def seconds_since(time_text):
    timestamp_value = parse_time_to_timestamp(time_text)
    if timestamp_value <= 0:
        return 999999.0
    return max(0.0, datetime.now().timestamp() - timestamp_value)


def get_record_sort_timestamp(record):
    for key in ["time", "dut_time", "panel_time", "batch_time"]:
        timestamp_value = parse_time_to_timestamp(record.get(key, ""))
        if timestamp_value:
            return timestamp_value
    filename_timestamp = parse_filename_time_to_timestamp(record.get("source_file", ""))
    if filename_timestamp:
        return filename_timestamp
    try:
        return float(record.get("file_mtime_ts") or 0.0)
    except Exception:
        return 0.0


def sort_records_latest_first(records):
    return sorted(records, key=get_record_sort_timestamp, reverse=True)


def safe_load_records():
    if load_all_fct_records is None:
        return []
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        records = load_all_fct_records(LOG_DIR)
        return sort_records_latest_first(records)
    except Exception as exc:
        return []


def normalize_result(result):
    raw = str(result or "").strip()
    if raw == "中断":
        return "中断"
    
    text = raw.upper()
    if "PASS" in text or "OK" in text or "SUCCESS" in text or "TRUE" in text:
        return "PASS"
    if "FAIL" in text or "NG" in text or "FALSE" in text:
        return "FAIL"
    return "中断"


def fallback_build_top_fail(records, limit=10):
    counter = {}
    for record in records:
        fail_items = record.get("fail_items", []) or []
        for item in fail_items:
            name = item.get("name") or item.get("raw_name") or item.get("item") or "-"
            
            # 自动剔除因人为操作导致的 Get Unit Info 报错
            if "GET UNIT INFO" in name.upper() or "GET_UNIT_INFO" in name.upper():
                continue

            if name not in counter:
                counter[name] = {
                    "item": name,
                    "count": 0,
                    "models": set(),
                    "modes": set(),
                    "stations": set(),
                    "latest_time": "",
                    "warning_level": "LOW",
                }
            counter[name]["count"] += 1
            if record.get("model"):
                counter[name]["models"].add(record.get("model"))
            if record.get("test_mode"):
                counter[name]["modes"].add(record.get("test_mode"))
            if record.get("station"):
                counter[name]["stations"].add(record.get("station"))
            
            record_time = record.get("time") or record.get("file_mtime") or ""
            if record_time and record_time > counter[name]["latest_time"]:
                counter[name]["latest_time"] = record_time

    result = []
    for name in counter:
        item = counter[name]
        count = item["count"]
        if count >= 5:
            level = "HIGH"
        elif count >= 3:
            level = "MEDIUM"
        else:
            level = "LOW"
        
        result.append({
            "item": item["item"],
            "count": count,
            "models": sorted(list(item["models"])),
            "modes": sorted(list(item["modes"])),
            "stations": sorted(list(item["stations"])),
            "latest_time": item["latest_time"],
            "warning_level": level,
        })

    result.sort(key=lambda x: x.get("count", 0), reverse=True)
    return result[:limit]


def get_top_fail_records(records, limit=10):
    if build_top_fail:
        try:
            data = build_top_fail(records, limit=limit)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return fallback_build_top_fail(records, limit=limit)


def build_stats(records):
    total = len(records)
    pass_count = 0
    fail_count = 0
    interrupt_count = 0

    for record in records:
        result = record.get("business_result") or record.get("result") or "中断"
        result = normalize_result(result)

        if result == "PASS":
            pass_count += 1
        elif result == "FAIL":
            fail_count += 1
        else:
            interrupt_count += 1

    fpy = 0
    fail_rate = 0
    interrupt_rate = 0

    if total > 0:
        fpy = round(pass_count / total * 100, 2)
        fail_rate = round(fail_count / total * 100, 2)
        interrupt_rate = round(interrupt_count / total * 100, 2)

    return {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "interrupt": interrupt_count,
        "fpy": fpy,
        "fail_rate": fail_rate,
        "interrupt_rate": interrupt_rate,
        "top_fail": get_top_fail_records(records, limit=10),
        "log_dir": LOG_DIR,
    }

def normalize_machine_payload(payload):
    data = dict(payload or {})
    data["machine_id"] = str(data.get("machine_id") or "UNKNOWN_MACHINE")
    data["timestamp"] = data.get("timestamp") or now_text()
    data["server_receive_time"] = now_text()
    data.setdefault("station", "FCT")
    data.setdefault("line", "")
    data.setdefault("host_name", "")
    data.setdefault("ip", "")
    data.setdefault("model", "")
    data.setdefault("test_mode", "Online")
    data.setdefault("machine_state", "IDLE")
    data.setdefault("current_sn", "")
    data.setdefault("current_step", "")
    data.setdefault("instruments", {})
    data.setdefault("measurements", {})
    data.setdefault("communication", {})
    data.setdefault("alarms", [])
    return data

def get_machine_online_status(payload):
    receive_time = payload.get("server_receive_time") or payload.get("timestamp") or ""
    age = seconds_since(receive_time)
    if age <= ONLINE_SECONDS: return "ONLINE"
    if age <= STALE_SECONDS: return "STALE"
    return "OFFLINE"

def summarize_machine(payload):
    online_status = get_machine_online_status(payload)
    instruments = payload.get("instruments") or {}
    offline_instruments = []
    if isinstance(instruments, dict):
        for name in instruments:
            info = instruments.get(name)
            if isinstance(info, dict):
                status = str(info.get("status", "")).upper()
                online = info.get("online", None)
                if status == "OFFLINE" or online is False:
                    offline_instruments.append(name)

    alarms = payload.get("alarms") or []
    alarm_count = len(alarms) if isinstance(alarms, list) else 1

    if online_status == "OFFLINE": display_state = "OFFLINE"
    elif online_status == "STALE": display_state = "STALE"
    elif alarm_count > 0 or len(offline_instruments) > 0: display_state = "WARNING"
    else: display_state = payload.get("machine_state", "IDLE")

    return {
        "machine_id": payload.get("machine_id", ""),
        "online_status": online_status,
        "display_state": display_state,
        "model": payload.get("model", ""),
        "test_mode": payload.get("test_mode", ""),
        "current_sn": payload.get("current_sn", ""),
        "current_step": payload.get("current_step", ""),
        "measurements": payload.get("measurements", {}),
        "alarm_count": alarm_count,
    }

def build_machine_summary():
    machines = [summarize_machine(TELEMETRY_CACHE[m]) for m in TELEMETRY_CACHE]
    online = sum(1 for m in machines if m.get("online_status") == "ONLINE")
    stale = sum(1 for m in machines if m.get("online_status") == "STALE")
    offline = sum(1 for m in machines if m.get("online_status") == "OFFLINE")
    machines.sort(key=lambda item: item.get("machine_id", ""))
    return {"total": len(machines), "online": online, "stale": stale, "offline": offline, "machines": machines}

def build_analysis(records):
    stats = build_stats(records)
    model_summary = {}
    
    # --- SPC 全量散点矩阵核心逻辑 ---
    # 扫描获取所有的数值类测试项
    numeric_metrics = {}
    for record in records[:200]: 
        for item in record.get("raw_items", []):
            name = item.get("name") or item.get("raw_name")
            val_str = str(item.get("value", ""))
            try:
                # 判定是否为数值类型
                float(val_str)
                if name not in numeric_metrics:
                    numeric_metrics[name] = {
                        "name": name,
                        "count": 0,
                        "unit": item.get("unit", ""),
                        "hilim": item.get("hilim"),
                        "lolim": item.get("lolim")
                    }
                numeric_metrics[name]["count"] += 1
            except Exception:
                continue

    # 将有数据的测项全部返回 (解除数量限制)
    all_metrics = sorted(numeric_metrics.values(), key=lambda x: x["count"], reverse=True)
    
    spc_matrix_data = []
    for metric in all_metrics:
        points = []
        for record in reversed(records[:100]):
            target_item = next((i for i in record.get("raw_items", []) if (i.get("name") or i.get("raw_name")) == metric["name"]), None)
            if target_item:
                try:
                    points.append({
                        "time": record.get("time", "")[-8:], # 仅截取时分秒
                        "val": float(target_item.get("value")),
                        "sn": record.get("sn", "Unknown")
                    })
                except Exception:
                    continue
        
        # 只保留有有效数据点的测项
        if len(points) > 0:
            spc_matrix_data.append({
                "name": metric["name"],
                "unit": metric["unit"],
                "hilim": metric["hilim"],
                "lolim": metric["lolim"],
                "points": points
            })

    # 型号汇总统计
    for record in records:
        model = record.get("model") or "UNKNOWN"
        result = normalize_result(record.get("business_result") or record.get("result") or "中断")
        if model not in model_summary:
            model_summary[model] = {"PASS": 0, "FAIL": 0, "中断": 0, "total": 0}
        model_summary[model][result] += 1
        model_summary[model]["total"] += 1

    top_fail_items = get_top_fail_records(records, limit=20)
    station_risk = build_station_risk(records) if build_station_risk else []
    
    return {
        "stats": stats, 
        "top_fail_items": top_fail_items, 
        "model_summary": model_summary, 
        "station_risk": station_risk,
        "spc_matrix": spc_matrix_data # 全量矩阵数据返回
    }

@app.route("/")
@app.route("/dashboard")
@app.route("/analysis")
@app.route("/machine")
def index(): return render_template("index.html")

@app.route("/api/health")
def api_health(): return jsonify({"ok": True, "server_time": now_text(), "parser_loaded": load_all_fct_records is not None, "log_dir": LOG_DIR})

@app.route("/api/all")
def api_all(): return jsonify(safe_load_records())

@app.route("/api/recent")
def api_recent():
    limit = int(request.args.get("limit", "50"))
    return jsonify(safe_load_records()[:limit])

@app.route("/api/search")
def api_search():
    sn = request.args.get("sn", "")
    records = safe_load_records()
    record = find_latest_record_by_sn(records, sn) if find_latest_record_by_sn else None
    return jsonify({"ok": bool(record), "record": record, "message": "" if record else "未找到"})

@app.route("/api/record_detail")
def api_record_detail():
    records = safe_load_records()
    index = request.args.get("index", "")
    if index != "":
        try:
            return jsonify({"ok": True, "record": records[int(index)]})
        except: pass
    return jsonify({"ok": False, "message": "未找到记录"})

@app.route("/api/top_fail")
def api_top_fail(): return jsonify(get_top_fail_records(safe_load_records(), limit=int(request.args.get("limit", "10"))))

@app.route("/api/stats")
def api_stats(): return jsonify(build_stats(safe_load_records()))

@app.route("/api/analysis")
def api_analysis(): return jsonify(build_analysis(safe_load_records()))

@app.route("/api/telemetry/push", methods=["POST"])
def api_telemetry_push():
    data = normalize_machine_payload(request.get_json(silent=True))
    TELEMETRY_CACHE[data["machine_id"]] = data
    return jsonify({"ok": True})

@app.route("/api/telemetry/latest")
def api_telemetry_latest(): return jsonify(build_machine_summary())

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)