#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS FCT 飞书 Bot 独立服务
============================
部署到 FCT6 机器，独立运行，从主服务器拉取数据并推送飞书通知。

功能:
  - 定时轮询主服务器风险预警并推送飞书
  - 定时发送日报 (08:00)
  - Web 配置页面 (端口 59489)
  - 支持手动触发测试/日报

用法:
  python3 feishu_service.py --server http://172.28.55.66:59488 --port 59489
"""

import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "feishu_config.json")
os.makedirs(DATA_DIR, exist_ok=True)

SERVER_URL = "http://127.0.0.1:59488"
BOT_PORT = 59489
POLL_INTERVAL = 30
DAILY_REPORT_HOUR = 8
DAILY_REPORT_MINUTE = 0

last_alert_ids = set()
daily_report_sent_today = False


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_webhook_url():
    return load_config().get("webhook_url", "")


def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nexus-feishu-bot/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def post_json(url, data):
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": "nexus-feishu-bot/1.0"
        }, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_feishu(webhook_url, title, content, msg_type="interactive"):
    payload = {"msg_type": msg_type}
    if msg_type == "interactive":
        payload["card"] = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red" if any(kw in title for kw in ["FAIL", "预警", "风险", "严重"]) else "blue"
            },
            "elements": [
                {"tag": "markdown", "content": content},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": "FCT 飞书 Bot \u00b7 " + time.strftime("%Y-%m-%d %H:%M:%S")}
                    ]
                }
            ]
        }
    elif msg_type == "text":
        payload["content"] = {"text": title + "\n" + content}
    return post_json(webhook_url, payload)


def poll_alerts():
    global last_alert_ids
    webhook_url = get_webhook_url()
    if not webhook_url:
        return
    result = fetch_json(f"{SERVER_URL}/api/alerts/risk")
    if not result.get("ok"):
        return
    alerts = result.get("alerts", [])
    new_alerts = [a for a in alerts if a.get("message") not in last_alert_ids]
    if not new_alerts:
        return
    last_alert_ids = set(a.get("message") for a in alerts)
    for alert in new_alerts:
        lines = [
            f"**\u5de5\u7ad9:** {alert.get('station', '?')}",
            f"**\u63d0\u8981:** {alert.get('message', '')}",
            f"**\u8be6\u60c5:** {alert.get('detail', '')}",
        ]
        fail_items = alert.get("fail_items", [])
        if fail_items:
            lines.append(f"**\u5931\u8d25\u6d4b\u9879:** {', '.join(f'`{f}`' for f in fail_items)}")
        send_feishu(webhook_url, f"\u26a0\ufe0f \u98ce\u9669\u9884\u8b66: {alert.get('station', '?')}", "\n".join(lines))


def send_daily_report():
    webhook_url = get_webhook_url()
    if not webhook_url:
        return
    stats = fetch_json(f"{SERVER_URL}/api/stats")
    if not stats.get("ok"):
        return
    d = stats.get("data", {})
    lines = [
        "**\uD83D\uDCC8 \u6838\u5FC3\u6307\u6807**",
        f"- \u603B\u65E5\u5FD7\u6570: {d.get('total', 0)}",
        f"- PASS: {d.get('pass_count', 0)}",
        f"- FAIL: {d.get('fail_count', 0)}",
        f"- \u4E2D\u65AD: {d.get('interrupt_count', 0)}",
        f"- \u4E00\u6B21\u901A\u8FC7\u7387(FPY): {d.get('fpy', 0)}%",
        "",
        "**\uD83D\uDD1D TOP FAIL \u6D4B\u9879**",
    ]
    top_fail = d.get("top_fail", [])
    for f in top_fail[:5]:
        lines.append(f"- {f.get('item', '?')}: {f.get('count', 0)} \u6B21")
    if not top_fail:
        lines.append("- \u65E0 FAIL \u8BB0\u5F55")
    cpk_warnings = d.get("cpk_warnings", [])
    if cpk_warnings:
        lines.extend(["", "**\u26A0\uFE0F CPK \u9884\u8B66**"])
        for c in cpk_warnings[:5]:
            lines.append(f"- {c.get('item', '?')}: Cpk={c.get('cpk', '?')}")
    send_feishu(webhook_url, f"\uD83D\uDCCA FCT \u6548\u80FD\u65E5\u62A5 \u00B7 {time.strftime('%Y-%m-%d')}", "\n".join(lines))


def scheduler_loop():
    global daily_report_sent_today
    while True:
        try:
            poll_alerts()
        except Exception:
            pass
        now = datetime.now()
        if now.hour == DAILY_REPORT_HOUR and now.minute >= DAILY_REPORT_MINUTE and not daily_report_sent_today:
            try:
                send_daily_report()
                daily_report_sent_today = True
            except Exception:
                pass
        if now.hour != DAILY_REPORT_HOUR:
            daily_report_sent_today = False
        time.sleep(POLL_INTERVAL)


class BotHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            cfg = load_config()
            wh = cfg.get("webhook_url", "")
            server = cfg.get("server_url", SERVER_URL)
            status = self._check_server_status()
            html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>FCT 飞书 Bot | FCT6</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0d0d0d;color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:40px;max-width:720px;margin:0 auto}}
h1{{font-size:28px;font-weight:800;margin-bottom:8px;letter-spacing:-0.5px}}
.sub{{color:#888;font-size:14px;margin-bottom:40px;font-family:"JetBrains Mono",monospace}}
.card{{background:#171717;border:1px solid #2a2a2a;border-radius:16px;padding:32px;margin-bottom:24px}}
.card h2{{font-size:16px;font-weight:700;margin-bottom:20px;color:#888}}
label{{display:block;font-size:13px;font-weight:600;color:#888;margin-bottom:8px}}
input[type=text],input[type=url]{{width:100%;background:#000;border:1px solid #2a2a2a;border-radius:8px;padding:14px 18px;color:#fff;font-size:15px;outline:none;margin-bottom:16px}}
input:focus{{border-color:#555}}
.btn{{background:#fff;color:#000;border:none;border-radius:8px;padding:12px 28px;font-size:15px;font-weight:700;cursor:pointer;transition:all .2s}}
.btn:hover{{opacity:.85;transform:scale(.98)}}
.btn-red{{background:#E31937;color:#fff}}
.btn-small{{padding:8px 16px;font-size:13px}}
.status{{display:inline-flex;align-items:center;gap:8px;padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600}}
.status-ok{{background:rgba(76,175,80,.15);color:#4caf50}}
.status-err{{background:rgba(227,25,55,.15);color:#E31937}}
.msg{{padding:12px 16px;border-radius:8px;font-size:14px;margin-top:16px;display:none}}
.msg-ok{{background:rgba(76,175,80,.15);color:#4caf50;display:block}}
.msg-err{{background:rgba(227,25,55,.15);color:#E31937;display:block}}
</style>
</head>
<body>
<h1>FCT 飞书 Bot</h1>
<div class="sub">FCT6 \u00b7 {time.strftime("%Y-%m-%d %H:%M:%S")}</div>
<div class="card">
<h2>\uD83D\uDD17 \u4E3B\u670D\u52A1\u5668\u8FDE\u63A5</h2>
<div style="margin-bottom:16px"><span class="status {status['cls']}">{status['text']}</span></div>
<label>主服务器地址</label>
<input type="url" id="serverUrl" value="{server}" placeholder="http://192.168.1.100:59488">
<button class="btn btn-small" onclick="saveServer()">保存</button>
</div>
<div class="card">
<h2>\uD83E\uDD16 \u98DE\u4E66 Webhook \u914D\u7F6E</h2>
<label>Webhook URL</label>
<input type="url" id="webhookUrl" value="{wh}" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/...">
<div style="display:flex;gap:12px;flex-wrap:wrap">
<button class="btn" onclick="saveWebhook()">\u4FDD\u5B58</button>
<button class="btn btn-red btn-small" onclick="testWebhook()">\u6D4B\u8BD5\u8FDE\u63A5</button>
<button class="btn btn-red btn-small" onclick="sendReport()">\u53D1\u9001\u65E5\u62A5</button>
</div>
<div id="msg" class="msg"></div>
</div>
<div class="card">
<h2>\u23F0 \u5B9A\u65F6\u4EFB\u52A1</h2>
<div style="color:#fff;font-size:15px;line-height:1.8">
<div>\u98CE\u9669\u9884\u8B66\u63A8\u9001: <span style="color:#4caf50;font-weight:700">\u6BCF {POLL_INTERVAL}\u79D2\u8F6E\u8BE2</span></div>
<div>\u5B9A\u65F6\u65E5\u62A5: <span style="color:#4caf50;font-weight:700">\u6BCF\u65E5 {DAILY_REPORT_HOUR}:{DAILY_REPORT_MINUTE:02d}</span></div>
</div>
</div>
<script>
function showMsg(text, type){{var m=document.getElementById('msg');m.textContent=text;m.className='msg msg-'+type;}}
function saveServer(){{var v=document.getElementById('serverUrl').value;fetch('/api/config',{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{server_url:v}})}}).then(function(r){{return r.json()}}).then(function(d){{showMsg(d.message||'ok','ok')}}).catch(function(e){{showMsg('Error: '+e,'err')}});}}
function saveWebhook(){{var v=document.getElementById('webhookUrl').value;fetch('/api/config',{{method:'PUT',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{webhook_url:v}})}}).then(function(r){{return r.json()}}).then(function(d){{showMsg(d.message||'ok','ok')}}).catch(function(e){{showMsg('Error: '+e,'err')}});}}
function testWebhook(){{fetch('/api/test',{{method:'POST'}}).then(function(r){{return r.json()}}).then(function(d){{showMsg(d.message||'ok',d.ok?'ok':'err')}}).catch(function(e){{showMsg('Error: '+e,'err')}});}}
function sendReport(){{fetch('/api/daily-report',{{method:'POST'}}).then(function(r){{return r.json()}}).then(function(d){{showMsg(d.message||'ok',d.ok?'ok':'err')}}).catch(function(e){{showMsg('Error: '+e,'err')}});}}
</script>
</body>
</html>"""
            self.wfile.write(html.encode("utf-8"))
        elif self.path == "/api/config":
            cfg = load_config()
            self._json_response({"ok": True, "webhook_url": cfg.get("webhook_url", ""), "server_url": cfg.get("server_url", SERVER_URL)})
        elif self.path == "/api/status":
            self._json_response(self._check_server_status())
        elif self.path == "/api/test":
            wh = get_webhook_url()
            if not wh:
                self._json_response({"ok": False, "message": "未配置 Webhook URL"})
                return
            ok, result = send_feishu(wh, "\u2705 FCT \u98DE\u4E66 Bot \u8FDE\u63A5\u6D4B\u8BD5",
                "\u8FDE\u63A5\u6210\u529F\uff01\u6B63\u5E38\u63A5\u6536\u544A\u8B66\u63A8\u9001\u3002\n\n\u2705 \u5B9E\u65F6\u98CE\u9669\u9884\u8B66\n\u2705 \u5B9A\u65F6\u6548\u80FD\u65E5\u62A5")
            self._json_response({"ok": ok, "message": "\u6D4B\u8BD5\u6210\u529F" if ok else f"\u6D4B\u8BD5\u5931\u8D25: {result}"})
        elif self.path == "/api/daily-report":
            try:
                send_daily_report()
                self._json_response({"ok": True, "message": "\u65E5\u62A5\u5DF2\u53D1\u9001"})
            except Exception as e:
                self._json_response({"ok": False, "message": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        if self.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                data = json.loads(body)
                cfg = load_config()
                if "webhook_url" in data:
                    cfg["webhook_url"] = data["webhook_url"].strip()
                if "server_url" in data:
                    cfg["server_url"] = data["server_url"].strip()
                    global SERVER_URL
                    SERVER_URL = cfg["server_url"]
                save_config(cfg)
                self._json_response({"ok": True, "message": "配置已保存"})
            except Exception as e:
                self._json_response({"ok": False, "message": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _check_server_status(self):
        result = fetch_json(f"{SERVER_URL}/api/stats")
        if result.get("ok"):
            return {"text": f"\u2705 \u4E3B\u670D\u52A1\u5668\u8FDE\u63A5\u6B63\u5E38 ({SERVER_URL})", "cls": "status-ok"}
        return {"text": f"\u274C \u65E0\u6CD5\u8FDE\u63A5\u4E3B\u670D\u52A1\u5668 ({SERVER_URL})", "cls": "status-err"}

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), format % args))


def main():
    global SERVER_URL, BOT_PORT
    import argparse
    parser = argparse.ArgumentParser(description="NEXUS FCT \u98DE\u4E66 Bot \u72EC\u7ACB\u670D\u52A1")
    parser.add_argument("--server", default=SERVER_URL, help="\u4E3B\u670D\u52A1\u5668\u5730\u5740 (default: %s)" % SERVER_URL)
    parser.add_argument("--port", type=int, default=BOT_PORT, help="\u672C\u5730\u7AEF\u53E3 (default: %d)" % BOT_PORT)
    args = parser.parse_args()
    SERVER_URL = args.server
    BOT_PORT = args.port

    cfg = load_config()
    cfg["server_url"] = SERVER_URL
    save_config(cfg)

    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", BOT_PORT), BotHTTPHandler)
    print("")
    print("  \u2705 NEXUS FCT \u98DE\u4E66 Bot \u5DF2\u542F\u52A8")
    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    print("  \u4E3B\u670D\u52A1\u5668: %s" % SERVER_URL)
    print("  \u672C\u5730\u7AEF\u53E3:  %d" % BOT_PORT)
    print("  \u914D\u7F6E\u9875\u9762: http://0.0.0.0:%d" % BOT_PORT)
    print("  \u98CE\u9669\u9884\u8B66: \u6BCF %d\u79D2\u8F6E\u8BE2" % POLL_INTERVAL)
    print("  \u5B9A\u65F6\u65E5\u62A5: \u6BCF\u65E5 %02d:%02d" % (DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE))
    print("")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  \u23F9 \u670D\u52A1\u5DF2\u505C\u6B62")
        server.server_close()


if __name__ == "__main__":
    main()