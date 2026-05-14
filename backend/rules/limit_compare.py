# -*- coding: utf-8 -*-
import os
import json
import re
from datetime import datetime
from collections import defaultdict


def load_spec(spec_path=None):
    if spec_path and os.path.exists(spec_path):
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def find_model_in_record(record):
    model = record.get("model") or ""
    if model:
        return model.upper()
    sn = str(record.get("sn") or "")
    for m in re.findall(r'(E\d{7})', sn):
        return m
    return "UNKNOWN"


def spec_limits_for_model(item_name, model, spec):
    if not spec or "items" not in spec:
        return None
    spec_item = spec["items"].get(item_name)
    if not spec_item:
        return None
    limits_list = spec_item.get("limits", [])
    for entry in limits_list:
        models_entry = entry.get("models", "*")
        if isinstance(models_entry, list) and model in models_entry:
            return {"lo": str(entry.get("lo", "")).strip(), "hi": str(entry.get("hi", "")).strip()}
    for entry in limits_list:
        models_entry = entry.get("models", "*")
        if models_entry == "*":
            return {"lo": str(entry.get("lo", "")).strip(), "hi": str(entry.get("hi", "")).strip()}
    return None


def resolve_model_group(model, spec):
    if not spec or "model_groups" not in spec:
        return model
    for group_name, models in spec["model_groups"].items():
        if model in models:
            return group_name
    return model


def build_station_profile(records, max_records_per_station=200):
    """按工站聚合限值信息，每个工站取最新一条记录的代表性限值"""
    station_profiles = {}
    for record in records:
        station = record.get("station") or "UNKNOWN"
        if station not in station_profiles:
            station_profiles[station] = {
                "model": find_model_in_record(record),
                "items": {}
            }
        if len(station_profiles[station]["items"]) >= 200:
            continue
        raw_items = record.get("raw_items") or []
        for item in raw_items:
            name = item.get("name") or item.get("raw_name")
            if not name:
                continue
            lo = str(item.get("lolim") or "").strip()
            hi = str(item.get("hilim") or "").strip()
            if not lo and not hi:
                continue
            if name not in station_profiles[station]["items"]:
                station_profiles[station]["items"][name] = {
                    "lo": lo, "hi": hi,
                    "unit": item.get("unit") or "",
                    "sn": record.get("sn") or "?",
                }
    return station_profiles


def build_machine_matrix(records, max_records_per_station=200):
    """
    机台间限值对比矩阵。
    对每个测项，列出每台机台的限值，标记哪些机台一致、哪些不同。
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    profiles = build_station_profile(records, max_records_per_station)

    stations = sorted(profiles.keys())
    station_models = {s: profiles[s]["model"] for s in stations}

    # 收集所有测项名
    all_items = set()
    for s in stations:
        all_items.update(profiles[s]["items"].keys())
    all_items = sorted(all_items)

    matrix_items = []
    for item_name in all_items:
        by_station = {}
        for s in stations:
            if item_name in profiles[s]["items"]:
                by_station[s] = dict(profiles[s]["items"][item_name])
                by_station[s]["model"] = profiles[s]["model"]
            else:
                by_station[s] = {"lo": "", "hi": "", "unit": "", "model": profiles[s]["model"], "missing": True}

        # 分析一致性
        # 按限值分组 -> 哪些工站用同一组限值
        limit_groups = defaultdict(list)
        for s, info in by_station.items():
            if info.get("missing"):
                limit_groups["(缺失)"].append(s)
            else:
                key = f"{info['lo']}~{info['hi']}"
                limit_groups[key].append(s)

        # 按型号分组 -> 同一型号下是否一致
        model_groups = defaultdict(list)
        for s, info in by_station.items():
            model_groups[info["model"]].append(s)

        model_consistency = {}
        for model, stns in model_groups.items():
            limits_set = set()
            for s in stns:
                if not by_station[s].get("missing"):
                    limits_set.add(f"{by_station[s]['lo']}~{by_station[s]['hi']}")
            model_consistency[model] = {
                "consistent": len(limits_set) <= 1,
                "stations": stns,
                "limit_variants": len(limits_set),
            }

        # 判断是否所有机台一致
        non_missing = {k: v for k, v in by_station.items() if not v.get("missing")}
        all_limits = set(f"{v['lo']}~{v['hi']}" for v in non_missing.values())
        all_same = len(all_limits) <= 1

        # 哪些机台是偏离的
        if all_same:
            deviant_stations = []
        else:
            # 多数派
            max_group = max(limit_groups.values(), key=len)
            majority_stations = set(max_group)
            deviant_stations = [s for s in stations if s not in majority_stations and not by_station[s].get("missing")]

        # 差异是否因型号不同导致
        model_diff = False
        if not all_same and len(all_limits) > 1:
            models_with_limits = {}
            for s, info in by_station.items():
                if not info.get("missing"):
                    key = f"{info['lo']}~{info['hi']}"
                    if key not in models_with_limits:
                        models_with_limits[key] = set()
                    models_with_limits[key].add(info["model"])
            if len(models_with_limits) > 1:
                # 不同限值对应不同的型号集合
                model_diff = all(
                    len(m_set) >= 1 for m_set in models_with_limits.values()
                )

        matrix_items.append({
            "item_name": item_name,
            "unit": next((v.get("unit", "") for v in by_station.values() if v.get("unit")), ""),
            "by_station": by_station,
            "all_same": all_same,
            "model_diff": model_diff,
            "limit_groups": dict(limit_groups),
            "model_consistency": model_consistency,
            "deviant_stations": deviant_stations,
            "station_count": len(stations),
            "present_station_count": len(non_missing),
        })

    # 排序：不一致的排前面
    matrix_items.sort(key=lambda x: (0 if x["all_same"] else 1, -x["station_count"]))

    return {
        "mode": "machine_matrix",
        "checked_at": now_str,
        "stations": stations,
        "station_models": station_models,
        "total_items": len(matrix_items),
        "consistent_count": sum(1 for x in matrix_items if x["all_same"]),
        "inconsistent_count": sum(1 for x in matrix_items if not x["all_same"]),
        "items": matrix_items,
    }


def build_spec_compliance_matrix(records, spec, max_records_per_station=200):
    """
    规格书合规矩阵。
    对每个测项，列出每台机台的限值与 Spec 的比对结果。
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    profiles = build_station_profile(records, max_records_per_station)

    stations = sorted(profiles.keys())
    station_models = {s: profiles[s]["model"] for s in stations}

    all_items = set()
    for s in stations:
        all_items.update(profiles[s]["items"].keys())
    all_items = sorted(all_items)

    spec_items = spec.get("items", {})
    model_groups = spec.get("model_groups", {})

    matrix_items = []
    for item_name in all_items:
        spec_entry = spec_items.get(item_name)
        if not spec_entry:
            continue  # Spec 中没有定义的测项跳过

        unit = spec_entry.get("unit", "")
        by_station = {}
        compliant_count = 0
        non_compliant_count = 0
        missing_count = 0

        for s in stations:
            model = profiles[s]["model"]
            model_group = resolve_model_group(model, spec)
            expected = spec_limits_for_model(item_name, model, spec)

            station_entry = {"model": model, "model_group": model_group}

            if item_name not in profiles[s]["items"]:
                station_entry["missing"] = True
                station_entry["match"] = False
                station_entry["note"] = "机台无此测项"
                missing_count += 1
            else:
                actual = profiles[s]["items"][item_name]
                station_entry["lo"] = actual["lo"]
                station_entry["hi"] = actual["hi"]
                station_entry["unit"] = actual.get("unit", "")
                station_entry["sn"] = actual.get("sn", "")

                if expected:
                    station_entry["expected_lo"] = expected["lo"]
                    station_entry["expected_hi"] = expected["hi"]
                    match = (actual["lo"] == expected["lo"] and actual["hi"] == expected["hi"])
                    station_entry["match"] = match
                    station_entry["note"] = "符合规格" if match else f"偏离规格: 实际={actual['lo']}~{actual['hi']}, 规格={expected['lo']}~{expected['hi']}"
                    if match:
                        compliant_count += 1
                    else:
                        non_compliant_count += 1
                else:
                    station_entry["match"] = False
                    station_entry["note"] = f"型号 {model} 在规格书中未定义此测项限值"
                    non_compliant_count += 1

            by_station[s] = station_entry

        all_compliant = non_compliant_count == 0 and missing_count == 0

        matrix_items.append({
            "item_name": item_name,
            "unit": unit,
            "by_station": by_station,
            "all_compliant": all_compliant,
            "compliant_count": compliant_count,
            "non_compliant_count": non_compliant_count,
            "missing_count": missing_count,
            "non_compliant_stations": [s for s, v in by_station.items() if not v.get("match", False)],
        })

    # 排序：不合规的排前面
    matrix_items.sort(key=lambda x: (0 if x["all_compliant"] else 1, -x["non_compliant_count"]))

    return {
        "mode": "spec_compliance_matrix",
        "checked_at": now_str,
        "spec_name": spec.get("spec_name", "unknown"),
        "spec_item_count": len(spec_items),
        "stations": stations,
        "station_models": station_models,
        "model_groups": model_groups,
        "total_items": len(matrix_items),
        "compliant_count": sum(1 for x in matrix_items if x["all_compliant"]),
        "non_compliant_count": sum(1 for x in matrix_items if not x["all_compliant"]),
        "items": matrix_items,
    }


def compare_limits(records, max_records_per_station=200, spec=None):
    """统一入口：根据是否有 spec 返回不同的对比结果"""
    if spec:
        return build_spec_compliance_matrix(records, spec, max_records_per_station)
    else:
        return build_machine_matrix(records, max_records_per_station)