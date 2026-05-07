import os
import glob
import xml.etree.ElementTree as ET
from datetime import datetime


def safe_get_text(root, tag_name, default=""):
    """
    安全读取 XML 中某个标签的文本。
    例如 <SN>G49-001</SN>
    """
    node = root.find(tag_name)
    if node is not None and node.text is not None:
        return node.text.strip()
    return default


def parse_fct_xml(xml_file_path):
    """
    解析单个 FCT XML 文件。

    当前支持格式示例：

    <TestResult>
        <SN>G49-001</SN>
        <Station>FCT</Station>
        <Result>FAIL</Result>
        <Time>2026-05-07 20:30:00</Time>
        <TestItems>
            <Item name="CAN_Comm" result="FAIL"/>
            <Item name="VoltageTest" result="PASS"/>
        </TestItems>
    </TestResult>
    """

    try:
        tree = ET.parse(xml_file_path)
        root = tree.getroot()

        sn = safe_get_text(root, "SN", default="")
        station = safe_get_text(root, "Station", default="FCT")
        result = safe_get_text(root, "Result", default="UNKNOWN").upper()
        test_time = safe_get_text(root, "Time", default="")

        fail_items = []
        raw_items = []

        for item in root.findall(".//Item"):
            item_name = item.attrib.get("name", "").strip()
            item_result = item.attrib.get("result", "").strip().upper()

            if not item_name:
                item_name = "UNKNOWN_ITEM"

            raw_items.append({
                "name": item_name,
                "result": item_result
            })

            if item_result == "FAIL":
                fail_items.append(item_name)

        if fail_items:
            result = "FAIL"

        if result in ["", "UNKNOWN"] and raw_items:
            if all(item["result"] == "PASS" for item in raw_items):
                result = "PASS"

        file_mtime_ts = os.path.getmtime(xml_file_path)
        file_mtime = datetime.fromtimestamp(file_mtime_ts).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "sn": sn,
            "station": station,
            "result": result,
            "fail_items": fail_items,
            "raw_items": raw_items,
            "time": test_time,
            "source_file": os.path.basename(xml_file_path),
            "file_mtime": file_mtime,
            "file_mtime_ts": file_mtime_ts
        }

    except Exception as e:
        try:
            file_mtime_ts = os.path.getmtime(xml_file_path)
            file_mtime = datetime.fromtimestamp(file_mtime_ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            file_mtime_ts = 0
            file_mtime = ""

        return {
            "sn": "",
            "station": "FCT",
            "result": "PARSE_ERROR",
            "fail_items": [],
            "raw_items": [],
            "time": "",
            "source_file": os.path.basename(xml_file_path),
            "file_mtime": file_mtime,
            "file_mtime_ts": file_mtime_ts,
            "error": str(e)
        }


def load_all_fct_xml(log_dir):
    """
    扫描 data/logs 目录下所有 XML 文件，并解析成字典。

    返回结构：
    {
        "G49-001": {...},
        "G49-002": {...}
    }
    """

    data = {}

    xml_pattern = os.path.join(log_dir, "*.xml")
    xml_files = glob.glob(xml_pattern)

    for xml_file in xml_files:
        record = parse_fct_xml(xml_file)
        sn = record.get("sn", "").strip()

        if not sn:
            # 没有 SN 的解析异常文件，用文件名作为 key，避免完全丢失
            sn = f"PARSE_ERROR_{record.get('source_file', '')}"

        data[sn] = record

    return data
