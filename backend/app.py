# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import math
from datetime import datetime
import functools # [优化点新增]
import time # [优化点新增]
from pathlib import Path # [新增] 用于跨平台路径处理

try:
    from flask import Flask, jsonify, render_template, request, Response
except ImportError as exc:
    raise ImportError(
        "Flask is required to run this application. Install it with 'pip install Flask'."
    ) from exc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# [修改点] 适配 Ubuntu 路径逻辑
_P = Path(PROJECT_ROOT)
TEMPLATE_DIR = str(_P / "frontend" / "templates")
STATIC_DIR = str(_P / "frontend" / "static")
LOG_DIR = str(_P / "data" / "logs")
CACHE_FILE = str(_P / "data" / "telemetry_cache.json")

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

# [优化点 3] 覆盖 Flask 原生的 jsonify 行为，使用紧凑型序列化，减少网络 I/O 体积
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False 

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


# ==============================
# [优化点 1 核心] 目录状态缓存控制
# ==============================
def get_dir_mtime(path):
    """获取目录的最后修改时间（秒级时间戳），用于判断是否有新日志文件产生"""
    try:
        return os.stat(path).st_mtime
    except Exception:
        return time.time()

# 使用 lru_cache 缓存解析结果。
@functools.lru_cache(maxsize=1)
def _cached_load_records(dir_mtime):
    if load_all_fct_records is None:
        return []
    try:
        records = load_all_fct_records(LOG_DIR)
        return sort_records_latest_first(records)
    except Exception as exc:
        print(f"Error loading records: {exc}")
        return []

def safe_load_records():
    """代理函数，将目录状态传入缓存系统"""
    os.makedirs(LOG_DIR, exist_ok=True)
    current_mtime = get_dir_mtime(LOG_DIR)
    return _cached_load_records(current_mtime)
# ==============================


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
        level = "HIGH" if count >= 5 else "MEDIUM" if count >= 3 else "LOW"
        
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
            if isinstance(data, list): return data
        except Exception: pass
    return fallback_build_top_fail(records, limit=limit)

def build_stats(records):
    total = len(records)
    pass_count = sum(1 for r in records if normalize_result(r.get("business_result") or r.get("result")) == "PASS")
    fail_count = sum(1 for r in records if normalize_result(r.get("business_result") or r.get("result")) == "FAIL")
    interrupt_count = total - pass_count - fail_count

    return {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "interrupt": interrupt_count,
        "fpy": round(pass_count / total * 100, 2) if total > 0 else 0,
        "fail_rate": round(fail_count / total * 100, 2) if total > 0 else 0,
        "interrupt_rate": round(interrupt_count / total * 100, 2) if total > 0 else 0,
        "top_fail": get_top_fail_records(records, limit=10),
        "log_dir": LOG_DIR,
    }

def normalize_machine_payload(payload):
    data = dict(payload or {})
    data["machine_id"] = str(data.get("machine_id") or "UNKNOWN_MACHINE")
    data["timestamp"] = data.get("timestamp") or now_text()
    data["server_receive_time"] = now_text()
    data.setdefault("station", "FCT")
    data.setdefault("machine_state", "IDLE")
    data.setdefault("current_step", "")
    data.setdefault("instruments", {})
    data.setdefault("measurements", {})
    data.setdefault("alarms", [])
    return data

def get_machine_online_status(payload):
    age = seconds_since(payload.get("server_receive_time") or payload.get("timestamp") or "")
    if age <= ONLINE_SECONDS: return "ONLINE"
    if age <= STALE_SECONDS: return "STALE"
    return "OFFLINE"

def summarize_machine(payload):
    online_status = get_machine_online_status(payload)
    alarms = payload.get("alarms") or []
    alarm_count = len(alarms) if isinstance(alarms, list) else 1
    display_state = "WARNING" if alarm_count > 0 else payload.get("machine_state", "IDLE")
    if online_status != "ONLINE": display_state = online_status

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
    return {"total": len(machines), "online": online, "stale": stale, "offline": offline, "machines": sorted(machines, key=lambda i: i["machine_id"])}

def build_analysis(records):
    recent_records = records[:2000]
    stats = build_stats(recent_records)
    model_summary = {}
    numeric_metrics = {}
    
    for record in recent_records[:200]: 
        for item in record.get("raw_items", []):
            name = item.get("name") or item.get("raw_name")
            val_str = str(item.get("value", ""))
            try:
                float(val_str)
                if name not in numeric_metrics:
                    numeric_metrics[name] = {"name": name, "count": 0, "unit": item.get("unit", ""), "hilim": item.get("hilim"), "lolim": item.get("lolim")}
                numeric_metrics[name]["count"] += 1
            except Exception: continue

    all_metrics = sorted(numeric_metrics.values(), key=lambda x: x["count"], reverse=True)[:30]
    spc_matrix_data = []
    
    for metric in all_metrics:
        points = []
        for record in reversed(recent_records[:100]):
            target_item = next((i for i in record.get("raw_items", []) if (i.get("name") or i.get("raw_name")) == metric["name"]), None)
            if target_item:
                try: points.append({"time": record.get("time", "")[-8:], "val": float(target_item.get("value")), "sn": record.get("sn", "Unknown")})
                except: continue
        if len(points) > 0:
            spc_matrix_data.append({"name": metric["name"], "unit": metric["unit"], "hilim": metric["hilim"], "lolim": metric["lolim"], "points": points})

    for record in recent_records:
        model = record.get("model") or "UNKNOWN"
        result = normalize_result(record.get("business_result") or record.get("result") or "中断")
        if model not in model_summary:
            model_summary[model] = {"PASS": 0, "FAIL": 0, "中断": 0, "total": 0}
        model_summary[model][result] += 1
        model_summary[model]["total"] += 1

    return {"stats": stats, "top_fail_items": get_top_fail_records(recent_records, limit=20), "model_summary": model_summary, "spc_matrix": spc_matrix_data}

def build_engineering_insights(records):
    insights = {
        "consecutive_fails": [],
        "cpk_warnings": []
    }
    
    station_history = {}
    for record in records[:100]:
        station = record.get("station", "UNKNOWN_STATION")
        if station not in station_history:
            station_history[station] = []
        station_history[station].append(record)

    for station, history in station_history.items():
        recent_3 = history[:3]
        if len(recent_3) == 3 and all(normalize_result(r.get("business_result") or r.get("result")) == "FAIL" for r in recent_3):
            fail_sets = [set((i.get("name") or i.get("raw_name")) for i in r.get("fail_items", [])) for r in recent_3]
            common_fails = set.intersection(*fail_sets) if fail_sets else set()
            if common_fails:
                insights["consecutive_fails"].append({
                    "station": station,
                    "consecutive_count": 3,
                    "common_fail_items": list(common_fails),
                    "action": "HALT_RECOMMENDED",
                    "reason": "检测到同一机台相同测项连续3次FAIL，存在极高治具探针损坏或线缆接触不良风险。"
                })

    metrics_data = {}
    pass_records = [r for r in records[:200] if normalize_result(r.get("business_result") or r.get("result")) == "PASS"]
    
    for record in pass_records:
        for item in record.get("raw_items", []):
            name = item.get("name") or item.get("raw_name")
            val_str = str(item.get("value", ""))
            hilim_str = str(item.get("hilim", ""))
            lolim_str = str(item.get("lolim", ""))
            
            try:
                val = float(val_str)
                hi = float(hilim_str) if hilim_str else None
                lo = float(lolim_str) if lolim_str else None
                
                if hi is not None and lo is not None and hi > lo:
                    if name not in metrics_data:
                        metrics_data[name] = {"values": [], "hi": hi, "lo": lo}
                    metrics_data[name]["values"].append(val)
            except Exception:
                continue

    for name, data in metrics_data.items():
        vals = data["values"]
        if len(vals) >= 10:
            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
            std_dev = math.sqrt(variance)
            
            if std_dev > 0:
                cpu = (data["hi"] - mean) / (3 * std_dev)
                cpl = (mean - data["lo"]) / (3 * std_dev)
                cpk = min(cpu, cpl)
                
                if cpk < 1.33:
                    insights["cpk_warnings"].append({
                        "item": name,
                        "sample_size": len(vals),
                        "cpk": round(cpk, 3),
                        "mean": round(mean, 4),
                        "std_dev": round(std_dev, 4),
                        "risk_level": "CRITICAL" if cpk < 1.0 else "WARNING"
                    })
                    
    insights["cpk_warnings"].sort(key=lambda x: x["cpk"])
    return insights

def load_telemetry_cache():
    global TELEMETRY_CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f: TELEMETRY_CACHE = json.load(f)
        except Exception: TELEMETRY_CACHE = {}

def save_telemetry_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f: json.dump(TELEMETRY_CACHE, f, ensure_ascii=False)
    except Exception: pass

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
def api_recent(): return jsonify(safe_load_records()[:int(request.args.get("limit", "50"))])

@app.route("/api/search")
def api_search():
    sn = request.args.get("sn", "")
    record = find_latest_record_by_sn(safe_load_records(), sn) if find_latest_record_by_sn else None
    return jsonify({"ok": bool(record), "record": record, "message": "" if record else "未找到"})

@app.route("/api/record_detail")
def api_record_detail():
    index = request.args.get("index", "")
    if index != "":
        try: return jsonify({"ok": True, "record": safe_load_records()[int(index)]})
        except: pass
    return jsonify({"ok": False, "message": "未找到记录"})

@app.route("/api/top_fail")
def api_top_fail(): return jsonify(get_top_fail_records(safe_load_records(), limit=int(request.args.get("limit", "10"))))

@app.route("/api/stats")
def api_stats(): return jsonify(build_stats(safe_load_records()))

@app.route("/api/analysis")
def api_analysis(): return jsonify(build_analysis(safe_load_records()))

@app.route("/api/engineering_insights")
def api_engineering_insights():
    return jsonify(build_engineering_insights(safe_load_records()))

@app.route("/api/telemetry/push", methods=["POST"])
def api_telemetry_push():
    data = normalize_machine_payload(request.get_json(silent=True))
    TELEMETRY_CACHE[data["machine_id"]] = data
    save_telemetry_cache()
    return jsonify({"ok": True})

@app.route("/api/telemetry/latest")
def api_telemetry_latest(): return jsonify(build_machine_summary())

if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)
    load_telemetry_cache()
    # [修改点] 开启多线程并关闭调试模式，优化 Ubuntu 服务器响应性
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)