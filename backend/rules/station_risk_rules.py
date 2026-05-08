from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Any

from backend.models.data_model import TestRecord, TestItem


def _parse_time(value: str):
    if not value:
        return None

    value = value.strip()

    fmts = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]

    for fmt in fmts:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass

    # 修正 +08:00 这种时区
    try:
        if value[-3] == ":":
            fixed = value[:-3] + value[-2:]
            return datetime.strptime(fixed, "%Y-%m-%dT%H:%M:%S.%f%z")
    except Exception:
        pass

    return None


def _build_key(item: TestItem) -> str:
    signal = item.signal or item.name
    instrument = item.instrument or "UNKNOWN"
    return f"{signal}||{instrument}"


def analyze_station_risk(
    records: List[TestRecord],
    window_minutes: int = 30,
    min_fail_count: int = 3,
    min_sn_count: int = 3,
) -> List[Dict[str, Any]]:

    fail_events = []

    for record in records:
        record_time = _parse_time(record.test_time)

        for item in record.test_items:
            if item.status != "FAILED":
                continue

            item_time = _parse_time(item.timestamp) or record_time
            if not item_time:
                continue

            fail_events.append({
                "sn": record.sn,
                "time": item_time,
                "item": item,
            })

    if not fail_events:
        return []

    fail_events.sort(key=lambda x: x["time"])

    risks = []
    seen_keys = set()

    for i, base in enumerate(fail_events):
        start = base["time"]
        end = start + timedelta(minutes=window_minutes)

        window = [
            e for e in fail_events
            if start <= e["time"] <= end
        ]

        grouped = defaultdict(list)
        for e in window:
            grouped[_build_key(e["item"])].append(e)

        for key, rows in grouped.items():
            if len(rows) < min_fail_count:
                continue

            sns = sorted({r["sn"] for r in rows})
            if len(sns) < min_sn_count:
                continue

            sample = rows[0]["item"]
            uniq = f"{key}|{start}"

            if uniq in seen_keys:
                continue

            seen_keys.add(uniq)

            risks.append({
                "level": "提示",
                "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end.strftime("%Y-%m-%d %H:%M:%S"),
                "window_minutes": window_minutes,
                "fail_count": len(rows),
                "sn_count": len(sns),
                "sns": sns[:10],
                "test_item": sample.name,
                "signal": sample.signal,
                "reference_point": sample.reference_point,
                "instrument": sample.instrument,
                "instrument_device": sample.instrument_device,
                "nominal": sample.nominal,
                "message": (
                    f"{window_minutes} 分钟内，同一测试项/点位重复 FAIL，"
                    f"涉及 {len(sns)} 个 SN，共 {len(rows)} 次。"
                    "建议检查机台、仪表、夹具与测试链路。"
                ),
            })

    return risks[:50]
