import re
from typing import Dict, Any


INSTRUMENT_DEVICE_MAP = {
    "DMM": "DMM / 34461A 或 GDM-9061",
    "OSC": "Oscilloscope / TBS2204B",
    "POWER": "Power Supply / R&S HMP4040 / E3645A / ITECH",
    "XCP": "XCP over CAN / ECU Internal Variable",
    "CAN": "CAN / ZLG CANFD 或 USB8502",
    "LIN": "LIN / USB8506",
    "ETH": "Ethernet / Radmoon",
    "UNKNOWN": "未识别仪表",
}


INSTRUMENT_HINT_MAP = {
    "DMM": "该测试项属于 DMM 测量链路。若短时间内多个 SN 在相同点位重复 FAIL，建议复核 DMM、继电器切换矩阵、探针接触、GND/参考点和夹具线束。",
    "OSC": "该测试项属于示波器波形测量链路。若短时间内多个 SN 在相同波形项重复 FAIL，建议复核示波器通道、探头/BNC/SMA 线、触发配置、探针接触和夹具屏蔽。",
    "POWER": "该测试项属于电源供电或电流测量链路。若短时间内多个 SN 重复 FAIL，建议复核电源通道、电源线、继电器、负载状态和供电路径。",
    "XCP": "该测试项属于 ECU 内部变量读取。若短时间内多个 SN 重复 FAIL，建议复核 ECU 通讯链路、标定变量、刷写版本、CAN/XCP 通道和测试时序。",
    "CAN": "该测试项属于 CAN 通讯链路。若短时间内多个 SN 重复 FAIL，建议复核 CAN 设备、线束、终端电阻、波特率、DBC/报文配置和接口板。",
    "LIN": "该测试项属于 LIN 通讯链路。若短时间内多个 SN 重复 FAIL，建议复核 LIN 设备、线束、主从配置、供电和通讯时序。",
    "ETH": "该测试项属于以太网通讯链路。若短时间内多个 SN 重复 FAIL，建议复核以太网治具、线束、PHY 状态、Radmoon 配置和通讯时序。",
    "UNKNOWN": "该测试项暂未识别出明确仪表。建议结合测试名称、Spec 和点位图人工确认测试链路。",
}


def clean_test_name(raw_name: str) -> str:
    text = raw_name or ""
    text = re.sub(r"^\s*\d+(\.\d+)*\s*", "", text)
    return text.strip()


def extract_section(raw_name: str) -> str:
    match = re.match(r"^\s*(\d+(\.\d+)*)", raw_name or "")
    if match:
        return match.group(1)
    return ""


def extract_instrument(raw_name: str) -> str:
    text = raw_name or ""

    matches = re.findall(r"\(([^()]*)\)", text)
    if matches:
        last = matches[-1].strip().upper()

        if "DMM" in last:
            return "DMM"
        if "OSC" in last:
            return "OSC"
        if "POWER" in last:
            return "POWER"
        if "XCP" in last:
            return "XCP"
        if "CAN" in last:
            return "CAN"
        if "LIN" in last:
            return "LIN"
        if "ETH" in last:
            return "ETH"

    upper = text.upper()

    if "DMM" in upper:
        return "DMM"
    if "OSC" in upper:
        return "OSC"
    if "POWER" in upper:
        return "POWER"
    if "XCP" in upper:
        return "XCP"
    if "CAN" in upper:
        return "CAN"
    if "LIN" in upper:
        return "LIN"
    if "ETH" in upper or "ETHERNET" in upper:
        return "ETH"

    return "UNKNOWN"


def remove_instrument_suffix(name: str) -> str:
    text = name or ""
    text = re.sub(r"\([^()]*\)\s*$", "", text)
    return text.strip()


def extract_signal_and_reference(raw_name: str) -> Dict[str, str]:
    name = clean_test_name(raw_name)
    name = remove_instrument_suffix(name)

    reference_point = ""
    signal = name

    patterns = [
        r"\s+to\s+",
        r"\s+from\s+",
        r"\s+From\s+",
        r"\s+TO\s+",
    ]

    for pattern in patterns:
        parts = re.split(pattern, name, maxsplit=1)
        if len(parts) == 2:
            signal = parts[0].strip()
            reference_point = parts[1].strip()

            reference_point = re.sub(
                r"\s+(Frequency|Duty|High Level|Low Level|Peak to Peak|Resistance|Volt|Voltage|Current).*$",
                "",
                reference_point,
                flags=re.IGNORECASE,
            ).strip()

            return {
                "signal": signal,
                "reference_point": reference_point,
            }

    # 对于 “Volt for TC_AI_Cur_1” 这种写法，真正信号在 for 后面
    m = re.search(r"\bfor\s+(.+)$", name, flags=re.IGNORECASE)
    if m:
        signal = m.group(1).strip()

    # 去掉常见测量描述，只保留更像点位/变量的主体
    signal = re.sub(
        r"\s+(Frequency|Duty|High Level|Low Level|Peak to Peak|Resistance|Volt|Voltage|Current)$",
        "",
        signal,
        flags=re.IGNORECASE,
    ).strip()

    return {
        "signal": signal,
        "reference_point": reference_point,
    }


def build_nominal(low_limit: str, high_limit: str, unit: str, rule: str) -> str:
    low = str(low_limit or "").strip()
    high = str(high_limit or "").strip()
    unit = str(unit or "").strip()
    rule = str(rule or "").strip().upper()

    if rule == "GELE":
        return f"{low} ~ {high} {unit}".strip()

    if rule == "EQ":
        return f"= {low} {unit}".strip()

    if rule == "LT":
        return f"< {low} {unit}".strip()

    if rule == "GT":
        return f"> {low} {unit}".strip()

    if rule == "GE":
        return f">= {low} {unit}".strip()

    if rule == "LE":
        return f"<= {high} {unit}".strip()

    if rule == "LOG":
        return "记录项，无判定上下限"

    if low or high:
        return f"Low={low}, High={high} {unit}".strip()

    return "未提供标称范围"


def build_engineering_hint(instrument: str, signal: str, reference_point: str) -> str:
    base = INSTRUMENT_HINT_MAP.get(instrument, INSTRUMENT_HINT_MAP["UNKNOWN"])

    detail = []

    if signal:
        detail.append(f"当前解析到的测试点/信号为 {signal}")

    if reference_point:
        detail.append(f"参考点为 {reference_point}")

    if detail:
        return base + " " + "，".join(detail) + "。"

    return base


def enrich_test_context(raw_name: str, unit: str, low_limit: str, high_limit: str, rule: str) -> Dict[str, Any]:
    section = extract_section(raw_name)
    display_name = clean_test_name(raw_name)
    instrument = extract_instrument(raw_name)
    signal_ref = extract_signal_and_reference(raw_name)

    signal = signal_ref["signal"]
    reference_point = signal_ref["reference_point"]

    nominal = build_nominal(low_limit, high_limit, unit, rule)

    return {
        "name": display_name,
        "section": section,
        "signal": signal,
        "reference_point": reference_point,
        "instrument": instrument,
        "instrument_device": INSTRUMENT_DEVICE_MAP.get(instrument, INSTRUMENT_DEVICE_MAP["UNKNOWN"]),
        "nominal": nominal,
        "engineering_hint": build_engineering_hint(instrument, signal, reference_point),
    }