# -*- coding: utf-8 -*-
"""
G4.9 FCT XML Dashboard - Data Models

业务状态统一：
- PASS
- FAIL
- 中断

注意：
ERROR / PAUSED / UNKNOWN / PARSE_ERROR 等只允许作为 raw_status 或技术字段存在，
前端和业务展示统一收敛为 “中断”。
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


BUSINESS_PASS = "PASS"
BUSINESS_FAIL = "FAIL"
BUSINESS_INTERRUPT = "中断"


def to_dict_safe(obj: Any) -> Dict[str, Any]:
    """把 dataclass 或普通对象安全转 dict。"""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    return dict(obj.__dict__) if hasattr(obj, "__dict__") else {}


@dataclass
class TestItem:
    name: str = ""
    status: str = ""
    business_status: str = BUSINESS_INTERRUPT

    value: str = ""
    unit: str = ""
    lolim: str = ""
    hilim: str = ""
    rule: str = ""
    datatype: str = ""
    timestamp: str = ""

    section: str = ""
    signal: str = ""
    reference: str = ""
    instrument: str = ""
    instrument_device: str = ""
    nominal_range: str = ""
    raw_name: str = ""
    group: str = ""

    engineering_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestRecord:
    sn: str = ""
    sn_aliases: List[str] = field(default_factory=list)

    model: str = "UNKNOWN"
    test_mode: str = "Unknown"
    date_folder: str = ""
    relative_path: str = ""

    station: str = "FCT"
    tester: str = ""
    product: str = ""

    result: str = BUSINESS_INTERRUPT
    business_result: str = BUSINESS_INTERRUPT
    raw_result: str = ""

    panel_status: str = ""
    panel_status_raw: str = ""
    dut_status: str = ""
    dut_status_raw: str = ""

    fail_items: List[Dict[str, Any]] = field(default_factory=list)
    interrupted_items: List[Dict[str, Any]] = field(default_factory=list)
    raw_items: List[Dict[str, Any]] = field(default_factory=list)

    time: str = ""
    batch_time: str = ""
    panel_time: str = ""
    dut_time: str = ""
    test_time: str = ""

    source_file: str = ""
    source_path: str = ""
    file_mtime: str = ""
    file_mtime_ts: float = 0.0

    total_tests: int = 0
    failed_tests: int = 0
    passed_tests: int = 0
    interrupted_tests: int = 0
    skipped_tests: int = 0

    parse_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MachineStatus:
    machine_id: str = ""
    station: str = "FCT"
    line: str = ""
    host_name: str = ""
    ip: str = ""

    model: str = ""
    test_mode: str = "Online"

    timestamp: str = ""
    server_receive_time: str = ""

    online_status: str = "OFFLINE"
    machine_state: str = "IDLE"
    display_state: str = "OFFLINE"

    current_sn: str = ""
    current_step: str = ""

    instruments: Dict[str, Any] = field(default_factory=dict)
    measurements: Dict[str, Any] = field(default_factory=dict)
    communication: Dict[str, Any] = field(default_factory=dict)
    alarms: List[Any] = field(default_factory=list)

    offline_instruments: List[str] = field(default_factory=list)
    alarm_count: int = 0

    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)