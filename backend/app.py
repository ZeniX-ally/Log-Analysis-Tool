import os
from flask import Flask, render_template, jsonify


# 获取当前 app.py 所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 项目根目录：Log-Analysis-Tool
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# 前端模板目录：frontend/templates
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "frontend", "templates")

# 前端静态资源目录：frontend/static
STATIC_DIR = os.path.join(PROJECT_ROOT, "frontend", "static")


app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR
)


# =========================================================
# 临时模拟数据
# 后面我们会把这里替换成 XML / TDMS 解析后的真实数据
# =========================================================
MOCK_FCT_DATA = {
    "G49-001": {
        "sn": "G49-001",
        "station": "FCT",
        "result": "FAIL",
        "fail_items": [
            "CAN_Comm",
            "VoltageTest"
        ],
        "time": "2026-05-07 10:30:00"
    },
    "G49-002": {
        "sn": "G49-002",
        "station": "FCT",
        "result": "PASS",
        "fail_items": [],
        "time": "2026-05-07 10:35:00"
    },
    "G49-003": {
        "sn": "G49-003",
        "station": "FCT",
        "result": "FAIL",
        "fail_items": [
            "FlashCheck"
        ],
        "time": "2026-05-07 10:40:00"
    }
}


# =========================================================
# 首页
# 浏览器访问：http://localhost:5000/
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


# =========================================================
# 健康检查接口
# 浏览器访问：http://localhost:5000/api/health
# =========================================================
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "G4.9 FCT Fail Dashboard backend is running"
    })


# =========================================================
# SN 查询接口
# 浏览器访问：http://localhost:5000/api/sn/G49-001
# =========================================================
@app.route("/api/sn/<sn>")
def query_by_sn(sn):
    sn = sn.strip()

    data = MOCK_FCT_DATA.get(sn)

    if data is None:
        return jsonify({
            "sn": sn,
            "station": "FCT",
            "result": "NOT_FOUND",
            "fail_items": [],
            "message": "未找到该 SN 的 FCT 测试记录"
        }), 404

    return jsonify(data)


# =========================================================
# 全部数据接口
# 浏览器访问：http://localhost:5000/api/all
# =========================================================
@app.route("/api/all")
def get_all_data():
    return jsonify(list(MOCK_FCT_DATA.values()))


# =========================================================
# 统计接口
# 浏览器访问：http://localhost:5000/api/stats
# =========================================================
@app.route("/api/stats")
def get_stats():
    total = len(MOCK_FCT_DATA)
    pass_count = 0
    fail_count = 0
    fail_item_count = {}

    for item in MOCK_FCT_DATA.values():
        if item["result"] == "PASS":
            pass_count += 1
        elif item["result"] == "FAIL":
            fail_count += 1

            for fail_item in item["fail_items"]:
                fail_item_count[fail_item] = fail_item_count.get(fail_item, 0) + 1

    return jsonify({
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "top_fail": fail_item_count
    })


# =========================================================
# 程序入口
# =========================================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )