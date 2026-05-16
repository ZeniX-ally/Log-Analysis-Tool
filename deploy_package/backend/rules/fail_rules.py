# -*- coding: utf-8 -*-
"""
Fail Rules

用于 Top Fail、Fail 分类、工程提示。
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List


def normalize_fail_name(item: Any) -> str:
    if isinstance(item, dict):
        return item.get("name") or item.get("raw_name") or item.get("item") or "-"
    return str(item or "-")


def build_top_fail(records: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    counter = Counter()
    detail = defaultdict(lambda: {
        "models": set(),
        "modes": set(),
        "stations": set(),
        "latest_time": "",
        "examples": [],
    })

    for r in records:
        for item in r.get("fail_items", []) or []:
            name = normalize_fail_name(item)
            counter[name] += 1

            d = detail[name]
            if r.get("model"):
                d["models"].add(r.get("model"))
            if r.get("test_mode"):
                d["modes"].add(r.get("test_mode"))
            if r.get("station"):
                d["stations"].add(r.get("station"))

            t = r.get("time") or r.get("file_mtime") or ""
            if t and t > d["latest_time"]:
                d["latest_time"] = t

            if len(d["examples"]) < 3:
                d["examples"].append({
                    "sn": r.get("sn", ""),
                    "value": item.get("value", ""),
                    "unit": item.get("unit", ""),
                    "nominal_range": item.get("nominal_range", ""),
                    "instrument": item.get("instrument", ""),
                })

    result = []
    for name, count in counter.most_common(limit):
        d = detail[name]
        result.append({
            "item": name,
            "count": count,
            "models": sorted(list(d["models"])),
            "modes": sorted(list(d["modes"])),
            "stations": sorted(list(d["stations"])),
            "latest_time": d["latest_time"],
            "examples": d["examples"],
            "warning_level": warning_level_by_count(count),
        })

    return result


def warning_level_by_count(count: int) -> str:
    if count >= 5:
        return "HIGH"
    if count >= 3:
        return "MEDIUM"
    return "LOW"


def build_fail_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "top_fail": build_top_fail(records, limit=20),
        "fail_record_count": sum(1 for r in records if r.get("business_result") == "FAIL"),
        "fail_item_count": sum(len(r.get("fail_items", []) or []) for r in records),
    }