# -*- coding: utf-8 -*-
import os, re, sys, math, statistics
from datetime import datetime
from collections import defaultdict
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
if PROJECT_ROOT not in sys.path: sys.path.insert(0, PROJECT_ROOT)

LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")
TELEMETRY_CACHE = {}

app = Flask(__name__, template_folder=os.path.join(PROJECT_ROOT, "frontend", "templates"), static_folder=os.path.join(PROJECT_ROOT, "frontend", "static"))

try:
    from backend.parser.fct_parser import load_all_fct_records, find_latest_record_by_sn
except BaseException:
    load_all_fct_records = find_latest_record_by_sn = None

try:
    from backend.rules.station_risk_rules import build_station_risk
except BaseException:
    build_station_risk = None

def now_text(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def safe_load_records():
    if not load_all_fct_records: return []
    os.makedirs(LOG_DIR, exist_ok=True)
    try: return load_all_fct_records(LOG_DIR)
    except: return []

# ================= 计算核心 =================
def calculate_cpk(data_list, usl, lsl):
    if len(data_list) < 5: return 0.0 # 样本太少不计
    try:
        mu = statistics.mean(data_list)
        sigma = statistics.stdev(data_list)
        if sigma == 0: return 9.99
        cpu = (usl - mu) / (3 * sigma)
        cpl = (mu - lsl) / (3 * sigma)
        return round(max(0, min(cpu, cpl)), 2)
    except: return 0.0

@app.route("/")
@app.route("/dashboard")
def index(): return render_template("index.html")

@app.route("/api/analysis")
def api_analysis():
    records = safe_load_records()
    
    # 1. 基础良率与型号分布
    model_summary = defaultdict(lambda: {"PASS":0, "FAIL":0, "中断":0, "total":0})
    
    # 2. FPY 与复测分析
    sn_history = defaultdict(list)
    for r in sorted(records, key=lambda x: x.get("time", "")):
        sn_history[r.get("sn")].append(r.get("business_result"))
    
    fpy_pass = 0
    retest_total = 0
    for sn, results in sn_history.items():
        if results[0] == "PASS": fpy_pass += 1
        if len(results) > 1: retest_total += 1
    
    total_unique_sn = len(sn_history)
    fpy_rate = round((fpy_pass / total_unique_sn * 100), 2) if total_unique_sn > 0 else 0

    # 3. 故障柏拉图 (Pareto) 与 CPK 数据准备
    pareto_counter = defaultdict(int)
    cpk_raw_data = defaultdict(list)
    cpk_limits = {}
    
    # 4. Cycle Time 节拍分析
    ct_list = []

    for r in records:
        res = r.get("business_result", "中断")
        model = r.get("model", "Unknown")
        model_summary[model][res] += 1
        model_summary[model]["total"] += 1
        
        # 柏拉图
        for f in r.get("fail_items", []):
            if "Get Unit Information" not in f.get("name", ""):
                pareto_counter[f.get("name", "Unknown")] += 1
        
        # CPK 抽样 (仅记录 PASS 的数值)
        if res == "PASS":
            for item in r.get("raw_items", []):
                try:
                    val = float(item.get("value"))
                    if not (math.isnan(val) or math.isinf(val)):
                        name = item.get("name")
                        cpk_raw_data[name].append(val)
                        if name not in cpk_limits:
                            # 简单提取限值逻辑
                            lo = float(item.get("lolim", -999) or -999)
                            hi = float(item.get("hilim", 999) or 999)
                            cpk_limits[name] = (lo, hi)
                except: continue

    # 计算前 5 名 CPK 最危险的项
    cpk_results = []
    for name, vals in cpk_raw_data.items():
        if name in cpk_limits:
            lo, hi = cpk_limits[name]
            score = calculate_cpk(vals, hi, lo)
            if score > 0: cpk_results.append({"item": name, "cpk": score, "samples": len(vals)})
    cpk_results.sort(key=lambda x: x["cpk"])

    # 柏拉图排序
    pareto_list = [{"item": k, "count": v} for k, v in pareto_counter.items()]
    pareto_list.sort(key=lambda x: x["count"], reverse=True)

    try: risks = build_station_risk(records) if build_station_risk else []
    except: risks = []

    return jsonify({
        "model_summary": model_summary,
        "fpy_rate": fpy_rate,
        "retest_count": retest_total,
        "unique_sn": total_unique_sn,
        "pareto": pareto_list[:8],
        "cpk_top": cpk_results[:5],
        "station_risk": risks
    })

@app.route("/api/recent")
def api_recent():
    # 🌟 修改点：从 URL 获取 limit 参数，如果没有则默认返回 1000 条（确保覆盖你的 75 条）
    limit = request.args.get('limit', default=1000, type=int)
    records = safe_load_records()
    return jsonify(records[:limit])

@app.route("/api/stats")
def api_stats():
    records = safe_load_records()
    total = len(records)
    passes = sum(1 for r in records if r.get("business_result") == "PASS")
    fails = sum(1 for r in records if r.get("business_result") == "FAIL")
    return jsonify({"total": total, "pass": passes, "fail": fails, "interrupt": total - passes - fails})

@app.route("/api/upload_log", methods=["POST"])
def api_upload_log():
    file = request.files.get('file')
    m_id = request.form.get("machine_id", "Unknown")
    if not file: return jsonify({"ok": False}), 400
    save_dir = os.path.join(LOG_DIR, m_id, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(save_dir, exist_ok=True)
    file.save(os.path.join(save_dir, file.filename))
    return jsonify({"ok": True})

@app.route("/api/telemetry/push", methods=["POST"])
def api_telemetry_push():
    data = request.get_json() or {}
    m_id = data.get("machine_id", "Unknown")
    data["server_receive_time"] = now_text()
    TELEMETRY_CACHE[m_id] = data
    return jsonify({"ok": True})

@app.route("/api/telemetry/latest")
def api_telemetry_latest():
    machines = []
    for m_id, payload in TELEMETRY_CACHE.items():
        age = (datetime.now() - datetime.strptime(payload["server_receive_time"], "%Y-%m-%d %H:%M:%S")).total_seconds()
        status = "ONLINE" if age < 15 else ("STALE" if age < 60 else "OFFLINE")
        machines.append({
            "machine_id": m_id, "online_status": status, "ip": payload.get("ip", "-"),
            "display_state": payload.get("machine_state", "IDLE"), "current_sn": payload.get("current_sn", "-"),
            "measurements": payload.get("measurements", {})
        })
    return jsonify({"total": len(machines), "online": sum(1 for m in machines if m["online_status"]=="ONLINE"), "machines": machines})

@app.route("/api/trends")
def api_trends():
    records = safe_load_records()
    trends = {}
    for r in records:
        sn, t = r.get("sn"), r.get("time")
        for it in r.get("raw_items", []):
            try:
                val = float(it.get("value"))
                if math.isnan(val) or math.isinf(val): continue
                name = it.get("name")
                if name not in trends: trends[name] = {"limit": it.get("nominal_range"), "unit": it.get("unit"), "data": []}
                trends[name]["data"].append({"sn": sn, "time": t, "value": val, "status": it.get("business_status")})
            except: continue
    return jsonify({"trends": [{"name": k, **v} for k, v in trends.items()]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)