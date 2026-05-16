# -*- coding: utf-8 -*-
"""
G4.9 FCT Test Context Knowledge

这里放工程上下文：
- 仪表识别
- 仪表设备映射
- 工程分析提示
- 测试项名称解析辅助

后续你可以继续根据 Spec / 点位图 / Station PDF 补充更精确的 TP、Net、Reference。
"""

import re
from typing import Dict


INSTRUMENT_DEVICE_MAPPING = {
    "DMM": "DMM / 34461A 或 GDM-9061",
    "OSC": "Oscilloscope / TBS2204B",
    "POWER": "Power Supply / R&S HMP4040 / E3645A / ITECH",
    "XCP": "XCP over CAN / ECU Internal Variable",
    "CAN": "CAN / ZLG CANFD 或 USB8502",
    "LIN": "LIN / USB8506",
    "ETH": "Ethernet / Radmoon",
    "UNKNOWN": "-"
}


ENGINEERING_HINTS = {
    "DMM": "若短时间内多个 SN 在相同 DMM 点位重复 FAIL，建议复核 DMM、继电器切换矩阵、探针接触、GND/参考点和夹具线束。仅为风险提示，不作为故障结论。",
    "OSC": "若短时间内多个 SN 在相同 OSC 波形项重复 FAIL，建议复核示波器通道、探头/BNC/SMA 线、触发配置、探针接触和夹具屏蔽。仅为风险提示，不作为故障结论。",
    "POWER": "若短时间内多个 SN 在电源相关项重复 FAIL，建议复核电源通道、电源线、继电器、负载状态和供电路径。仅为风险提示，不作为故障结论。",
    "XCP": "若短时间内多个 SN 在 XCP 项重复 FAIL，建议复核 ECU 通讯链路、标定变量、刷写版本、CAN/XCP 通道和测试时序。仅为风险提示，不作为故障结论。",
    "CAN": "若短时间内多个 SN 在 CAN 项重复 FAIL，建议复核 CAN 设备、线束、终端电阻、波特率、DBC/报文配置和接口板。仅为风险提示，不作为故障结论。",
    "LIN": "若短时间内多个 SN 在 LIN 项重复 FAIL，建议复核 LIN 设备、线束、主从配置、供电和通讯时序。仅为风险提示，不作为故障结论。",
    "ETH": "若短时间内多个 SN 在 Ethernet 项重复 FAIL，建议复核以太网治具、线束、PHY 状态、Radmoon 配置和通讯时序。仅为风险提示，不作为故障结论。",
    "UNKNOWN": "建议结合 Spec、点位图、测试站接线和原始 XML 复核该测试项。仅为风险提示，不作为故障结论。"
}


def detect_instrument(test_name: str) -> str:
    """根据测试项名称识别仪表类型。"""
    text = (test_name or "").upper()

    if "(DMM)" in text or "DMM" in text:
        return "DMM"
    if "(OSC)" in text or "OSC" in text or "SCOPE" in text:
        return "OSC"
    if "XCP" in text:
        return "XCP"
    if "CAN" in text:
        return "CAN"
    if "LIN" in text:
        return "LIN"
    if "ETH" in text or "ETHERNET" in text or "PHY" in text:
        return "ETH"
    if any(k in text for k in ["POWER", "SUPPLY", "VIN", "VOUT", "VBAT", "CURRENT", "VOLTAGE"]):
        return "POWER"

    return "UNKNOWN"


def get_instrument_device(instrument: str) -> str:
    return INSTRUMENT_DEVICE_MAPPING.get(instrument or "UNKNOWN", "-")


def get_engineering_hint(instrument: str) -> str:
    return ENGINEERING_HINTS.get(instrument or "UNKNOWN", ENGINEERING_HINTS["UNKNOWN"])


def extract_section(test_name: str) -> str:
    """提取章节号，例如 6.1.1.2.24。"""
    text = test_name or ""
    m = re.match(r"^\s*(\d+(?:\.\d+)+)", text)
    return m.group(1) if m else ""


def extract_signal(test_name: str) -> str:
    """
    粗略提取点位/信号。
    示例：
    6.1.1.2.24 P1V2_PHY_AVDD(DMM) -> P1V2_PHY_AVDD
    RelayLSD_Output to GND Low Level(OSC) -> RelayLSD_Output to GND Low Level
    """
    text = test_name or ""

    text = re.sub(r"^\s*\d+(?:\.\d+)+\s*", "", text)
    text = re.sub(r"\((DMM|OSC|XCP|CAN|LIN|ETH|POWER)\)", "", text, flags=re.IGNORECASE)
    return text.strip()


def build_nominal_range(lolim: str, hilim: str, unit: str) -> str:
    lo = str(lolim or "").strip()
    hi = str(hilim or "").strip()
    u = str(unit or "").strip()

    if lo and hi:
        return f"{lo} ~ {hi} {u}".strip()
    if lo:
        return f">= {lo} {u}".strip()
    if hi:
        return f"<= {hi} {u}".strip()
    return "-"