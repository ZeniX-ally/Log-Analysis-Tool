# -*- coding: utf-8 -*-
import glob
import os
import re
import datetime
import xml.etree.ElementTree as ET

# =========================================================
# 1. 绝对安全的全局兜底函数定义 (避免作用域报错)
# =========================================================
def fallback_detect_instrument(test_name):
    t = str(test_name or "").upper()
    if "DMM" in t: return "DMM"
    if "OSC" in t or "SCOPE" in t: return "OSC"
    if "POWER" in t or "VIN" in t: return "POWER"
    return "UNKNOWN"

def fallback_get_instrument_device(ins): return "-"
def fallback_get_engineering_hint(ins): return "无相关排查建议"
def fallback_extract_section(name): return ""
def fallback_extract_signal(name): return str(name)
def fallback_build_nominal_range(lo, hi, u): return f"{lo}~{hi} {u}"

# 默认绑定兜底函数
detect_instrument = fallback_detect_instrument
get_instrument_device = fallback_get_instrument_device
get_engineering_hint = fallback_get_engineering_hint
extract_section = fallback_extract_section
extract_signal = fallback_extract_signal
build_nominal_range = fallback_build_nominal_range

# 动态尝试加载外部知识库 (无损降级)
try:
    import backend.knowledge.test_context as kt
    detect_instrument = getattr(kt, 'detect_instrument', detect_instrument)
    get_instrument_device = getattr(kt, 'get_instrument_device', get_instrument_device)
    get_engineering_hint = getattr(kt, 'get_engineering_hint', get_engineering_hint)
    extract_section = getattr(kt, 'extract_section', extract_section)
    extract_signal = getattr(kt, 'extract_signal', extract_signal)
    build_nominal_range = getattr(kt, 'build_nominal_range', build_nominal_range)
except BaseException:
    try:
        import knowledge.test_context as kt
        detect_instrument = getattr(kt, 'detect_instrument', detect_instrument)
        get_instrument_device = getattr(kt, 'get_instrument_device', get_instrument_device)
        get_engineering_hint = getattr(kt, 'get_engineering_hint', get_engineering_hint)
        extract_section = getattr(kt, 'extract_section', extract_section)
        extract_signal = getattr(kt, 'extract_signal', extract_signal)
        build_nominal_range = getattr(kt, 'build_nominal_range', build_nominal_range)
    except BaseException:
        pass

# =========================================================
# 2. 核心底层辅助函数
# =========================================================
PASS_TEXTS = {"PASS", "PASSED", "OK", "SUCCESS", "TRUE"}
FAIL_TEXTS = {"FAIL", "FAILED", "NG", "FALSE"}

def local_name(tag): return str(tag).split("}", 1)[-1].upper() if tag else ""

def iter_by_tag(root, tag_name):
    target = str(tag_name or "").upper()
    for node in root.iter():
        if local_name(node.tag) == target: yield node

def find_first(root, tag_name):
    for node in iter_by_tag(root, tag_name): return node
    return None

def get_attr(node, *names):
    if node is None: return ""
    lower_map = {str(k).lower(): str(v) for k, v in node.attrib.items()}
    for name in names:
        if name in node.attrib: return str(node.attrib[name])
        low_name = str(name).lower()
        if low_name in lower_map: return lower_map[low_name]
    return ""

def normalize_raw_status(status):
    text = str(status or "").strip().upper()
    if text in PASS_TEXTS: return "PASS"
    if text in FAIL_TEXTS: return "FAIL"
    return "中断"

def format_timestamp(value):
    text = str(value or "").strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", text)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    return text

def get_file_time(path):
    try:
        ts = os.path.getmtime(path)
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"), ts
    except BaseException: return "", 0.0

def get_relative_path(path, log_dir=None):
    try:
        if log_dir: return os.path.relpath(path, log_dir).replace("\\", "/")
    except BaseException: pass
    return os.path.basename(path)

def get_model_from_sn(sn):
    text = str(sn or "").strip()
    m = re.search(r"(E\d{7})", text, re.I)
    return m.group(1).upper() if m else "UNKNOWN"

def extract_sn_from_filename(filename):
    base = os.path.basename(str(filename or ""))
    for part in base.split("_"):
        if re.search(r"E\d{7}", part, re.I) and len(part) >= 8:
            return os.path.splitext(part)[0]
    m = re.search(r"(E\d{7}[A-Za-z0-9]+)", base, re.I)
    return m.group(1) if m else ""

def build_parent_map(root):
    parent_map = {}
    for parent in root.iter():
        for child in list(parent): parent_map[child] = parent
    return parent_map

def get_parent_group(node, parent_map):
    curr = node
    while curr in parent_map:
        curr = parent_map[curr]
        if local_name(curr.tag) == "GROUP":
            return get_attr(curr, "NAME", "Name", "name")
    return ""

def get_path_groups(node, parent_map):
    groups = []
    curr = node
    while curr in parent_map:
        curr = parent_map[curr]
        if local_name(curr.tag) == "GROUP":
            name = get_attr(curr, "NAME", "Name", "name")
            if name: groups.append(name)
    groups.reverse()
    return groups

# =========================================================
# 3. 强抗错 XML 提取核心
# =========================================================
def read_xml_safely(file_path):
    content = ""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
    except BaseException:
        try:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f: content = f.read()
        except BaseException: return ""
    
    # 彻底清洗所有非法控制字符与声明
    content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', content)
    content = re.sub(r'<\?xml[^>]+\?>', '', content)
    return content.strip()

def salvage_info_from_broken_xml(content):
    sn = ""
    status = "中断"
    sn_match = re.search(r'ID="([^"]+)"', content)
    if sn_match: sn = sn_match.group(1)
    
    if re.search(r'STATUS="Failed"', content, re.I): status = "FAIL"
    elif re.search(r'STATUS="Passed"', content, re.I): status = "PASS"
    return sn, status

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
        timestamp = format_timestamp(get_attr(node, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time"))
        instrument = detect_instrument(name)

        items.append({
            "name": name, "status": raw_status, "business_status": business_status, "result": business_status,
            "value": value, "unit": unit, "lolim": lolim, "hilim": hilim, "rule": rule, "datatype": datatype,
            "timestamp": timestamp, "section": extract_section(name), "signal": extract_signal(name),
            "reference": "GND" if "GND" in str(name).upper() else "", "instrument": instrument,
            "instrument_device": get_instrument_device(instrument), "nominal_range": build_nominal_range(lolim, hilim, unit),
            "raw_name": name, "group": get_parent_group(node, parent_map), "groups": get_path_groups(node, parent_map),
            "engineering_hint": get_engineering_hint(instrument),
        })
    return items

def get_station_from_xml(root):
    factory = find_first(root, "FACTORY")
    product = find_first(root, "PRODUCT")
    tester = get_attr(factory, "TESTER", "Tester", "tester")
    product_name = get_attr(product, "NAME", "Name", "name")
    station = tester.split("_")[-1] if tester else "FCT"
    return station, tester, product_name

def build_sn_aliases(sn):
    text = str(sn or "").strip()
    if not text: return []
    aliases = {text, text.upper()}
    if len(text) > 8: aliases.add(text[-8:])
    if len(text) > 10: aliases.add(text[-10:])
    if len(text) > 12: aliases.add(text[-12:])
    return sorted(list(aliases))

def decide_overall_result(raw_status, total_tests, passed_tests, failed_tests, interrupted_tests, skipped_tests):
    if total_tests <= 0 or interrupted_tests > 0 or skipped_tests > 0 or total_tests > (passed_tests + failed_tests): return "中断"
    if normalize_raw_status(raw_status) == "中断": return "中断"
    if failed_tests > 0: return "FAIL"
    if passed_tests == total_tests: return "PASS"
    return "中断"

# =========================================================
# 4. 主解析引擎
# =========================================================
def parse_fct_xml(xml_file_path, log_dir=None):
    file_time, file_ts = get_file_time(xml_file_path)
    source_file = os.path.basename(xml_file_path)
    relative_path = get_relative_path(xml_file_path, log_dir)
    
    content = read_xml_safely(xml_file_path)

    try:
        if not content: raise ValueError("文件数据为空")
        root = ET.fromstring(content)
        parent_map = build_parent_map(root)

        batch = find_first(root, "BATCH")
        panel = find_first(root, "PANEL")
        dut = find_first(root, "DUT")

        sn = get_attr(dut, "ID", "Id", "id") or extract_sn_from_filename(source_file)
        model = get_model_from_sn(sn)
        test_mode = get_attr(panel, "RUNMODE", "RunMode", "runmode") or "Production"

        batch_time = format_timestamp(get_attr(batch, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time"))
        panel_time = format_timestamp(get_attr(panel, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time"))
        dut_time = format_timestamp(get_attr(dut, "TIMESTAMP", "TimeStamp", "timestamp", "TIME", "time"))
        test_time = dut_time or panel_time or batch_time or file_time
        date_folder = test_time[:10].replace("-", "") if test_time and len(test_time) >= 10 else ""

        panel_status_raw = get_attr(panel, "STATUS", "Status", "status")
        dut_status_raw = get_attr(dut, "STATUS", "Status", "status")
        raw_result = dut_status_raw or panel_status_raw

        station, tester, product_name = get_station_from_xml(root)
        raw_items = parse_test_nodes(root, parent_map)

        total_tests = len(raw_items)
        passed_tests = sum(1 for i in raw_items if i.get("business_status") == "PASS")
        failed_tests = sum(1 for i in raw_items if i.get("business_status") == "FAIL")
        interrupted_tests = sum(1 for i in raw_items if i.get("business_status") == "中断")
        skipped_tests = sum(1 for i in raw_items if str(i.get("status", "")).strip().upper() in ["SKIP", "SKIPPED"])

        fail_items = [i for i in raw_items if i.get("business_status") == "FAIL"]
        interrupted_items = [i for i in raw_items if i.get("business_status") == "中断"]

        business_result = decide_overall_result(raw_result, total_tests, passed_tests, failed_tests, interrupted_tests, skipped_tests)

        return {
            "sn": sn, "sn_aliases": build_sn_aliases(sn), "model": model, 
            "test_mode": test_mode, "date_folder": date_folder, "relative_path": relative_path,
            "station": station, "tester": tester, "product": product_name,
            "result": business_result, "business_result": business_result, "raw_result": raw_result,
            "panel_status": normalize_raw_status(panel_status_raw), "panel_status_raw": panel_status_raw,
            "dut_status": normalize_raw_status(dut_status_raw), "dut_status_raw": dut_status_raw,
            "fail_items": fail_items, "interrupted_items": interrupted_items, "raw_items": raw_items,
            "time": test_time, "batch_time": batch_time, "panel_time": panel_time, "dut_time": dut_time,
            "test_time": test_time, "source_file": source_file, "source_path": xml_file_path,
            "file_mtime": file_time, "file_mtime_ts": file_ts,
            "total_tests": total_tests, "failed_tests": failed_tests, "passed_tests": passed_tests,
            "interrupted_tests": interrupted_tests, "skipped_tests": skipped_tests, "parse_error": ""
        }
    except BaseException as exc:
        salvaged_sn, salvaged_status = salvage_info_from_broken_xml(content)
        final_sn = salvaged_sn or extract_sn_from_filename(source_file)
        
        return {
            "sn": final_sn, "sn_aliases": build_sn_aliases(final_sn), "model": get_model_from_sn(final_sn),
            "test_mode": "Unknown", "date_folder": "", "relative_path": relative_path,
            "station": "FCT", "tester": "", "product": "",
            "result": salvaged_status, "business_result": salvaged_status, "raw_result": "PARSE_ERROR",
            "panel_status": "中断", "panel_status_raw": "", "dut_status": "中断", "dut_status_raw": "",
            "fail_items": [], "interrupted_items": [], "raw_items": [],
            "time": file_time, "batch_time": "", "panel_time": "", "dut_time": "", "test_time": file_time,
            "source_file": source_file, "source_path": xml_file_path, "file_mtime": file_time, "file_mtime_ts": file_ts,
            "total_tests": 0, "failed_tests": 0, "passed_tests": 0, "interrupted_tests": 0, "skipped_tests": 0,
            "parse_error": f"由于 XML 结构损坏 ({str(exc)})，已切入灾难抢救模式"
        }

def load_all_fct_records(log_dir):
    pattern = os.path.join(log_dir, "**", "*.xml")
    files = glob.glob(pattern, recursive=True)
    records = [parse_fct_xml(path, log_dir=log_dir) for path in files]
    records.sort(key=lambda item: item.get("file_mtime_ts", 0), reverse=True)
    return records

def load_all_fct_xml(log_dir): return load_all_fct_records(log_dir)

def find_latest_record_by_sn(records, query_sn):
    query = str(query_sn or "").strip().upper()
    if not query: return None
    matched = []
    for record in records:
        sn = str(record.get("sn", "")).upper()
        aliases = [str(alias).upper() for alias in record.get("sn_aliases", [])]
        source_file = str(record.get("source_file", "")).upper()
        relative_path = str(record.get("relative_path", "")).upper()
        if query == sn or query in aliases or sn.endswith(query) or query in source_file or query in relative_path:
            matched.append(record)
    if not matched: return None
    matched.sort(key=lambda item: item.get("file_mtime_ts", 0), reverse=True)
    return matched[0]