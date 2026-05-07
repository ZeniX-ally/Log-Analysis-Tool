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

SKIP_STATUS_SET = {
    "SKIPPED",
    "SKIP"
}

DONE_STATUS_SET = {
    "DONE"
}


def normalize_status(status):
    """
    将 FTS/TestStand XML 状态统一成前端和后端通用状态。

    输出：
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

    if s in SKIP_STATUS_SET:
        return "SKIPPED"

    if s in DONE_STATUS_SET:
        return "DONE"

    return s


def is_abnormal_status(status):
    """
    判断是否属于非 PASS 状态。
    用于统计异常测试项。
    """

    return status in {
        "FAIL",
        "PAUSED",
        "INTERRUPTED",
        "ERROR"
    }


def format_timestamp(ts):
    """
    把 2026-05-05T10:39:18.768+08:00 转成 2026-05-05 10:39:18。
    如果格式异常，则原样返回。
    """

    if not ts:
        return ""

    ts = str(ts).strip()

    try:
        no_tz = re.sub(r"([+-]\d{2}:\d{2}|Z)$", "", ts)
        no_ms = no_tz.split(".")[0]
        return no_ms.replace("T", " ")
    except Exception:
        return ts


def get_file_time(xml_file_path):
    """
    读取文件修改时间。
    """

    try:
        file_mtime_ts = os.path.getmtime(xml_file_path)
        file_mtime = datetime.fromtimestamp(file_mtime_ts).strftime("%Y-%m-%d %H:%M:%S")
        return file_mtime, file_mtime_ts
    except Exception:
        return "", 0


def extract_sn_from_filename(filename):
    """
    从文件名兜底提取 SN。

    示例：
    F_Fts_PEU_G49_FCT6_E3002781AFV75236898002K50400241_20260505104457494_20265524457582.xml
    """

    base = os.path.basename(filename)

    match = re.search(r"FCT6_([^_]+)_", base, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    match = re.search(r"(E[A-Za-z0-9]{20,40})", base)
    if match:
        return match.group(1).strip()

    return ""


def get_station_from_xml(root):
    """
    从 FACTORY TESTER 或 PRODUCT NAME 获取站点信息。
    """

    factory = root.find(".//FACTORY")
    product = root.find(".//PRODUCT")

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
    """
    建立 child -> parent 映射。
    用于从 TEST 反查上级 GROUP。
    """

    return {
        child: parent
        for parent in root.iter()
        for child in parent
    }


def get_parent_group(test_node, parent_map):
    """
    获取 TEST 的上级 GROUP。
    """

    parent = parent_map.get(test_node)

    while parent is not None:
        if parent.tag == "GROUP":
            return parent
        parent = parent_map.get(parent)

    return None


def get_path_groups(node, parent_map):
    """
    获取当前 TEST 所在 GROUP 路径。
    """

    groups = []
    parent = parent_map.get(node)

    while parent is not None:
        if parent.tag == "GROUP":
            name = parent.attrib.get("NAME", "").strip()
            if name:
                groups.append(name)
        parent = parent_map.get(parent)

    groups.reverse()
    return groups


def parse_test_nodes(root, parent_map):
    """
    解析所有 TEST 节点。

    返回：
    raw_items
    fail_items
    paused_items
    interrupted_items
    error_items
    """

    raw_items = []
    fail_items = []
    paused_items = []
    interrupted_items = []
    error_items = []

    test_nodes = root.findall(".//TEST")

    for index, test in enumerate(test_nodes, start=1):
        group = get_parent_group(test, parent_map)
        group_path = get_path_groups(test, parent_map)

        test_name = test.attrib.get("NAME", "").strip()
        test_status_raw = test.attrib.get("STATUS", "").strip()
        test_status = normalize_status(test_status_raw)

        group_name = ""
        group_status = ""
        group_status_raw = ""
        group_type = ""
        group_timestamp = ""

        if group is not None:
            group_name = group.attrib.get("NAME", "").strip()
            group_status_raw = group.attrib.get("STATUS", "").strip()
            group_status = normalize_status(group_status_raw)
            group_type = group.attrib.get("TYPE", "").strip()
            group_timestamp = format_timestamp(group.attrib.get("TIMESTAMP", ""))

        item_name = test_name or group_name or f"TEST_{index}"

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
    """
    解析异常 GROUP。

    用途：
    1. DUT / PANEL 是 Terminated 但 TEST 没有明确 Failed 时，用 GROUP 定位中断点。
    2. 识别 PAUSED / INTERRUPTED / ERROR 的 GROUP。
    """

    abnormal_groups = []
    failed_groups = []
    paused_groups = []
    interrupted_groups = []
    error_groups = []

    for group in root.findall(".//GROUP"):
        raw_status = group.attrib.get("STATUS", "").strip()
        status = normalize_status(raw_status)

        if not is_abnormal_status(status):
            continue

        name = group.attrib.get("NAME", "").strip()
        group_type = group.attrib.get("TYPE", "").strip()

        if not name:
            continue

        # 跳过太泛化的大流程节点，避免定位不清晰
        if name in {"MainSequence Callback"}:
            continue

        item = {
            "name": name,
            "type": group_type,
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
    """
    决定整机最终结果。

    优先级：
    1. DUT/PANEL 明确 INTERRUPTED -> INTERRUPTED
    2. DUT/PANEL 明确 PAUSED -> PAUSED
    3. DUT/PANEL 明确 ERROR -> FAIL
    4. TEST 有 FAIL -> FAIL
    5. TEST 有 INTERRUPTED -> INTERRUPTED
    6. TEST 有 PAUSED -> PAUSED
    7. DUT/PANEL PASS -> PASS
    8. 全部 TEST PASS -> PASS
    9. UNKNOWN
    """

    if dut_status == "INTERRUPTED" or panel_status == "INTERRUPTED":
        return "INTERRUPTED"

    if dut_status == "PAUSED" or panel_status == "PAUSED":
        return "PAUSED"

    if dut_status == "ERROR" or panel_status == "ERROR":
        return "FAIL"

    if fail_items:
        return "FAIL"

    if interrupted_items:
        return "INTERRUPTED"

    if paused_items:
        return "PAUSED"

    if error_items:
        return "FAIL"

    if group_info.get("interrupted_groups"):
        return "INTERRUPTED"

    if group_info.get("paused_groups"):
        return "PAUSED"

    if group_info.get("error_groups"):
        return "FAIL"

    if dut_status == "PASS":
        return "PASS"

    if panel_status == "PASS":
        return "PASS"

    if raw_items and all(item.get("result") == "PASS" for item in raw_items):
        return "PASS"

    return "UNKNOWN"


def parse_fct_xml(xml_file_path):
    """
    解析 G4.9 FCT 真实 FTS XML。
    """

    file_mtime, file_mtime_ts = get_file_time(xml_file_path)

    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        parent_map = build_parent_map(root)

        batch_timestamp = format_timestamp(root.attrib.get("TIMESTAMP", ""))

        product = root.find(".//PRODUCT")
        panel = root.find(".//PANEL")
        dut = root.find(".//DUT")

        station, tester = get_station_from_xml(root)

        product_name = ""
        if product is not None:
            product_name = product.attrib.get("NAME", "").strip()

        sn = ""

        if dut is not None:
            sn = dut.attrib.get("ID", "").strip()

        if not sn:
            sn = extract_sn_from_filename(xml_file_path)

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

        # 如果整机中断但 TEST 没有明确中断项，则用 GROUP 兜底定位
        if result == "INTERRUPTED" and not interrupted_items:
            for group in group_info.get("interrupted_groups", []):
                if group["name"] not in interrupted_items:
                    interrupted_items.append(group["name"])

        # 如果整机暂停但 TEST 没有明确暂停项，则用 GROUP 兜底定位
        if result == "PAUSED" and not paused_items:
            for group in group_info.get("paused_groups", []):
                if group["name"] not in paused_items:
                    paused_items.append(group["name"])

        # 如果整机 FAIL 但 TEST 没有明确失败项，则用 GROUP 兜底定位
        if result == "FAIL" and not fail_items:
            for group in group_info.get("failed_groups", []):
                if group["name"] not in fail_items:
                    fail_items.append(group["name"])

            for group in group_info.get("error_groups", []):
                if group["name"] not in fail_items:
                    fail_items.append(group["name"])

        sn_aliases = []
        if sn:
            sn_aliases.append(sn)
            sn_aliases.append(sn[-8:])
            sn_aliases.append(sn[-10:])
            sn_aliases.append(sn[-12:])

        source_file = os.path.basename(xml_file_path)

        return {
            "sn": sn,
            "sn_aliases": list(dict.fromkeys([x for x in sn_aliases if x])),
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

        return {
            "sn": fallback_sn,
            "sn_aliases": [fallback_sn] if fallback_sn else [],
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
    扫描 data/logs 下所有 XML。
    """

    records = []

    xml_pattern = os.path.join(log_dir, "*.xml")
    xml_files = glob.glob(xml_pattern)

    for xml_file in xml_files:
        record = parse_fct_xml(xml_file)
        records.append(record)

    records.sort(
        key=lambda x: x.get("file_mtime_ts", 0),
        reverse=True
    )

    return records


def load_all_fct_xml(log_dir):
    """
    兼容旧版函数。
    """

    records = load_all_fct_records(log_dir)

    data = {}
    for record in records:
        key = record.get("source_file") or record.get("sn") or f"UNKNOWN_{len(data)}"
        data[key] = record

    return data


def find_latest_record_by_sn(records, query_sn):
    """
    SN 查询逻辑。
    支持完整 SN、后 8/10/12 位、文件名片段。
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
        aliases = [
            str(x).strip().upper()
            for x in record.get("sn_aliases", [])
            if x
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

        if query and query in source_file:
            matched.append(record)
            continue

    if not matched:
        return None

    matched.sort(
        key=lambda x: x.get("file_mtime_ts", 0),
        reverse=True
    )

    return matched[0]