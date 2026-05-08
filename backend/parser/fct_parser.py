import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.models.data_model import TestRecord, TestItem
from backend.knowledge.test_context import enrich_test_context


LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")

MODEL_PREFIX_MAP = {
    "E3002781": "E3002781",
    "E3002624": "E3002624",
}


def normalize_status(status: str) -> str:
    value = str(status or "").strip().upper()

    if value in ["PASSED", "PASS", "OK", "SUCCESS", "TRUE"]:
        return "PASSED"

    if value in ["FAILED", "FAIL", "NG", "ERROR", "FALSE"]:
        return "FAILED"

    if value in ["SKIPPED", "SKIP"]:
        return "SKIPPED"

    if value in ["DONE"]:
        return "DONE"

    return value or "UNKNOWN"


def normalize_record_result(status: str) -> str:
    value = normalize_status(status)

    if value == "PASSED":
        return "PASS"

    if value == "FAILED":
        return "FAIL"

    if value == "SKIPPED":
        return "SKIPPED"

    return "UNKNOWN"


def guess_model_from_text(text: str) -> str:
    text = str(text or "")

    for prefix, model in MODEL_PREFIX_MAP.items():
        if prefix in text:
            return model

    return "UNKNOWN"


def guess_model_from_path(file_path: str) -> str:
    path = file_path.replace("\\", "/")

    for prefix, model in MODEL_PREFIX_MAP.items():
        if prefix in path:
            return model

    return "UNKNOWN"


def guess_source_from_path(file_path: str) -> str:
    path = file_path.replace("\\", "/").lower()

    if "/online/" in path:
        return "online"

    if "/offline/" in path:
        return "offline"

    return "unknown"


def guess_time_from_file(file_path: str) -> str:
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def get_attr(element, key: str, default: str = "") -> str:
    if element is None:
        return default

    return str(element.attrib.get(key, default)).strip()


def find_root_meta(root, file_path: str):
    factory = root.find(".//FACTORY")
    panel = root.find(".//PANEL")
    dut = root.find(".//DUT")

    sn = get_attr(dut, "ID")
    if not sn:
        sn = os.path.splitext(os.path.basename(file_path))[0]

    tester = get_attr(factory, "TESTER")
    runmode = get_attr(panel, "RUNMODE")
    panel_status = get_attr(panel, "STATUS")
    dut_status = get_attr(dut, "STATUS")
    test_time = get_attr(dut, "TIMESTAMP") or get_attr(panel, "TIMESTAMP") or guess_time_from_file(file_path)
    total_test_time = get_attr(dut, "TESTTIME") or get_attr(panel, "TESTTIME")

    result = normalize_record_result(dut_status or panel_status)

    model = guess_model_from_text(sn)
    if model == "UNKNOWN":
        model = guess_model_from_path(file_path)

    return {
        "sn": sn,
        "model": model,
        "result": result,
        "tester": tester,
        "runmode": runmode,
        "test_time": test_time,
        "total_test_time": total_test_time,
    }


def is_real_test_group(group) -> bool:
    group_type = get_attr(group, "TYPE")
    test = group.find("./TEST")

    if test is None:
        return False

    if group_type in ["NumericLimitTest", "StringValueTest", "FtsStringValueTest", "PassFailTest"]:
        return True

    return True


def parse_test_item_from_group(group) -> Optional[TestItem]:
    test = group.find("./TEST")

    if test is None:
        return None

    raw_name = get_attr(test, "NAME") or get_attr(group, "NAME")
    unit = get_attr(test, "UNIT")
    value = get_attr(test, "VALUE")
    high_limit = get_attr(test, "HILIM")
    low_limit = get_attr(test, "LOLIM")
    status = normalize_status(get_attr(test, "STATUS") or get_attr(group, "STATUS"))
    rule = get_attr(test, "RULE")
    datatype = get_attr(test, "DATATYPE")
    timestamp = get_attr(group, "TIMESTAMP")
    test_type = get_attr(group, "TYPE")

    context = enrich_test_context(
        raw_name=raw_name,
        unit=unit,
        low_limit=low_limit,
        high_limit=high_limit,
        rule=rule,
    )

    return TestItem(
        raw_name=raw_name,
        name=context["name"],
        section=context["section"],
        signal=context["signal"],
        reference_point=context["reference_point"],
        instrument=context["instrument"],
        instrument_device=context["instrument_device"],
        unit=unit,
        value=value,
        low_limit=low_limit,
        high_limit=high_limit,
        nominal=context["nominal"],
        rule=rule,
        status=status,
        datatype=datatype,
        timestamp=timestamp,
        test_type=test_type,
        engineering_hint=context["engineering_hint"],
    )


def parse_xml_file(file_path: str) -> Optional[TestRecord]:
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        meta = find_root_meta(root, file_path)

        test_items: List[TestItem] = []

        for group in root.iter("GROUP"):
            if not is_real_test_group(group):
                continue

            item = parse_test_item_from_group(group)

            if item:
                test_items.append(item)

        fail_items = [
            item.name
            for item in test_items
            if item.status.upper() == "FAILED"
        ]

        result = meta["result"]

        if fail_items:
            result = "FAIL"

        record = TestRecord(
            sn=meta["sn"],
            model=meta["model"],
            result=result,
            fail_items=fail_items,
            file_name=os.path.basename(file_path),
            file_path=file_path,
            test_time=meta["test_time"],
            source=guess_source_from_path(file_path),
            tester=meta["tester"],
            runmode=meta["runmode"],
            total_test_time=meta["total_test_time"],
            test_items=test_items,
        )

        return record

    except Exception as e:
        print(f"[Parser Error] {file_path}: {e}")
        return None


def scan_xml_files(limit: int = 1000) -> List[TestRecord]:
    records: List[TestRecord] = []

    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)
        return records

    xml_files = []

    for root_dir, _, files in os.walk(LOG_DIR):
        for file_name in files:
            if file_name.lower().endswith(".xml"):
                xml_files.append(os.path.join(root_dir, file_name))

    xml_files.sort(
        key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
        reverse=True,
    )

    for file_path in xml_files[:limit]:
        record = parse_xml_file(file_path)
        if record:
            records.append(record)

    return records


def search_by_sn(sn: str) -> Optional[TestRecord]:
    target = str(sn or "").strip().upper()

    if not target:
        return None

    records = scan_xml_files(limit=3000)

    for record in records:
        if record.sn.upper() == target:
            return record

    for record in records:
        if target in record.sn.upper():
            return record

    return None


def get_record_by_file_path(file_path: str) -> Optional[TestRecord]:
    if not file_path:
        return None

    abs_path = os.path.abspath(file_path)

    log_root = os.path.abspath(LOG_DIR)

    if not abs_path.startswith(log_root):
        return None

    if not os.path.exists(abs_path):
        return None

    return parse_xml_file(abs_path)