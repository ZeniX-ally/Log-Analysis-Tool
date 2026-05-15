import glob
import os
import re
import datetime
import xml.etree.ElementTree as ET

try:
    from backend.knowledge.test_context import detect_instrument
    from backend.knowledge.test_context import get_instrument_device
    from backend.knowledge.test_context import get_engineering_hint
    from backend.knowledge.test_context import extract_section
    from backend.knowledge.test_context import extract_signal
    from backend.knowledge.test_context import build_nominal_range
except Exception:
    def detect_instrument(test_name):
        text = str(test_name or "").upper()
        if "DMM" in text:
            return "DMM"
        if "OSC" in text or "SCOPE" in text:
            return "OSC"
        if "XCP" in text:
            return "XCP"
        if "CAN" in text:
            return "CAN"
        if "LIN" in text:
            return "LIN"
        if "ETH" in text or "ETHERNET" in text:
            return "ETH"
        if "POWER" in text or "VIN" in text or "VOUT" in text:
            return "POWER"
        return "UNKNOWN"

    def get_instrument_device(instrument):
        mapping = {
            "DMM": "DMM",
            "OSC": "Oscilloscope",
            "POWER": "Power Supply",
            "XCP": "XCP over CAN",
            "CAN": "CAN Interface",
            "LIN": "LIN Interface",
            "ETH": "Ethernet Interface",
        }
        return mapping.get(str(instrument or "UNKNOWN"), "-")

    def get_engineering_hint(instrument):
        return "仅为工程风险提示，不作为故障结论。"

    def extract_section(test_name):
        match_obj = re.match(r"^\s*(\d+(?:\.\d+)+)", str(test_name or ""))
        if match_obj:
            return match_obj.group(1)
        return ""

    def extract_signal(test_name):
        text = str(test_name or "")
        text = re.sub(r"^\s*\d+(?:\.\d+)+\s*", "", text)
        text = re.sub(r"\((DMM|OSC|XCP|CAN|LIN|ETH|POWER)\)", "", text, flags=re.I)
        return text.strip()

    def build_nominal_range(lolim, hilim, unit):
        lo = str(lolim or "").strip()
        hi = str(hilim or "").strip()
        u = str(unit or "").strip()
        if lo and hi:
            return (lo + " ~ " + hi + " " + u).strip()
        if lo:
            return (">= " + lo + " " + u).strip()
        if hi:
            return ("<= " + hi + " " + u).strip()
        return "-"


PASS_TEXTS = set(["PASS", "PASSED", "OK", "SUCCESS", "TRUE"])
FAIL_TEXTS = set(["FAIL", "FAILED", "NG", "FALSE"])


def local_name(tag):
    if not tag:
        return ""
    return str(tag).split("}", 1)[-1].upper()


def iter_by_tag(root, tag_name):
    target = str(tag_name or "").upper()
    for node in root.iter():
        if local_name(node.tag) == target:
            yield node


def find_first(root, tag_name):
    for node in iter_by_tag(root, tag_name):
        return node
    return None


def get_attr(node, *names):
    if node is None:
        return ""

    lower_map = {}
    for key in node.attrib:
        lower_map[str(key).lower()] = node.attrib.get(key)

    for name in names:
        if name in node.attrib:
            return str(node.attrib.get(name) or "")
        low_name = str(name).lower()
        if low_name in lower_map:
            return str(lower_map.get(low_name) or "")

    return ""


def normalize_raw_status(status):
    text = str(status or "").strip().upper()
    if text in PASS_TEXTS:
        return "PASS"
    if text in FAIL_TEXTS:
        return "FAIL"
    return "中断"


def is_abnormal_status(status):
    return normalize_raw_status(status) == "中断"


def format_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return ""

    match_obj = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", text)
    if match_obj:
        year = match_obj.group(1)
        month = match_obj.group(2)
        day = match_obj.group(3)
        hour = match_obj.group(4)
        minute = match_obj.group(5)
        second = match_obj.group(6)
        return year + "-" + month + "-" + day + " " + hour + ":" + minute + ":" + second

    return text


def get_file_time(xml_file_path):
    try:
        ts_value = os.path.getmtime(xml_file_path)
        time_text = datetime.fromtimestamp(ts_value).strftime("%Y-%m-%d %H:%M:%S")
        return time_text, ts_value
    except Exception:
        return "", 0.0


def get_relative_path(xml_file_path, log_dir=None):
    try:
        if log_dir:
            return os.path.relpath(xml_file_path, log_dir).replace("\\", "/")
    except Exception:
        pass

    return os.path.basename(xml_file_path)


def looks_like_model(text):
    value = str(text or "").strip()
    return re.match(r"^E\d{7}$", value, re.I) is not None


def get_model_from_sn(sn):
    text = str(sn or "").strip()
    match_obj = re.search(r"(E\d{7})", text, re.I)
    if match_obj:
        return match_obj.group(1).upper()
    return "UNKNOWN"


def extract_sn_from_filename(filename):
    base = os.path.basename(str(filename or ""))

    parts = base.split("_")
    for part in parts:
        if re.search(r"E\d{7}", part, re.I) and len(part) >= 8:
            return os.path.splitext(part)[0]

    match_obj = re.search(r"(E\d{7}[A-Za-z0-9]+)", base, re.I)
    if match_obj:
        return match_obj.group(1)

    return ""


def extract_path_metadata(xml_file_path, log_dir=None):
    relative_path = get_relative_path(xml_file_path, log_dir)
    parts = relative_path.replace("\\", "/").split("/")

    test_mode = "Unknown"
    model = "UNKNOWN"
    date_folder = ""

    for index in range(len(parts)):
        part = parts[index]
        low = part.lower()

        if low == "online" or low == "offline":
            if low == "online":
                test_mode = "Online"
            else:
                test_mode = "Offline"

            if index + 1 < len(parts):
                if looks_like_model(parts[index + 1]):
                    model = parts[index + 1].upper()

            if index + 2 < len(parts):
                date_folder = parts[index + 2]

            break

    if model == "UNKNOWN":
        for part in parts:
            if looks_like_model(part):
                model = part.upper()
                break

    return {
        "test_mode": test_mode,
        "model": model,
        "date_folder": date_folder,
        "relative_path": relative_path,
    }


def build_parent_map(root):
    parent_map = {}
    for parent in root.iter():
        for child in list(parent):
            parent_map[child] = parent
    return parent_map


def get_parent_group(node, parent_map):
    current = node
    while current in parent_map:
        current = parent_map[current]
        if local_name(current.tag) == "GROUP":
            return get_attr(current, "NAME", "Name", "name")
    return ""


def get_path_groups(node, parent_map):
    groups = []
    current = node
    while current in parent_map:
        current = parent_map[current]
        if local_name(current.tag) == "GROUP":
            name = get_attr(current, "NAME", "Name", "name")
            if name:
                groups.append(name)
    groups.reverse()
    return groups


def parse_test_nodes(root, parent_map):
    items = []

    for node in iter_by_tag(root, "TEST"):
        name = get_attr(node, "NAME", "Name", "name")
        raw_status = get_attr(node, "STATUS", "Status", "status")
        business_status = normalize_raw_status(raw_status)

        value = get_attr(node, "VALUE", "Value", "value")
        unit = get_attr(node, "UNIT", "Unit", "unit")
        lolim = get_attr(node, "LOLIM", "LoLim", "LO_LIMIT", "LOW", "low")
        hilim = get_attr(node, "HILIM", "HiLim", "HI_LIMIT", "HIGH", "high")
        rule = get_attr(node, "RULE", "Rule", "rule")
        datatype = get_attr(node, "DATATYPE", "DataType", "datatype")
        timestamp = get_attr(node, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time")
        timestamp = format_timestamp(timestamp)

        instrument = detect_instrument(name)

        item = {
            "name": name,
            "status": raw_status,
            "business_status": business_status,
            "result": business_status,
            "value": value,
            "unit": unit,
            "lolim": lolim,
            "hilim": hilim,
            "rule": rule,
            "datatype": datatype,
            "timestamp": timestamp,
            "section": extract_section(name),
            "signal": extract_signal(name),
            "reference": "GND" if "GND" in str(name).upper() else "",
            "instrument": instrument,
            "instrument_device": get_instrument_device(instrument),
            "nominal_range": build_nominal_range(lolim, hilim, unit),
            "raw_name": name,
            "group": get_parent_group(node, parent_map),
            "groups": get_path_groups(node, parent_map),
            "engineering_hint": get_engineering_hint(instrument),
        }

        items.append(item)

    return items


def parse_abnormal_groups(root):
    abnormal = []
    for node in iter_by_tag(root, "GROUP"):
        name = get_attr(node, "NAME", "Name", "name")
        status = get_attr(node, "STATUS", "Status", "status")
        business_status = normalize_raw_status(status)
        if business_status == "中断":
            abnormal.append({"name": name, "status": status, "business_status": "中断"})
    return abnormal


def get_station_from_xml(root):
    factory = find_first(root, "FACTORY")
    product = find_first(root, "PRODUCT")

    tester = get_attr(factory, "TESTER", "Tester", "tester")
    product_name = get_attr(product, "NAME", "Name", "name")
    factory_name = get_attr(factory, "NAME", "Name", "name")
    line = get_attr(factory, "LINE", "Line", "line")
    user = get_attr(factory, "USER", "User", "user")

    station = "FCT"
    if tester:
        parts = tester.split("_")
        if parts:
            station = parts[-1] or "FCT"

    return station, tester, product_name, factory_name, line, user


def build_sn_aliases(sn):
    text = str(sn or "").strip()
    aliases = set()

    if text:
        aliases.add(text)
        aliases.add(text.upper())

        if len(text) > 8:
            aliases.add(text[-8:])
        if len(text) > 10:
            aliases.add(text[-10:])
        if len(text) > 12:
            aliases.add(text[-12:])

    return sorted(list(aliases))


def decide_overall_result(raw_status, total_tests, passed_tests, failed_tests, interrupted_tests, skipped_tests):
    raw_norm = normalize_raw_status(raw_status)

    if total_tests <= 0:
        return "中断"

    completed_tests = passed_tests + failed_tests

    if interrupted_tests > 0:
        return "中断"

    if skipped_tests > 0:
        return "中断"

    if total_tests > completed_tests:
        return "中断"

    if raw_norm == "中断":
        return "中断"

    if failed_tests > 0:
        return "FAIL"

    if passed_tests == total_tests:
        return "PASS"

    return "中断"


def parse_fct_xml(xml_file_path, log_dir=None):
    meta = extract_path_metadata(xml_file_path, log_dir)
    file_time, file_ts = get_file_time(xml_file_path)
    source_file = os.path.basename(xml_file_path)

    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        parent_map = build_parent_map(root)

        batch = find_first(root, "BATCH")
        panel = find_first(root, "PANEL")
        dut = find_first(root, "DUT")

        sn = get_attr(dut, "ID", "Id", "id")
        if not sn:
            sn = extract_sn_from_filename(source_file)

        model = meta.get("model", "UNKNOWN")
        if model == "UNKNOWN":
            model = get_model_from_sn(sn)

        batch_time = format_timestamp(get_attr(batch, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time"))
        panel_time = format_timestamp(get_attr(panel, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time"))
        dut_time = format_timestamp(get_attr(dut, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time"))

        panel_status_raw = get_attr(panel, "STATUS", "Status", "status")
        dut_status_raw = get_attr(dut, "STATUS", "Status", "status")
        raw_result = dut_status_raw or panel_status_raw

        station, tester, product_name, factory_name, line, user = get_station_from_xml(root)
        raw_items = parse_test_nodes(root, parent_map)

        total_tests = len(raw_items)
        passed_tests = 0
        failed_tests = 0
        interrupted_tests = 0
        skipped_tests = 0

        for item in raw_items:
            item_status = item.get("business_status")
            if item_status == "PASS":
                passed_tests += 1
            elif item_status == "FAIL":
                failed_tests += 1
            else:
                interrupted_tests += 1

            raw_item_status = str(item.get("status", "")).strip().upper()
            if raw_item_status == "SKIP" or raw_item_status == "SKIPPED":
                skipped_tests += 1

        fail_items = []
        interrupted_items = []

        for item in raw_items:
            if item.get("business_status") == "FAIL":
                fail_items.append(item)
            elif item.get("business_status") == "中断":
                interrupted_items.append(item)

        business_result = decide_overall_result(
            raw_result,
            total_tests,
            passed_tests,
            failed_tests,
            interrupted_tests,
            skipped_tests,
        )

        test_time = dut_time or panel_time or batch_time or file_time

        panel_testtime = get_attr(panel, "TESTTIME", "TestTime", "testtime")
        dut_testtime = get_attr(dut, "TESTTIME", "TestTime", "testtime")

        return {
            "sn": sn,
            "sn_aliases": build_sn_aliases(sn),
            "model": model,
            "factory": factory_name,
            "line": line,
            "user": user,
            "test_mode": meta.get("test_mode", "Unknown"),
            "date_folder": meta.get("date_folder", ""),
            "relative_path": meta.get("relative_path", ""),
            "station": station,
            "tester": tester,
            "product": product_name,
            "result": business_result,
            "business_result": business_result,
            "raw_result": raw_result,
            "panel_status": normalize_raw_status(panel_status_raw),
            "panel_status_raw": panel_status_raw,
            "dut_status": normalize_raw_status(dut_status_raw),
            "dut_status_raw": dut_status_raw,
            "fail_items": fail_items,
            "interrupted_items": interrupted_items,
            "raw_items": raw_items,
            "time": test_time,
            "batch_time": batch_time,
            "panel_time": panel_time,
            "dut_time": dut_time,
            "test_time": test_time,
            "panel_testtime": panel_testtime,
            "dut_testtime": dut_testtime,
            "source_file": source_file,
            "source_path": xml_file_path,
            "file_mtime": file_time,
            "file_mtime_ts": file_ts,
            "total_tests": total_tests,
            "failed_tests": failed_tests,
            "passed_tests": passed_tests,
            "interrupted_tests": interrupted_tests,
            "skipped_tests": skipped_tests,
            "parse_error": "",
        }

    except Exception as exc:
        sn = extract_sn_from_filename(source_file)
        model = meta.get("model", "UNKNOWN")

        if model == "UNKNOWN":
            model = get_model_from_sn(sn)

        return {
            "sn": sn,
            "sn_aliases": build_sn_aliases(sn),
            "model": model,
            "test_mode": meta.get("test_mode", "Unknown"),
            "date_folder": meta.get("date_folder", ""),
            "relative_path": meta.get("relative_path", ""),
            "station": "FCT",
            "tester": "",
            "product": "",
            "result": "中断",
            "business_result": "中断",
            "raw_result": "PARSE_ERROR",
            "panel_status": "中断",
            "panel_status_raw": "",
            "dut_status": "中断",
            "dut_status_raw": "",
            "fail_items": [],
            "interrupted_items": [],
            "raw_items": [],
            "time": file_time,
            "batch_time": "",
            "panel_time": "",
            "dut_time": "",
            "test_time": file_time,
            "source_file": source_file,
            "source_path": xml_file_path,
            "file_mtime": file_time,
            "file_mtime_ts": file_ts,
            "total_tests": 0,
            "failed_tests": 0,
            "passed_tests": 0,
            "interrupted_tests": 0,
            "skipped_tests": 0,
            "parse_error": str(exc),
        }


def load_all_fct_records(log_dir):
    pattern = os.path.join(log_dir, "**", "*.xml")
    files = glob.glob(pattern, recursive=True)

    records = []
    for path in files:
        records.append(parse_fct_xml(path, log_dir=log_dir))

    records.sort(key=lambda item: item.get("file_mtime_ts", 0), reverse=True)
    return records


def load_all_fct_xml(log_dir):
    return load_all_fct_records(log_dir)


def find_latest_record_by_sn(records, query_sn):
    query = str(query_sn or "").strip().upper()

    if not query:
        return None

    matched = []

    for record in records:
        sn = str(record.get("sn", "")).upper()

        aliases = []
        for alias in record.get("sn_aliases", []):
            aliases.append(str(alias).upper())

        source_file = str(record.get("source_file", "")).upper()
        relative_path = str(record.get("relative_path", "")).upper()

        if query == sn:
            matched.append(record)
            continue

        if query in aliases:
            matched.append(record)
            continue

        if sn.endswith(query):
            matched.append(record)
            continue

        if query in source_file:
            matched.append(record)
            continue

        if query in relative_path:
            matched.append(record)
            continue

    if not matched:
        return None

    matched.sort(key=lambda item: item.get("file_mtime_ts", 0), reverse=True)
    return matched[0]
