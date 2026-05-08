from collections import Counter, defaultdict
from typing import List, Dict, Any

from backend.models.data_model import TestRecord


def get_top_fail(records: List[TestRecord], limit: int = 10) -> List[Dict[str, Any]]:
    counter = Counter()

    for record in records:
        for item in record.test_items:
            if item.status.upper() == "FAILED":
                counter[item.name] += 1

    result = []

    for item, count in counter.most_common(limit):
        result.append({
            "item": item,
            "count": count,
        })

    return result


def get_model_summary(records: List[TestRecord]) -> List[Dict[str, Any]]:
    summary = defaultdict(lambda: {
        "total": 0,
        "pass": 0,
        "fail": 0,
        "unknown": 0,
    })

    for record in records:
        model = record.model or "UNKNOWN"
        result = record.result.upper()

        summary[model]["total"] += 1

        if result == "PASS":
            summary[model]["pass"] += 1
        elif result == "FAIL":
            summary[model]["fail"] += 1
        else:
            summary[model]["unknown"] += 1

    output = []

    for model, data in summary.items():
        total = data["total"]
        fail_rate = round(data["fail"] / total * 100, 2) if total else 0

        output.append({
            "model": model,
            "total": total,
            "pass": data["pass"],
            "fail": data["fail"],
            "unknown": data["unknown"],
            "fail_rate": fail_rate,
        })

    output.sort(key=lambda x: x["total"], reverse=True)
    return output


def get_recent_fail_trend(records: List[TestRecord]) -> List[Dict[str, Any]]:
    trend = defaultdict(lambda: {
        "total": 0,
        "fail": 0,
    })

    for record in records:
        date_key = "UNKNOWN"

        if record.test_time:
            date_key = record.test_time[:10]

        trend[date_key]["total"] += 1

        if record.result.upper() == "FAIL":
            trend[date_key]["fail"] += 1

    output = []

    for date_key, data in trend.items():
        fail_rate = round(data["fail"] / data["total"] * 100, 2) if data["total"] else 0

        output.append({
            "date": date_key,
            "total": data["total"],
            "fail": data["fail"],
            "fail_rate": fail_rate,
        })

    output.sort(key=lambda x: x["date"])
    return output[-14:]


def get_warning_list(records: List[TestRecord]) -> List[Dict[str, Any]]:
    top_fail = get_top_fail(records, limit=20)

    warnings = []

    for item in top_fail:
        count = item["count"]

        if count >= 10:
            level = "HIGH"
            message = "High repeated failure item detected"
        elif count >= 5:
            level = "MEDIUM"
            message = "Repeated failure item detected"
        elif count >= 3:
            level = "LOW"
            message = "Potential repeated failure item"
        else:
            continue

        warnings.append({
            "level": level,
            "item": item["item"],
            "count": count,
            "message": message,
        })

    return warnings


def build_analysis(records: List[TestRecord]) -> Dict[str, Any]:
    total = len(records)
    pass_count = sum(1 for r in records if r.result.upper() == "PASS")
    fail_count = sum(1 for r in records if r.result.upper() == "FAIL")
    unknown_count = total - pass_count - fail_count

    fail_rate = round(fail_count / total * 100, 2) if total else 0

    return {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "unknown": unknown_count,
        "fail_rate": fail_rate,
        "top_fail": get_top_fail(records),
        "model_summary": get_model_summary(records),
        "trend": get_recent_fail_trend(records),
        "warnings": get_warning_list(records),
    }