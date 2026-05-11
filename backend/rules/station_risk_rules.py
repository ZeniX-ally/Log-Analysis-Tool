# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

def parse_dt(text: str) -> Optional[datetime]:
    if not text:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    candidates = ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]
    for fmt in candidates:
        try: return datetime.strptime(raw[:19], fmt)
        except Exception: pass
    try:
        compact = "".join(ch for ch in raw if ch.isdigit())
        if len(compact) >= 14: return datetime.strptime(compact[:14], "%Y%m%d%H%M%S")
    except Exception: pass
    return None

def time_bucket(dt_value: datetime, window_minutes: int) -> str:
    if window_minutes <= 0: window_minutes = 30
    minute = (dt_value.minute // window_minutes) * window_minutes
    bucket = dt_value.replace(minute=minute, second=0, microsecond=0)
    return bucket.strftime("%Y-%m-%d %H:%M")

def build_station_risk(
    records: List[Dict[str, Any]],
    window_minutes: int = 30,
    min_fail_count: int = 3,
    min_sn_count: int = 3,
) -> List[Dict[str, Any]]:
    groups: Dict[Any, Dict[str, Any]] = defaultdict(
        lambda: {
            "sns": set(), "records": [], "models": set(), "modes": set(),
            "stations": set(), "latest_time": "", "instrument": "", "signal": "",
        }
    )

    for record in records:
        record_time = record.get("time") or record.get("file_mtime") or ""
        dt_value = parse_dt(record_time)
        if not dt_value: continue

        bucket = time_bucket(dt_value, window_minutes)
        fail_items = record.get("fail_items", []) or []

        for item in fail_items:
            item_name = item.get("name") or item.get("raw_name") or "-"
            
            # 🌟 核心拦截：把人为操作失误从物理链路预警中彻底剔除 🌟
            if "Get Unit Information" in item_name:
                continue

            signal = item.get("signal") or item_name
            instrument = item.get("instrument") or "UNKNOWN"

            key = (bucket, item_name, signal, instrument)
            group = groups[key]

            sn = record.get("sn", "")
            if sn: group["sns"].add(sn)

            group["records"].append({
                "sn": sn, "time": record_time, "model": record.get("model", ""),
                "mode": record.get("test_mode", ""), "station": record.get("station", ""),
                "value": item.get("value", ""), "unit": item.get("unit", ""),
                "nominal_range": item.get("nominal_range", ""), "file": record.get("source_file", ""),
            })

            if record.get("model"): group["models"].add(record.get("model"))
            if record.get("test_mode"): group["modes"].add(record.get("test_mode"))
            if record.get("station"): group["stations"].add(record.get("station"))

            if record_time and record_time > group["latest_time"]:
                group["latest_time"] = record_time

            group["instrument"] = instrument
            group["signal"] = signal

    risks: List[Dict[str, Any]] = []

    for key, group in groups.items():
        bucket, item_name, signal, instrument = key
        fail_count = len(group["records"])
        sn_count = len(group["sns"])

        if fail_count >= min_fail_count and sn_count >= min_sn_count:
            level = "HIGH" if fail_count >= 5 else "MEDIUM"
            risks.append({
                "time_window": f"{bucket} / {window_minutes}min", "item": item_name, "signal": signal,
                "instrument": instrument, "fail_count": fail_count, "sn_count": sn_count,
                "models": sorted(list(group["models"])), "modes": sorted(list(group["modes"])),
                "stations": sorted(list(group["stations"])), "latest_time": group["latest_time"],
                "level": level, "message": "短时间内多产品在同一节点 Fail，疑似机台探针或仪表物理异常，需工程师排查。",
                "examples": group["records"][:5],
            })

    risks.sort(key=lambda item: (0 if item.get("level") == "HIGH" else 1, -int(item.get("fail_count", 0)), item.get("latest_time", "")))
    return risks