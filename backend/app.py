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
        compact = ""
        for ch in text:
            if ch.isdigit():
                compact += ch

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
        return [
            {
                "sn": "",
                "sn_aliases": [],
                "model": "UNKNOWN",
                "test_mode": "Unknown",
                "date_folder": "",
                "relative_path": "",
                "station": "FCT",
                "tester": "",
                "product": "",
                "result": "中断",
                "business_result": "中断",
                "raw_result": "LOAD_ERROR",
                "panel_status": "中断",
                "panel_status_raw": "",
                "dut_status": "中断",
                "dut_status_raw": "",
                "fail_items": [],
                "interrupted_items": [],
                "raw_items": [],
                "time": now_text(),
                "batch_time": "",
                "panel_time": "",
                "dut_time": "",
                "test_time": now_text(),
                "source_file": "",
                "source_path": "",
                "file_mtime": "",
                "file_mtime_ts": 0.0,
                "total_tests": 0,
                "failed_tests": 0,
                "passed_tests": 0,
                "interrupted_tests": 0,
                "skipped_tests": 0,
                "parse_error": str(exc),
            }
        ]


def normalize_result(result):
    raw = str(result or "").strip()

    if raw == "中断":
        return "中断"

    text = raw.upper()

    if text in ["PASS", "PASSED", "OK", "SUCCESS", "TRUE"]:
        return "PASS"

    if text in ["FAIL", "FAILED", "NG", "FALSE"]:
        return "FAIL"

    return "中断"


def fallback_build_top_fail(records, limit=10):
    counter = {}

    for record in records:
        fail_items = record.get("fail_items", []) or []

        for item in fail_items:
            name = item.get("name") or item.get("raw_name") or item.get("item") or "-"

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

        result.append(
            {
                "item": item["item"],
                "count": count,
                "models": sorted(list(item["models"])),
                "modes": sorted(list(item["modes"])),
                "stations": sorted(list(item["stations"])),
                "latest_time": item["latest_time"],
                "warning_level": level,
            }
        )

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

    fail_rate = 0
    interrupt_rate = 0

    if total > 0:
        fail_rate = round(fail_count / total * 100, 2)
        interrupt_rate = round(interrupt_count / total * 100, 2)

    return {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "interrupt": interrupt_count,
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

    if age <= ONLINE_SECONDS:
        return "ONLINE"

    if age <= STALE_SECONDS:
        return "STALE"

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

    if isinstance(alarms, list):
        alarm_count = len(alarms)
    else:
        alarm_count = 1

    if online_status == "OFFLINE":
        display_state = "OFFLINE"
    elif online_status == "STALE":
        display_state = "STALE"
    elif alarm_count > 0 or len(offline_instruments) > 0:
        display_state = "WARNING"
    else:
        display_state = payload.get("machine_state", "IDLE")

    return {
        "machine_id": payload.get("machine_id", ""),
        "station": payload.get("station", ""),
        "line": payload.get("line", ""),
        "host_name": payload.get("host_name", ""),
        "ip": payload.get("ip", ""),
        "model": payload.get("model", ""),
        "test_mode": payload.get("test_mode", ""),
        "timestamp": payload.get("timestamp", ""),
        "server_receive_time": payload.get("server_receive_time", ""),
        "online_status": online_status,
        "machine_state": payload.get("machine_state", ""),
        "display_state": display_state,
        "current_sn": payload.get("current_sn", ""),
        "current_step": payload.get("current_step", ""),
        "measurements": payload.get("measurements", {}),
        "instruments": payload.get("instruments", {}),
        "communication": payload.get("communication", {}),
        "alarms": alarms,
        "offline_instruments": offline_instruments,
        "alarm_count": alarm_count,
    }


def build_machine_summary():
    machines = []

    for machine_id in TELEMETRY_CACHE:
        machines.append(summarize_machine(TELEMETRY_CACHE[machine_id]))

    total = len(machines)
    online = 0
    stale = 0
    offline = 0
    alarm_machines = 0
    offline_instruments = 0

    for machine in machines:
        if machine.get("online_status") == "ONLINE":
            online += 1
        elif machine.get("online_status") == "STALE":
            stale += 1
        elif machine.get("online_status") == "OFFLINE":
            offline += 1

        if machine.get("alarm_count", 0) > 0:
            alarm_machines += 1

        offline_instruments += len(machine.get("offline_instruments", []))

    machines.sort(key=lambda item: item.get("machine_id", ""))

    return {
        "total": total,
        "online": online,
        "stale": stale,
        "offline": offline,
        "alarm_machines": alarm_machines,
        "offline_instruments": offline_instruments,
        "machines": machines,
        "server_time": now_text(),
    }


def build_analysis(records):
    stats = build_stats(records)
    model_summary = {}
    scatter_points = []

    for record in records:
        model = record.get("model") or "UNKNOWN"
        result = record.get("business_result") or record.get("result") or "中断"
        result = normalize_result(result)

        if model not in model_summary:
            model_summary[model] = {
                "PASS": 0,
                "FAIL": 0,
                "中断": 0,
                "total": 0,
            }

        model_summary[model][result] += 1
        model_summary[model]["total"] += 1

        if result != "PASS":
            fail_items = record.get("fail_items", []) or []
            item_name = result

            if fail_items:
                item_name = fail_items[0].get("name") or fail_items[0].get("raw_name") or result

            scatter_points.append(
                {
                    "time": record.get("time", ""),
                    "item": item_name,
                    "model": model,
                    "mode": record.get("test_mode", ""),
                    "station": record.get("station", ""),
                    "machine": record.get("tester", ""),
                    "result": result,
                    "sn": record.get("sn", ""),
                }
            )

    top_fail_items = get_top_fail_records(records, limit=20)

    if build_station_risk:
        try:
            station_risk = build_station_risk(records)
        except Exception:
            station_risk = []
    else:
        station_risk = []

    return {
        "stats": stats,
        "top_fail_items": top_fail_items,
        "scatter_points": scatter_points[:300],
        "model_summary": model_summary,
        "station_risk": station_risk,
        "machine_latest": build_machine_summary(),
        "server_time": now_text(),
    }


@app.route("/")
@app.route("/dashboard")
@app.route("/analysis")
@app.route("/machine")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    return jsonify(
        {
            "ok": True,
            "server_time": now_text(),
            "project_root": PROJECT_ROOT,
            "log_dir": LOG_DIR,
            "log_dir_exists": os.path.isdir(LOG_DIR),
            "template_dir": TEMPLATE_DIR,
            "parser_loaded": load_all_fct_records is not None,
            "parser_import_error": PARSER_IMPORT_ERROR,
            "telemetry_machine_count": len(TELEMETRY_CACHE),
            "business_status": ["PASS", "FAIL", "中断"],
        }
    )


@app.route("/api/all")
def api_all():
    records = safe_load_records()
    return jsonify(records)


@app.route("/api/recent")
def api_recent():
    limit = request.args.get("limit", "50")

    try:
        limit = int(limit)
    except Exception:
        limit = 50

    records = safe_load_records()
    return jsonify(records[:limit])


@app.route("/api/search")
def api_search():
    sn = request.args.get("sn", "")
    records = safe_load_records()

    if find_latest_record_by_sn:
        record = find_latest_record_by_sn(records, sn)
    else:
        record = None

    return jsonify(
        {
            "ok": bool(record),
            "query": sn,
            "record": record,
            "message": "" if record else "未找到匹配 SN",
        }
    )


@app.route("/api/sn/<sn>")
def api_sn(sn):
    records = safe_load_records()

    if find_latest_record_by_sn:
        record = find_latest_record_by_sn(records, sn)
    else:
        record = None

    return jsonify(
        {
            "ok": bool(record),
            "query": sn,
            "record": record,
            "message": "" if record else "未找到匹配 SN",
        }
    )


@app.route("/api/record_detail")
def api_record_detail():
    records = safe_load_records()

    file_path = request.args.get("file_path", "")
    path = request.args.get("path", "")
    file_name = request.args.get("file", "")
    source_file = request.args.get("source_file", "")
    relative_path = request.args.get("relative_path", "")
    sn = request.args.get("sn", "")
    index = request.args.get("index", "")

    query = file_path or path or file_name or source_file or relative_path or sn

    if index != "":
        try:
            index_value = int(index)
            if 0 <= index_value < len(records):
                return jsonify({"ok": True, "record": records[index_value]})
        except Exception:
            pass

    query = str(query or "").strip()

    if not query:
        return jsonify({"ok": False, "message": "未收到记录标识"}), 400

    def norm(value):
        text = str(value or "").strip()
        text = text.replace("\\", "/")
        text = text.replace("%5C", "/")
        text = text.replace("%2F", "/")
        text = text.lower()
        return text

    query_norm = norm(query)

    for record in records:
        candidates = [
            record.get("source_path", ""),
            record.get("source_file", ""),
            record.get("relative_path", ""),
            record.get("sn", ""),
        ]

        aliases = record.get("sn_aliases", []) or []
        for alias in aliases:
            candidates.append(alias)

        for candidate in candidates:
            candidate_norm = norm(candidate)

            if not candidate_norm:
                continue

            if query_norm == candidate_norm:
                return jsonify({"ok": True, "record": record})

    for record in records:
        candidates = [
            record.get("source_path", ""),
            record.get("source_file", ""),
            record.get("relative_path", ""),
            record.get("sn", ""),
        ]

        aliases = record.get("sn_aliases", []) or []
        for alias in aliases:
            candidates.append(alias)

        for candidate in candidates:
            candidate_norm = norm(candidate)

            if not candidate_norm:
                continue

            if query_norm in candidate_norm or candidate_norm in query_norm:
                return jsonify({"ok": True, "record": record})

    return jsonify(
        {
            "ok": False,
            "message": "未找到记录",
            "query": query,
            "record_count": len(records),
        }
    ), 404


@app.route("/api/top_fail")
def api_top_fail():
    limit = request.args.get("limit", "10")

    try:
        limit = int(limit)
    except Exception:
        limit = 10

    records = safe_load_records()
    data = get_top_fail_records(records, limit=limit)
    return jsonify(data)


@app.route("/api/stats")
def api_stats():
    records = safe_load_records()
    return jsonify(build_stats(records))


@app.route("/api/debug/files")
def api_debug_files():
    records = safe_load_records()

    simple = []

    for record in records[:100]:
        simple.append(
            {
                "sn": record.get("sn"),
                "model": record.get("model"),
                "mode": record.get("test_mode"),
                "result": record.get("business_result"),
                "raw_result": record.get("raw_result"),
                "time": record.get("time"),
                "file": record.get("source_file"),
                "relative_path": record.get("relative_path"),
                "source_path": record.get("source_path"),
                "total_tests": record.get("total_tests"),
                "passed_tests": record.get("passed_tests"),
                "failed_tests": record.get("failed_tests"),
                "interrupted_tests": record.get("interrupted_tests"),
                "parse_error": record.get("parse_error"),
            }
        )

    return jsonify(
        {
            "ok": True,
            "log_dir": LOG_DIR,
            "count": len(records),
            "records": simple,
        }
    )


@app.route("/api/analysis")
def api_analysis():
    records = safe_load_records()
    return jsonify(build_analysis(records))


@app.route("/api/station_risk")
def api_station_risk():
    records = safe_load_records()

    try:
        window = int(request.args.get("window", 30))
    except Exception:
        window = 30

    try:
        min_fail = int(request.args.get("min_fail", 3))
    except Exception:
        min_fail = 3

    try:
        min_sn = int(request.args.get("min_sn", 3))
    except Exception:
        min_sn = 3

    if build_station_risk:
        try:
            risks = build_station_risk(
                records,
                window_minutes=window,
                min_fail_count=min_fail,
                min_sn_count=min_sn,
            )
        except Exception:
            risks = []
    else:
        risks = []

    return jsonify(risks)


@app.route("/api/telemetry/push", methods=["POST"])
def api_telemetry_push():
    payload = request.get_json(silent=True) or {}
    data = normalize_machine_payload(payload)

    machine_id = data["machine_id"]
    TELEMETRY_CACHE[machine_id] = data

    if machine_id not in TELEMETRY_HISTORY:
        TELEMETRY_HISTORY[machine_id] = []

    TELEMETRY_HISTORY[machine_id].append(data)
    TELEMETRY_HISTORY[machine_id] = TELEMETRY_HISTORY[machine_id][-MAX_HISTORY_PER_MACHINE:]

    return jsonify(
        {
            "ok": True,
            "message": "telemetry received",
            "machine_id": machine_id,
            "server_time": now_text(),
        }
    )


@app.route("/api/telemetry/latest")
def api_telemetry_latest():
    return jsonify(build_machine_summary())


@app.route("/api/telemetry/machine/<machine_id>")
def api_telemetry_machine(machine_id):
    payload = TELEMETRY_CACHE.get(machine_id)

    if not payload:
        return jsonify({"ok": False, "message": "machine not found"}), 404

    return jsonify(
        {
            "ok": True,
            "machine": summarize_machine(payload),
            "history": TELEMETRY_HISTORY.get(machine_id, [])[-100:],
        }
    )


@app.route("/api/machines")
def api_machines():
    return jsonify(build_machine_summary())


@app.route("/api/machine/status", methods=["GET", "POST"])
def api_machine_status_compat():
    if request.method == "POST":
        return api_telemetry_push()

    return api_telemetry_latest()


if __name__ == "__main__":
    os.makedirs(LOG_DIR, exist_ok=True)

    print("=" * 80)
    print("G4.9 FCT XML Dashboard / FCT Monitor")
    print("PROJECT_ROOT:", PROJECT_ROOT)
    print("LOG_DIR     :", LOG_DIR)
    print("TEMPLATE_DIR:", TEMPLATE_DIR)
    print("URL         : http://127.0.0.1:5000/")
    print("=" * 80)

    app.run(host="0.0.0.0", port=5000, debug=True)