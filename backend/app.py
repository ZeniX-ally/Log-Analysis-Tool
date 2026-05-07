
import os
import re
import sys
from datetime import datetime
from flask import Flask, render_template, jsonify


# =========================================================
# 路径配置
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "static")
LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR
)


# =========================================================
# 时间解析与排序
# =========================================================

def parse_time_to_timestamp(time_text):
    if not time_text:
        return 0

    text = str(time_text).strip()

    if not text:
        return 0

    try:
        iso_text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_text)
        return dt.timestamp()
    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%dT%H:%M:%S"
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.timestamp()
        except Exception:
            continue

    return 0


def parse_filename_time_to_timestamp(source_file):
    if not source_file:
        return 0

    filename = os.path.basename(str(source_file))
    matches = re.findall(r"_(\d{17})_", filename)

    if not matches:
        return 0

    text = matches[0]

    try:
        dt = datetime.strptime(text[:14], "%Y%m%d%H%M%S")
        return dt.timestamp()
    except Exception:
        return 0


def get_record_sort_timestamp(record):
    time_fields = [
        record.get("time", ""),
        record.get("dut_time", ""),
        record.get("panel_time", ""),
        record.get("batch_time", "")
    ]

    for time_text in time_fields:
        ts = parse_time_to_timestamp(time_text)
        if ts > 0:
            return ts

    filename_ts = parse_filename_time_to_timestamp(record.get("source_file", ""))
    if filename_ts > 0:
        return filename_ts

    return record.get("file_mtime_ts", 0) or 0


def sort_records_latest_first(records):
    return sorted(
        records,
        key=lambda record: get_record_sort_timestamp(record),
        reverse=True
    )


# =========================================================
# Parser 加载
# =========================================================

def load_parser_function():
    try:
        from parser.fct_parser import load_all_fct_records
        return load_all_fct_records, None
    except Exception as e:
        return None, str(e)


def safe_load_records():
    load_all_fct_records, import_error = load_parser_function()

    if import_error:
        return [], "导入 fct_parser.py 失败：" + import_error

    try:
        records = load_all_fct_records(LOG_DIR)
        records = sort_records_latest_first(records)
        return records, None
    except Exception as e:
        return [], "解析 XML 失败：" + str(e)


# =========================================================
# SN 查询
# =========================================================

def find_latest_record_by_sn(records, query_sn):
    if not query_sn:
        return None

    query = str(query_sn).strip().upper()

    if not query:
        return None

    matched_records = []

    for record in records:
        sn = str(record.get("sn", "")).strip().upper()
        source_file = str(record.get("source_file", "")).strip().upper()

        aliases = [
            str(alias).strip().upper()
            for alias in record.get("sn_aliases", [])
            if alias
        ]

        if query == sn:
            matched_records.append(record)
            continue

        if query in aliases:
            matched_records.append(record)
            continue

        if sn and sn.endswith(query):
            matched_records.append(record)
            continue

        if source_file and query in source_file:
            matched_records.append(record)
            continue

    if not matched_records:
        return None

    matched_records = sort_records_latest_first(matched_records)
    return matched_records[0]


# =========================================================
# 页面路由
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


# =========================================================
# API：健康检查
# =========================================================

@app.route("/api/health")
def health():
    load_all_fct_records, import_error = load_parser_function()

    parser_status = "ok"
    if import_error:
        parser_status = "error"

    return jsonify({
        "status": "ok",
        "message": "G4.9 FCT Dashboard backend is running",
        "project_root": PROJECT_ROOT,
        "template_dir": TEMPLATE_DIR,
        "static_dir": STATIC_DIR,
        "log_dir": LOG_DIR,
        "parser_status": parser_status,
        "parser_error": import_error
    })


# =========================================================
# API：SN 查询
# =========================================================

@app.route("/api/sn/<sn>")
def query_sn(sn):
    records, error = safe_load_records()

    if error:
        return jsonify({
            "sn": sn,
            "station": "FCT",
            "result": "PARSE_ERROR",
            "fail_items": [],
            "paused_items": [],
            "interrupted_items": [],
            "error_items": [],
            "failed_groups": [],
            "paused_groups": [],
            "interrupted_groups": [],
            "error_groups": [],
            "raw_items": [],
            "message": error
        }), 500

    data = find_latest_record_by_sn(records, sn)

    if data is None:
        return jsonify({
            "sn": sn,
            "station": "FCT",
            "result": "NOT_FOUND",
            "fail_items": [],
            "paused_items": [],
            "interrupted_items": [],
            "error_items": [],
            "failed_groups": [],
            "paused_groups": [],
            "interrupted_groups": [],
            "error_groups": [],
            "raw_items": [],
            "message": "未找到该 SN 的 FCT XML 测试记录。支持完整 SN、SN 后 8/10/12 位、或文件名片段查询。"
        }), 404

    return jsonify(data)


# =========================================================
# API：全部记录
# =========================================================

@app.route("/api/all")
def get_all():
    records, error = safe_load_records()

    if error:
        return jsonify([])

    return jsonify(records)


# =========================================================
# API：统计
# =========================================================

@app.route("/api/stats")
def get_stats():
    records, error = safe_load_records()

    if error:
        return jsonify({
            "total": 0,
            "pass": 0,
            "fail": 0,
            "paused": 0,
            "interrupted": 0,
            "error": 0,
            "parse_error": 1,
            "unknown": 0,
            "top_fail": {},
            "top_paused": {},
            "top_interrupted": {},
            "top_error": {},
            "message": error
        })

    total = len(records)

    pass_count = 0
    fail_count = 0
    paused_count = 0
    interrupted_count = 0
    error_count = 0
    parse_error_count = 0
    unknown_count = 0

    top_fail = {}
    top_paused = {}
    top_interrupted = {}
    top_error = {}

    for record in records:
        result = record.get("result", "")

        if result == "PASS":
            pass_count += 1
        elif result == "FAIL":
            fail_count += 1
        elif result == "PAUSED":
            paused_count += 1
        elif result == "INTERRUPTED":
            interrupted_count += 1
        elif result == "ERROR":
            error_count += 1
        elif result == "PARSE_ERROR":
            parse_error_count += 1
        else:
            unknown_count += 1

        for item in record.get("fail_items", []):
            top_fail[item] = top_fail.get(item, 0) + 1

        for item in record.get("paused_items", []):
            top_paused[item] = top_paused.get(item, 0) + 1

        for item in record.get("interrupted_items", []):
            top_interrupted[item] = top_interrupted.get(item, 0) + 1

        for item in record.get("error_items", []):
            top_error[item] = top_error.get(item, 0) + 1

    sorted_top_fail = dict(sorted(top_fail.items(), key=lambda item: item[1], reverse=True))
    sorted_top_paused = dict(sorted(top_paused.items(), key=lambda item: item[1], reverse=True))
    sorted_top_interrupted = dict(sorted(top_interrupted.items(), key=lambda item: item[1], reverse=True))
    sorted_top_error = dict(sorted(top_error.items(), key=lambda item: item[1], reverse=True))

    return jsonify({
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "paused": paused_count,
        "interrupted": interrupted_count,
        "error": error_count,
        "parse_error": parse_error_count,
        "unknown": unknown_count,
        "top_fail": sorted_top_fail,
        "top_paused": sorted_top_paused,
        "top_interrupted": sorted_top_interrupted,
        "top_error": sorted_top_error
    })


# =========================================================
# API：调试
# =========================================================

@app.route("/api/debug/files")
def debug_files():
    records, error = safe_load_records()

    if error:
        return jsonify({
            "error": error,
            "records": []
        }), 500

    simple_records = []

    for record in records:
        simple_records.append({
            "sn": record.get("sn", ""),
            "aliases": record.get("sn_aliases", []),
            "station": record.get("station", ""),
            "tester": record.get("tester", ""),
            "product": record.get("product", ""),
            "result": record.get("result", ""),
            "panel_status": record.get("panel_status", ""),
            "panel_status_raw": record.get("panel_status_raw", ""),
            "dut_status": record.get("dut_status", ""),
            "dut_status_raw": record.get("dut_status_raw", ""),
            "source_file": record.get("source_file", ""),
            "time": record.get("time", ""),
            "dut_time": record.get("dut_time", ""),
            "panel_time": record.get("panel_time", ""),
            "batch_time": record.get("batch_time", ""),
            "file_mtime": record.get("file_mtime", ""),
            "file_mtime_ts": record.get("file_mtime_ts", 0),
            "filename_sort_ts": parse_filename_time_to_timestamp(record.get("source_file", "")),
            "final_sort_ts": get_record_sort_timestamp(record),
            "total_tests": record.get("total_tests", 0),
            "failed_tests": record.get("failed_tests", 0),
            "passed_tests": record.get("passed_tests", 0),
            "paused_tests": record.get("paused_tests", 0),
            "interrupted_tests": record.get("interrupted_tests", 0),
            "error_tests": record.get("error_tests", 0),
            "skipped_tests": record.get("skipped_tests", 0),
            "fail_items": record.get("fail_items", []),
            "paused_items": record.get("paused_items", []),
            "interrupted_items": record.get("interrupted_items", []),
            "error_items": record.get("error_items", []),
            "failed_groups": record.get("failed_groups", []),
            "paused_groups": record.get("paused_groups", []),
            "interrupted_groups": record.get("interrupted_groups", []),
            "error_groups": record.get("error_groups", [])
        })

    return jsonify(simple_records)


# =========================================================
# 启动入口
# =========================================================

if __name__ == "__main__":
    print("====================================")
    print("G4.9 FCT Dashboard backend starting")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Template dir: {TEMPLATE_DIR}")
    print(f"Static dir: {STATIC_DIR}")
    print(f"Log dir: {LOG_DIR}")
    print("Open: http://localhost:5000")
    print("Health: http://localhost:5000/api/health")
    print("Debug: http://localhost:5000/api/debug/files")
    print("====================================")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
from flask import Flask, render_template, jsonify


# =========================================================
# 路径配置
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

