# -*- coding: utf-8 -*-
"""
POWERED BY ZENIX-ALLY — 终端实时监控仪表盘
==============================================
用法:  python tools/server_monitor.py [--host IP] [--port PORT]

依赖:  pip install rich psutil
       (psutil 可选，缺失时仅不显示系统资源)

显示内容:
  - 系统资源 (CPU / 内存 / 磁盘 / 负载)
  - 日志统计 (已接收 / 已分析 / 待处理 / 每日FAIL)
  - 传输速率
  - 6台FCT机台连接状态 + IP
  - 实时活动日志 (新文件提示 / 上传结果)
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich.console import Console
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("[ERROR] 需要 rich 库: pip install rich")
    sys.exit(1)


console = Console()

MACHINE_IP_MAP = {
    "PEU_G49_FCT1_01": "172.28.55.11",
    "PEU_G49_FCT2_01": "172.28.55.12",
    "PEU_G49_FCT3_01": "172.28.55.13",
    "PEU_G49_FCT4_01": "172.28.55.14",
    "PEU_G49_FCT5_01": "172.28.55.15",
    "PEU_G49_FCT6_01": "172.28.55.16",
}

MACHINE_SHORT = {
    "PEU_G49_FCT1_01": "FCT1",
    "PEU_G49_FCT2_01": "FCT2",
    "PEU_G49_FCT3_01": "FCT3",
    "PEU_G49_FCT4_01": "FCT4",
    "PEU_G49_FCT5_01": "FCT5",
    "PEU_G49_FCT6_01": "FCT6",
}


def fetch_status(host, port):
    url = f"http://{host}:{port}/api/server/status"
    try:
        req = Request(url)
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError:
        return None
    except Exception:
        return None


def build_header(data, host, port):
    if data and data.get("server"):
        uptime = data["server"].get("uptime", "-")
        start = data["server"].get("start_time", "-")[:19]
    else:
        uptime = "-"
        start = "-"

    status_color = "green" if data else "red"
    status_text = "● CONNECTED" if data else "● DISCONNECTED"

    header = Table.grid(padding=(0, 2))
    header.add_column(justify="left", ratio=1)
    header.add_column(justify="center", ratio=1)
    header.add_column(justify="right", ratio=1)

    header.add_row(
        Text(f"POWERED BY ZENIX-ALLY", style="bold white"),
        Text(f"{host}:{port}", style="cyan"),
        Text(f"{status_text}  |  {datetime.now().strftime('%H:%M:%S')}", style=status_color),
    )
    return Panel(header, style="bright_blue", box=box.ROUNDED)


def build_system_panel(data):
    if not data or not data.get("system"):
        return Panel(
            Text("等待数据...", style="dim"),
            title="[bold]系统资源[/bold]",
            border_style="blue",
            box=box.ROUNDED,
        )

    sys_data = data["system"]
    cpu = sys_data.get("cpu_percent")
    mem = sys_data.get("memory_percent")
    disk = sys_data.get("disk_percent")
    load = sys_data.get("load_avg")

    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right", ratio=1)

    def bar(val, max_val=100, width=18):
        if val is None:
            return Text("N/A", style="dim")
        filled = int(val / max_val * width)
        filled = min(filled, width)
        bar_chars = "█" * filled + "░" * (width - filled)
        color = "green" if val < 60 else "yellow" if val < 85 else "red"
        return Text(f"{bar_chars} {val:.1f}%", style=color)

    table.add_row("CPU:", bar(cpu))
    table.add_row("MEM:", bar(mem))
    table.add_row("DISK:", bar(disk))

    if load:
        load_str = ", ".join(f"{x:.2f}" for x in load)
        table.add_row("LOAD:", Text(load_str, style="cyan"))

    uptime = data.get("server", {}).get("uptime", "-")
    table.add_row("UPTIME:", Text(uptime, style="cyan"))

    return Panel(table, title="[bold]系统资源[/bold]", border_style="blue", box=box.ROUNDED)


def build_stats_panel(data):
    if not data or not data.get("metrics"):
        return Panel(
            Text("等待数据...", style="dim"),
            title="[bold]日志统计[/bold]",
            border_style="green",
            box=box.ROUNDED,
        )

    m = data["metrics"]
    received = m.get("total_received", 0)
    analyzed = m.get("total_analyzed", 0)
    total_fail = m.get("total_fail", 0)
    daily_fail = m.get("daily_fail", 0)
    speed = m.get("transfer_speed_display", "0 B/s")
    daily_date = m.get("daily_date", "")

    pending = max(0, received - analyzed)

    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right", ratio=1)

    table.add_row("已接收:", Text(f"{received:,} 个文件", style="bold white"))
    table.add_row("已分析:", Text(f"{analyzed:,} 个文件", style="green"))
    table.add_row("待处理:", Text(f"{pending:,} 个文件", style="yellow" if pending > 0 else "dim"))
    table.add_row("", "")
    table.add_row(f"今日 FAIL ({daily_date}):", Text(f"{daily_fail}", style="red bold"))
    table.add_row("累计 FAIL:", Text(f"{total_fail}", style="red"))
    table.add_row("", "")
    table.add_row("传输速率:", Text(speed, style="cyan bold"))

    return Panel(table, title="[bold]日志统计[/bold]", border_style="green", box=box.ROUNDED)


def build_machines_panel(data):
    if not data or not data.get("machines"):
        return Panel(
            Text("等待机台数据...", style="dim"),
            title="[bold]机台状态[/bold]",
            border_style="yellow",
            box=box.ROUNDED,
        )

    machines = data["machines"].get("machines", [])
    online = data["machines"].get("online", 0)
    stale = data["machines"].get("stale", 0)
    offline = data["machines"].get("offline", 0)

    table = Table(
        box=box.SIMPLE,
        header_style="bold cyan",
        show_edge=False,
        padding=(0, 2),
    )
    table.add_column("机台", justify="center", style="bold")
    table.add_column("IP", justify="center")
    table.add_column("状态", justify="center")
    table.add_column("运行状态", justify="center")
    table.add_column("最后心跳", justify="center")

    if not machines:
        for short_id, ip in MACHINE_IP_MAP.items():
            table.add_row(
                short_id,
                ip,
                Text("● OFFLINE", style="red"),
                Text("-", style="dim"),
                Text("-", style="dim"),
            )
    else:
        seen = set()
        for m in machines:
            mid = m.get("machine_id", "")
            seen.add(mid)
            short = MACHINE_SHORT.get(mid, mid)
            ip = MACHINE_IP_MAP.get(mid, m.get("ip", "-"))
            status = m.get("online_status", "OFFLINE")
            state = m.get("display_state", "-")
            hb = m.get("last_heartbeat", m.get("timestamp", ""))[-8:]

            if status == "ONLINE":
                status_style = "green"
            elif status == "STALE":
                status_style = "yellow"
            else:
                status_style = "red"

            table.add_row(
                Text(short, style="bold"),
                Text(ip, style="cyan"),
                Text(f"● {status}", style=status_style),
                Text(state, style="bold white" if state == "RUNNING" else "dim"),
                Text(hb, style="dim"),
            )

        for mid, ip in MACHINE_IP_MAP.items():
            if mid not in seen:
                short = MACHINE_SHORT.get(mid, mid)
                table.add_row(
                    Text(short, style="bold dim"),
                    Text(ip, style="dim"),
                    Text("● OFFLINE", style="red"),
                    Text("-", style="dim"),
                    Text("-", style="dim"),
                )

    summary = Text(
        f"在线: {online}  存疑: {stale}  离线: {offline}  共: {online + stale + offline}台",
        style="cyan",
    )

    return Panel(
        table,
        title="[bold]机台状态[/bold]",
        subtitle=summary,
        border_style="yellow",
        box=box.ROUNDED,
    )


def build_activity_panel(data):
    if not data or not data.get("metrics"):
        return Panel(
            Text("等待活动数据...", style="dim"),
            title="[bold]实时活动[/bold]",
            border_style="magenta",
            box=box.ROUNDED,
        )

    uploads = data["metrics"].get("recent_uploads", [])
    table = Table(
        box=box.SIMPLE,
        show_header=False,
        show_edge=False,
        padding=(0, 1),
    )
    table.add_column("时间", justify="left", no_wrap=True, width=9)
    table.add_column("事件", justify="left", no_wrap=True, width=6)
    table.add_column("内容", justify="left", ratio=1)

    if not uploads:
        table.add_row(
            Text("-", style="dim"),
            Text("-", style="dim"),
            Text("暂无活动记录", style="dim"),
        )
    else:
        for entry in reversed(uploads[-15:]):
            t = entry.get("time", "")[-8:]
            event = entry.get("event", "")
            fname = entry.get("filename", "")
            mid = entry.get("machine_id", "")
            short_mid = MACHINE_SHORT.get(mid, mid)
            size = entry.get("size", 0)
            result = entry.get("result", "-")

            if size >= 1048576:
                size_str = f"{size/1048576:.1f}MB"
            elif size >= 1024:
                size_str = f"{size/1024:.0f}KB"
            else:
                size_str = f"{size}B"

            if event == "RECEIVED":
                event_style = "yellow"
                event_text = "[NEW]"
                content = Text.assemble(
                    Text(f"{fname} ", style="white"),
                    Text(f"来自 {short_mid} ", style="cyan"),
                    Text(f"({size_str})", style="dim"),
                )
            elif event == "ANALYZED":
                if result == "FAIL":
                    event_style = "red"
                    event_text = "[FAIL]"
                else:
                    event_style = "green"
                    event_text = "[OK]"
                content = Text.assemble(
                    Text(f"{fname} ", style="white"),
                    Text(f"→ {result} ", style=event_style),
                    Text(f"({short_mid})", style="dim"),
                )
            else:
                event_style = "dim"
                event_text = "[---]"
                content = Text(f"{fname}", style="dim")

            table.add_row(
                Text(t, style="dim"),
                Text(event_text, style=event_style),
                content,
            )

    return Panel(
        table,
        title="[bold]实时活动[/bold]",
        border_style="magenta",
        box=box.ROUNDED,
    )


def build_dashboard(data, host, port):
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="machines", ratio=1),
        Layout(name="activity", ratio=1),
    )

    layout["header"].update(build_header(data, host, port))

    body = Layout()
    body.split_row(
        Layout(name="system", ratio=1),
        Layout(name="stats", ratio=1),
    )
    body["system"].update(build_system_panel(data))
    body["stats"].update(build_stats_panel(data))
    layout["body"].update(body)

    layout["machines"].update(build_machines_panel(data))
    layout["activity"].update(build_activity_panel(data))

    return layout


def main():
    parser = argparse.ArgumentParser(description="NEXUS FCT Server Monitor")
    parser.add_argument("--host", default="127.0.0.1", help="服务器 IP (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=59488, help="服务器端口 (默认: 59488)")
    parser.add_argument("--interval", type=float, default=2.0, help="刷新间隔秒数 (默认: 2.0)")
    args = parser.parse_args()

    host = args.host
    port = args.port
    interval = args.interval

    if host == "127.0.0.1":
        host = "localhost"

    console.clear()
    console.print(f"[bold cyan]POWERED BY ZENIX-ALLY[/bold cyan]")
    console.print(f"  服务器: [green]{host}:{port}[/green]")
    console.print(f"  刷新间隔: {interval}s")
    console.print(f"  按 [bold]Ctrl+C[/bold] 退出")
    console.print()

    connect_failures = 0
    last_data = None

    try:
        with Live(
            console=console,
            screen=True,
            auto_refresh=False,
            refresh_per_second=4,
        ) as live:
            while True:
                data = fetch_status(host, port)
                if data:
                    connect_failures = 0
                    last_data = data
                else:
                    connect_failures += 1

                display_data = data if data else last_data
                layout = build_dashboard(display_data, host, port)
                live.update(layout, refresh=True)
                time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]监控已停止[/bold yellow]")


if __name__ == "__main__":
    main()