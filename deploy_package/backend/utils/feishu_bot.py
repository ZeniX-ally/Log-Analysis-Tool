import json
import os
import time
import urllib.request

DEFAULT_WEBHOOK_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "feishu_webhook.json")


def load_webhook_url(filepath=None):
    filepath = filepath or DEFAULT_WEBHOOK_FILE
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("webhook_url") or None
    except Exception:
        return None


def save_webhook_url(url, filepath=None):
    filepath = filepath or DEFAULT_WEBHOOK_FILE
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"webhook_url": url, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=2)


def send_message(webhook_url, title, content, msg_type="interactive"):
    payload = {
        "msg_type": msg_type,
    }
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
                        {"tag": "plain_text", "content": "FCT 效能诊断中枢 · " + time.strftime("%Y-%m-%d %H:%M:%S")}
                    ]
                }
            ]
        }
    elif msg_type == "text":
        payload["content"] = {"text": title + "\n" + content}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("StatusCode") == 0, result
    except Exception as e:
        return False, str(e)


def push_alert(webhook_url, alerts):
    if not webhook_url or not alerts:
        return False, "no webhook or no alerts"
    title = f"\u26a0\ufe0f \u98ce\u9669\u9884\u8b66: {len(alerts)} \u6761\u6307\u793a"
    lines = []
    for a in alerts:
        lines.append(f"**\u5de5\u7ad9:** {a.get('station', '?')}")
        lines.append(f"**\u63d0\u8981:** {a.get('message', '')}")
        lines.append(f"**\u8be6\u60c5:** {a.get('detail', '')}")
        fail_items = a.get("fail_items", [])
        if fail_items:
            items_str = ", ".join(f"`{f}`" for f in fail_items)
            lines.append(f"**\u5931\u8d25\u6d4b\u9879:** {items_str}")
        lines.append("")
    content = "\n".join(lines)
    return send_message(webhook_url, title, content)


def push_daily_report(webhook_url, stats, top_fails, cpk_warnings):
    if not webhook_url:
        return False, "no webhook"
    title = "\ud83d\udcca FCT \u6548\u80fd\u65e5\u62a5 \u2022 " + time.strftime("%Y-%m-%d")
    lines = [
        "**\ud83d\udcc8 \u6838\u5fc3\u6307\u6807**",
        f"- \u603b\u65e5\u5fd7\u6570: {stats.get('total', 0)}",
        f"- PASS: {stats.get('pass', 0)}",
        f"- FAIL: {stats.get('fail', 0)}",
        f"- \u4e2d\u65ad: {stats.get('interrupt', 0)}",
        f"- \u4e00\u6b21\u901a\u8fc7\u7387(FPY): {stats.get('fpy', 0)}%",
        "",
        "**\ud83d\udd1d TOP FAIL \u6d4b\u9879**",
    ]
    for f in (top_fails or [])[:5]:
        lines.append(f"- {f.get('item', '?')}: {f.get('count', 0)} \u6b21")
    if not top_fails:
        lines.append("- \u65e0 FAIL \u8bb0\u5f55")

    if cpk_warnings:
        lines.extend(["", "**\u26a0\ufe0f CPK \u9884\u8b66**"])
        for c in cpk_warnings[:5]:
            lines.append(f"- {c.get('item', '?')}: Cpk={c.get('cpk', '?')}")

    content = "\n".join(lines)
    return send_message(webhook_url, title, content, msg_type="interactive")
