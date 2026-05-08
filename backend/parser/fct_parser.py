import os
import re
import glob
import xml.etree.ElementTree as ET
from datetime import datetime


PASS_STATUS_SET = {
    "PASSED",
    "PASS"
}

FAIL_STATUS_SET = {
    "FAILED",
    "FAIL"
}

PAUSED_STATUS_SET = {
    "PAUSED",
    "PAUSE",
    "SUSPENDED",
    "SUSPEND"
}

INTERRUPTED_STATUS_SET = {
    "TERMINATED",
    "TERMINATE",
    "ABORTED",
    "ABORT",
    "STOPPED",
    "STOP",
    "CANCELLED",
    "CANCELED",
    "INTERRUPTED",
    "INTERRUPT"
}

ERROR_STATUS_SET = {
    "ERROR",
    "RUNTIME_ERROR",
    "EXCEPTION"
}

SKIPPED_STATUS_SET = {
    "SKIPPED",
    "SKIP"
}

DONE_STATUS_SET = {
    "DONE"
}


KNOWN_MODEL_PREFIXES = [
    "E3002781",
    "E3002624",
    "E3002609",
    "E3002752",
    "E3002757"
]


def local_name(tag):
    """
    Remove XML namespace from tag name.

    Example:
    {namespace}DUT -> DUT
    DUT            -> DUT
    """
    if tag is None:
        return ""

    text = str(tag)

    if "}" in text:
        return text.split("}", 1)[1]

    return text


def iter_by_tag(root, tag_name):
    """
    Iterate XML nodes by local tag name.
    This is more robust than root.findall('.//TAG') when namespace exists.
    """
    wanted = str(tag_name).upper()

    for node in root.iter():
        if local_name(node.tag).upper() == wanted:
            yield node


def find_first(root, tag_name):
    """
    Find first XML node by local tag name.
    """
    for node in iter_by_tag(root, tag_name):
        return node

    return None


def normalize_status(status):
    """
    Normalize raw FTS/TestStand status into dashboard status.

    Output:
    PASS
    FAIL
    PAUSED
    INTERRUPTED
    ERROR
    SKIPPED
    DONE
    UNKNOWN
    """
    if status is None:
        return "UNKNOWN"

    s = str(status).strip().upper()

    if not s:
        return "UNKNOWN"

    if s in PASS_STATUS_SET:
        return "PASS"

    if s in FAIL_STATUS_SET:
        return "FAIL"

    if s in PAUSED_STATUS_SET:
        return "PAUSED"

    if s in INTERRUPTED_STATUS_SET:
        return "INTERRUPTED"

    if s in ERROR_STATUS_SET:
        return "ERROR"

    if s in SKIPPED_STATUS_SET:
        return "SKIPPED"

    if s in DONE_STATUS_SET:
        return "DONE"

    return s


def is_abnormal_status(status):
    return status in {
        "FAIL",
        "PAUSED",
        "INTERRUPTED",
        "ERROR"
    }


def format_timestamp(ts):
    """
    Convert XML timestamp to readable format.

    Example:
    2026-05-05T10:39:18.768+08:00 -> 2026-05-05 10:39:18
    """
    if not ts:
        return ""

    text = str(ts).strip()

    try:
        text = re.sub(r"([+-]\d{2}:\d{2}|Z)$", "", text)
        text = text.split(".")[0]
        return text.replace("T", " ")
    except Exception:
        return str(ts)


def get_file_time(xml_file_path):
    try:
        file_mtime_ts = os.path.getmtime(xml_file_path)
        file_mtime = datetime.fromtimestamp(file_mtime_ts).strftime("%Y-%m-%d %H:%M:%S")
        return file_mtime, file_mtime_ts
    except Exception:
        return "", 0


def get_relative_path(xml_file_path, log_dir):
    try:
        rel = os.path.relpath(xml_file_path, log_dir)
        return rel.replace("\\", "/")
    except Exception:
        return os.path.basename(xml_file_path)


def looks_like_model(text):
    if not text:
        return False

    value = str(text).strip().upper()

    if value in KNOWN_MODEL_PREFIXES:
        return True

    if re.match(r"^E\d{7}$", value):
        return True

    return False


def get_model_from_sn(sn):
    text = str(sn or "").strip().upper()

    for prefix in KNOWN_MODEL_PREFIXES:
        if text.startswith(prefix):
            return prefix

    match = re.match(r"^(E\d{7})", text)
    if match:
        return match.group(1)

    return ""


def extract_path_metadata(xml_file_path, log_dir):
    """
    Extract production path metadata.

    Supported path examples:
    data/logs/Online/E3002781/20260507/xxx.xml
    data/logs/Offline/E3002624/20260507/xxx.xml

    Output:
    test_mode    -> Online / Offline / Unknown
    model        -> E3002781 / E3002624 / ...
    date_folder  -> date directory after model
    relative_path
    """
    relative_path = get_relative_path(xml_file_path, log_dir)
    parts = relative_path.replace("\\", "/").split("/")

    test_mode = "Unknown"
    model = ""
    date_folder = ""

    lower_parts = [p.lower() for p in parts]

    mode_index = -1

    for index, part in enumerate(lower_parts):
        if part == "online":
            test_mode = "Online"
            mode_index = index
            break

        if part == "offline":
            test_mode = "Offline"
            mode_index = index
            break

    if mode_index >= 0:
        if len(parts) > mode_index + 1:
            candidate_model = parts[mode_index + 1].strip()
            if looks_like_model(candidate_model):
                model = candidate_model.upper()

        if len(parts) > mode_index + 2:
            date_folder = parts[mode_index + 2].strip()

    # Fallback: find model anywhere in path
    if not model:
        for part in parts:
            if looks_like_model(part):
                model = part.strip().upper()
                break

    return {
        "test_mode": test_mode,
        "model": model,
        "date_folder": date_folder,
        "relative_path": relative_path
    }


def extract_sn_from_filename(filename):
    """
    Extract SN from FTS filename.

    Example:
    F_Fts_PEU_G49_FCT6_E3002781AFV75236898002K50400241_20260505104457494_20265524457582.xml
    """
    base = os.path.basename(filename)

    match = re.search(r"FCT\d*_([^_]+)_", base, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    match = re.search(r"(E[A-Za-z0-9]{20,50})", base)
    if match:
        return match.group(1).strip()

    return ""


def get_station_from_xml(root):
    factory = find_first(root, "FACTORY")
    product = find_first(root, "PRODUCT")

    tester = ""
    product_name = ""

    if factory is not None:
        tester = factory.attrib.get("TESTER", "").strip()

    if product is not None:
        product_name = product.attrib.get("NAME", "").strip()

    if tester:
        parts = tester.split("_")
        if parts:
            return parts[-1], tester

    if product_name:
        return product_name, tester

    return "FCT", tester


def build_parent_map(root):
    return {
        child: parent
        for parent in root.iter()
        for child in parent
    }


def get_parent_group(node, parent_map):
    parent = parent_map.get(node)

    while parent is not None:
        if local_name(parent.tag).upper() == "GROUP":
            return parent

        parent = parent_map.get(parent)

    return None


def get_path_groups(node, parent_map):
    groups = []
    parent = parent_map.get(node)

    while parent is not None:
        if local_name(parent.tag).upper() == "GROUP":
            name = parent.attrib.get("NAME", "").strip()
            if name:
                groups.append(name)

        parent = parent_map.get(parent)

    groups.reverse()
    return groups


def parse_test_nodes(root, parent_map):
    raw_items = []
    fail_items = []
    paused_items = []
    interrupted_items = []
    error_items = []

    test_nodes = list(iter_by_tag(root, "TEST"))

    for index, test in enumerate(test_nodes, start=1):
        group = get_parent_group(test, parent_map)
        group_path = get_path_groups(test, parent_map)

        test_name = test.attrib.get("NAME", "").strip()
        test_status_raw = test.attrib.get("STATUS", "").strip()
        test_status = normalize_status(test_status_raw)

        group_name = ""
        group_type = ""
        group_status_raw = ""
        group_status = ""
        group_timestamp = ""

        if group is not None:
            group_name = group.attrib.get("NAME", "").strip()
            group_type = group.attrib.get("TYPE", "").strip()
            group_status_raw = group.attrib.get("STATUS", "").strip()
            group_status = normalize_status(group_status_raw)
            group_timestamp = format_timestamp(group.attrib.get("TIMESTAMP", ""))

        item_name = test_name or group_name or "TEST_" + str(index)

        item = {
            "index": index,
            "name": item_name,
            "result": test_status,
            "status_raw": test_status_raw,

            "value": test.attrib.get("VALUE", ""),
            "unit": test.attrib.get("UNIT", ""),
            "hi_limit": test.attrib.get("HILIM", ""),
            "lo_limit": test.attrib.get("LOLIM", ""),
            "rule": test.attrib.get("RULE", ""),
            "datatype": test.attrib.get("DATATYPE", ""),
            "description": test.attrib.get("DESCRIPTION", ""),
            "target": test.attrib.get("TARGET", ""),

            "group_name": group_name,
            "group_type": group_type,
            "group_status": group_status,
            "group_status_raw": group_status_raw,
            "group_timestamp": group_timestamp,
            "group_path": " / ".join(group_path)
        }

        raw_items.append(item)

        if test_status == "FAIL":
            fail_items.append(item_name)
        elif test_status == "PAUSED":
            paused_items.append(item_name)
        elif test_status == "INTERRUPTED":
            interrupted_items.append(item_name)
        elif test_status == "ERROR":
            error_items.append(item_name)

    return raw_items, fail_items, paused_items, interrupted_items, error_items


def parse_abnormal_groups(root):
    abnormal_groups = []
    failed_groups = []
    paused_groups = []
    interrupted_groups = []
    error_groups = []

    for group in iter_by_tag(root, "GROUP"):
        raw_status = group.attrib.get("STATUS", "").strip()
        status = normalize_status(raw_status)

        if not is_abnormal_status(status):
            continue

        name = group.attrib.get("NAME", "").strip()

        if not name:
            continue

        if name in {"MainSequence Callback"}:
            continue

        item = {
            "name": name,
            "type": group.attrib.get("TYPE", ""),
            "stepgroup": group.attrib.get("STEPGROUP", ""),
            "timestamp": format_timestamp(group.attrib.get("TIMESTAMP", "")),
            "status": status,
            "status_raw": raw_status
        }

        abnormal_groups.append(item)

        if status == "FAIL":
            failed_groups.append(item)
        elif status == "PAUSED":
            paused_groups.append(item)
        elif status == "INTERRUPTED":
            interrupted_groups.append(item)
        elif status == "ERROR":
            error_groups.append(item)

    return {
        "abnormal_groups": abnormal_groups,
        "failed_groups": failed_groups,
        "paused_groups": paused_groups,
        "interrupted_groups": interrupted_groups,
        "error_groups": error_groups
    }


def decide_overall_result(
    dut_status,
    panel_status,
    fail_items,
    paused_items,
    interrupted_items,
    error_items,
    group_info,
    raw_items
):
    if dut_status == "INTERRUPTED" or panel_status == "INTERRUPTED":
        return "INTERRUPTED"

    if dut_status == "PAUSED" or panel_status == "PAUSED":
        return "PAUSED"

    if dut_status == "ERROR" or panel_status == "ERROR":
        return "ERROR"

    if fail_items:
        return "FAIL"

    if interrupted_items:
        return "INTERRUPTED"

    if paused_items:
        return "PAUSED"

    if error_items:
        return "ERROR"

    if group_info.get("interrupted_groups"):
        return "INTERRUPTED"

    if group_info.get("paused_groups"):
        return "PAUSED"

    if group_info.get("error_groups"):
        return "ERROR"

    if group_info.get("failed_groups"):
        return "FAIL"

    if dut_status == "PASS":
        return "PASS"

    if panel_status == "PASS":
        return "PASS"

    if raw_items and all(item.get("result") == "PASS" for item in raw_items):
        return "PASS"

    return "UNKNOWN"


def build_sn_aliases(sn):
    aliases = []

    if sn:
        aliases.append(sn)

        if len(sn) >= 8:
            aliases.append(sn[-8:])

        if len(sn) >= 10:
            aliases.append(sn[-10:])

        if len(sn) >= 12:
            aliases.append(sn[-12:])

    return list(dict.fromkeys([x for x in aliases if x]))


def parse_fct_xml(xml_file_path, log_dir=None):
    if log_dir is None:
        log_dir = os.path.dirname(xml_file_path)

    file_mtime, file_mtime_ts = get_file_time(xml_file_path)
    path_meta = extract_path_metadata(xml_file_path, log_dir)

    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        parent_map = build_parent_map(root)

        batch_timestamp = format_timestamp(root.attrib.get("TIMESTAMP", ""))

        product = find_first(root, "PRODUCT")
        panel = find_first(root, "PANEL")
        dut = find_first(root, "DUT")

        station, tester = get_station_from_xml(root)

        product_name = ""
        if product is not None:
            product_name = product.attrib.get("NAME", "").strip()

        sn = ""

        if dut is not None:
            sn = dut.attrib.get("ID", "").strip()

        if not sn:
            sn = extract_sn_from_filename(xml_file_path)

        model = path_meta.get("model", "")

        if not model:
            model = get_model_from_sn(sn)

        panel_status = "UNKNOWN"
        panel_status_raw = ""
        panel_timestamp = ""
        panel_testtime = ""

        if panel is not None:
            panel_status_raw = panel.attrib.get("STATUS", "").strip()
            panel_status = normalize_status(panel_status_raw)
            panel_timestamp = format_timestamp(panel.attrib.get("TIMESTAMP", ""))
            panel_testtime = panel.attrib.get("TESTTIME", "")

        dut_status = "UNKNOWN"
        dut_status_raw = ""
        dut_timestamp = ""
        dut_testtime = ""

        if dut is not None:
            dut_status_raw = dut.attrib.get("STATUS", "").strip()
            dut_status = normalize_status(dut_status_raw)
            dut_timestamp = format_timestamp(dut.attrib.get("TIMESTAMP", ""))
            dut_testtime = dut.attrib.get("TESTTIME", "")

        raw_items, fail_items, paused_items, interrupted_items, error_items = parse_test_nodes(root, parent_map)
        group_info = parse_abnormal_groups(root)

        result = decide_overall_result(
            dut_status=dut_status,
            panel_status=panel_status,
            fail_items=fail_items,
            paused_items=paused_items,
            interrupted_items=interrupted_items,
            error_items=error_items,
            group_info=group_info,
            raw_items=raw_items
        )

        if result == "INTERRUPTED" and not interrupted_items:
            for group in group_info.get("interrupted_groups", []):
                if group["name"] not in interrupted_items:
                    interrupted_items.append(group["name"])

        if result == "PAUSED" and not paused_items:
            for group in group_info.get("paused_groups", []):
                if group["name"] not in paused_items:
                    paused_items.append(group["name"])

        if result == "FAIL" and not fail_items:
            for group in group_info.get("failed_groups", []):
                if group["name"] not in fail_items:
                    fail_items.append(group["name"])

        if result == "ERROR" and not error_items:
            for group in group_info.get("error_groups", []):
                if group["name"] not in error_items:
                    error_items.append(group["name"])

        source_file = os.path.basename(xml_file_path)

        return {
            "sn": sn,
            "sn_aliases": build_sn_aliases(sn),

            "model": model or "-",
            "test_mode": path_meta.get("test_mode", "Unknown"),
            "date_folder": path_meta.get("date_folder", ""),
            "relative_path": path_meta.get("relative_path", source_file),

            "station": station,
            "tester": tester,
            "product": product_name,

            "result": result,

            "panel_status": panel_status,
            "panel_status_raw": panel_status_raw,

            "dut_status": dut_status,
            "dut_status_raw": dut_status_raw,

            "fail_items": fail_items,
            "paused_items": paused_items,
            "interrupted_items": interrupted_items,
            "error_items": error_items,

            "failed_groups": group_info.get("failed_groups", []),
            "paused_groups": group_info.get("paused_groups", []),
            "interrupted_groups": group_info.get("interrupted_groups", []),
            "error_groups": group_info.get("error_groups", []),
            "abnormal_groups": group_info.get("abnormal_groups", []),

            "raw_items": raw_items,

            "time": dut_timestamp or panel_timestamp or batch_timestamp,
            "batch_time": batch_timestamp,
            "panel_time": panel_timestamp,
            "dut_time": dut_timestamp,
            "test_time": dut_testtime or panel_testtime,

            "source_file": source_file,
            "source_path": xml_file_path,
            "file_mtime": file_mtime,
            "file_mtime_ts": file_mtime_ts,

            "total_tests": len(raw_items),
            "failed_tests": len([item for item in raw_items if item["result"] == "FAIL"]),
            "passed_tests": len([item for item in raw_items if item["result"] == "PASS"]),
            "paused_tests": len([item for item in raw_items if item["result"] == "PAUSED"]),
            "interrupted_tests": len([item for item in raw_items if item["result"] == "INTERRUPTED"]),
            "error_tests": len([item for item in raw_items if item["result"] == "ERROR"]),
            "skipped_tests": len([item for item in raw_items if item["result"] == "SKIPPED"])
        }

    except Exception as e:
        source_file = os.path.basename(xml_file_path)
        fallback_sn = extract_sn_from_filename(source_file)
        fallback_model = path_meta.get("model", "") or get_model_from_sn(fallback_sn) or "-"

        return {
            "sn": fallback_sn,
            "sn_aliases": build_sn_aliases(fallback_sn),

            "model": fallback_model,
            "test_mode": path_meta.get("test_mode", "Unknown"),
            "date_folder": path_meta.get("date_folder", ""),
            "relative_path": path_meta.get("relative_path", source_file),

            "station": "FCT",
            "tester": "",
            "product": "FCT",

            "result": "PARSE_ERROR",

            "panel_status": "UNKNOWN",
            "panel_status_raw": "",

            "dut_status": "UNKNOWN",
            "dut_status_raw": "",

            "fail_items": [],
            "paused_items": [],
            "interrupted_items": [],
            "error_items": [],

            "failed_groups": [],
            "paused_groups": [],
            "interrupted_groups": [],
            "error_groups": [],
            "abnormal_groups": [],

            "raw_items": [],

            "time": "",
            "batch_time": "",
            "panel_time": "",
            "dut_time": "",
            "test_time": "",

            "source_file": source_file,
            "source_path": xml_file_path,
            "file_mtime": file_mtime,
            "file_mtime_ts": file_mtime_ts,

            "total_tests": 0,
            "failed_tests": 0,
            "passed_tests": 0,
            "paused_tests": 0,
            "interrupted_tests": 0,
            "error_tests": 0,
            "skipped_tests": 0,

            "error": str(e)
        }


def load_all_fct_records(log_dir):
    """
    Recursively scan all XML files under log_dir.

    Supported:
    data/logs/*.xml
    data/logs/Online/Model/Date/*.xml
    data/logs/Offline/Model/Date/*.xml
    """
    records = []

    xml_pattern = os.path.join(log_dir, "**", "*.xml")
    xml_files = glob.glob(xml_pattern, recursive=True)

    for xml_file in xml_files:
        record = parse_fct_xml(xml_file, log_dir=log_dir)
        records.append(record)

    records.sort(
        key=lambda item: item.get("file_mtime_ts", 0),
        reverse=True
    )

    return records


def load_all_fct_xml(log_dir):
    """
    Compatibility function for older app.py versions.
    """
    records = load_all_fct_records(log_dir)

    data = {}

    for index, record in enumerate(records):
        key = record.get("relative_path") or record.get("source_file") or record.get("sn") or "UNKNOWN_" + str(index)
        data[key] = record

    return data


def find_latest_record_by_sn(records, query_sn):
    """
    Compatibility SN search helper.

    Supports:
    full SN
    SN suffix
    aliases
    filename fragment
    relative path fragment
    """
    if not query_sn:
        return None

    query = str(query_sn).strip().upper()

    if not query:
        return None

    matched = []

    for record in records:
        sn = str(record.get("sn", "")).strip().upper()
        source_file = str(record.get("source_file", "")).strip().upper()
        relative_path = str(record.get("relative_path", "")).strip().upper()

        aliases = [
            str(alias).strip().upper()
            for alias in record.get("sn_aliases", [])
            if alias
        ]

        if query == sn:
            matched.append(record)
            continue

        if query in aliases:
            matched.append(record)
            continue

        if sn and sn.endswith(query):
            matched.append(record)
            continue

        if source_file and query in source_file:
            matched.append(record)
            continue

        if relative_path and query in relative_path:
            matched.append(record)
            continue

    if not matched:
        return None

    matched.sort(
        key=lambda item: item.get("file_mtime_ts", 0),
        reverse=True
    )

    return matched[0]