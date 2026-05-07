import os
from flask import Flask, render_template, jsonify

from parser.fct_parser import load_all_fct_xml


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "static")
LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")


app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "G4.9 FCT Dashboard backend is running",
        "log_dir": LOG_DIR
    })


@app.route("/api/sn/<sn>")
def query_sn(sn):
    sn = sn.strip()

    all_data = load_all_fct_xml(LOG_DIR)
    data = all_data.get(sn)

    if data is None:
        return jsonify({
            "sn": sn,
            "station": "FCT",
            "result": "NOT_FOUND",
            "fail_items": [],
            "raw_items": [],
            "message": "未找到该 SN 的 FCT XML 测试记录"
        }), 404

    return jsonify(data)


@app.route("/api/all")
def get_all():
    all_data = load_all_fct_xml(LOG_DIR)
    records = list(all_data.values())

    records.sort(
        key=lambda x: x.get("file_mtime_ts", 0),
        reverse=True
    )

    return jsonify(records)


@app.route("/api/recent_xml")
def recent_xml():
    all_data = load_all_fct_xml(LOG_DIR)
    records = list(all_data.values())

    records.sort(
        key=lambda x: x.get("file_mtime_ts", 0),
        reverse=True
    )

    latest_records = records[:20]

    return jsonify(latest_records)


@app.route("/api/stats")
def get_stats():
    all_data = load_all_fct_xml(LOG_DIR)

    total = len(all_data)
    pass_count = 0
    fail_count = 0
    parse_error_count = 0
    top_fail = {}

    for record in all_data.values():
        result = record.get("result", "")

        if result == "PASS":
            pass_count += 1
        elif result == "FAIL":
            fail_count += 1
        elif result == "PARSE_ERROR":
            parse_error_count += 1

        for fail_item in record.get("fail_items", []):
            top_fail[fail_item] = top_fail.get(fail_item, 0) + 1

    return jsonify({
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "parse_error": parse_error_count,
        "top_fail": top_fail
    })


if __name__ == "__main__":
    print("====================================")
    print("G4.9 FCT Dashboard backend starting")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Template dir: {TEMPLATE_DIR}")
    print(f"Static dir: {STATIC_DIR}")
    print(f"Log dir: {LOG_DIR}")
    print("Open: http://localhost:5000")
    print("Health: http://localhost:5000/api/health")
    print("====================================")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )