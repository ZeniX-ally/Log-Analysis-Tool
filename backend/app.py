import os
import sys
from datetime import datetime
from flask import Flask, jsonify, request, render_template

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.parser.fct_parser import scan_xml_files, search_by_sn, get_record_by_file_path
from backend.rules.fail_rules import build_analysis, get_top_fail
from backend.rules.station_risk_rules import analyze_station_risk
from backend.models.data_model import MachineStatus


TEMPLATE_DIR = os.path.join(BASE_DIR, "frontend", "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)

machine_store = {}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("index.html")


@app.route("/analysis")
def analysis_page():
    return render_template("index.html")


@app.route("/machine")
def machine_page():
    return render_template("index.html")


@app.route("/api/recent")
def api_recent():
    limit = request.args.get("limit", default=100, type=int)
    records = scan_xml_files(limit=limit)

    return jsonify([
        record.to_dict(include_items=False)
        for record in records
    ])


@app.route("/api/search")
def api_search():
    sn = request.args.get("sn", "").strip()

    if not sn:
        return jsonify({
            "success": False,
            "message": "SN is required",
            "data": None,
        })

    record = search_by_sn(sn)

    if not record:
        return jsonify({
            "success": False,
            "message": "SN not found",
            "data": None,
        })

    return jsonify({
        "success": True,
        "message": "OK",
        "data": record.to_dict(include_items=True),
    })


@app.route("/api/record_detail")
def api_record_detail():
    file_path = request.args.get("file_path", "").strip()

    if not file_path:
        return jsonify({
            "success": False,
            "message": "file_path is required",
            "data": None,
        })

    record = get_record_by_file_path(file_path)

    if not record:
        return jsonify({
            "success": False,
            "message": "record not found or file path is not allowed",
            "data": None,
        })

    return jsonify({
        "success": True,
        "message": "OK",
        "data": record.to_dict(include_items=True),
    })


@app.route("/api/top_fail")
def api_top_fail():
    records = scan_xml_files(limit=1000)
    return jsonify(get_top_fail(records))


@app.route("/api/analysis")
def api_analysis():
    records = scan_xml_files(limit=3000)
    return jsonify(build_analysis(records))


@app.route("/api/station_risk")
def api_station_risk():
    limit = request.args.get("limit", default=1000, type=int)
    window_minutes = request.args.get("window_minutes", default=30, type=int)
    min_fail_count = request.args.get("min_fail_count", default=3, type=int)
    min_sn_count = request.args.get("min_sn_count", default=3, type=int)

    records = scan_xml_files(limit=limit)

    risks = analyze_station_risk(
        records=records,
        window_minutes=window_minutes,
        min_fail_count=min_fail_count,
        min_sn_count=min_sn_count,
    )

    return jsonify(risks)


@app.route("/api/machine/status", methods=["POST"])
def api_machine_status_post():
    payload = request.get_json(silent=True) or {}

    machine_id = str(payload.get("machine_id", "UNKNOWN"))
    online = bool(payload.get("online", True))
    voltage = float(payload.get("voltage", 0))
    current = float(payload.get("current", 0))
    temperature = float(payload.get("temperature", 0))
    status = str(payload.get("status", "UNKNOWN"))

    data = MachineStatus(
        machine_id=machine_id,
        online=online,
        voltage=voltage,
        current=current,
        temperature=temperature,
        status=status,
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    machine_store[machine_id] = data.to_dict()

    return jsonify({
        "success": True,
        "message": "Machine status updated",
        "data": data.to_dict(),
    })


@app.route("/api/machine/status", methods=["GET"])
def api_machine_status_get():
    return jsonify(list(machine_store.values()))


@app.route("/api/health")
def api_health():
    return jsonify({
        "success": True,
        "message": "Server is running",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


if __name__ == "__main__":
    print("========================================")
    print("LOG Analysis Tool starting...")
    print(f"Project root : {BASE_DIR}")
    print(f"Template dir : {TEMPLATE_DIR}")
    print("Server URL   : http://127.0.0.1:5000")
    print("========================================")

    app.run(host="0.0.0.0", port=5000, debug=True)