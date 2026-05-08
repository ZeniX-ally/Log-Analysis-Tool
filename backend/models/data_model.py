from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class TestItem:
    raw_name: str
    name: str
    section: str
    signal: str
    reference_point: str
    instrument: str
    instrument_device: str
    unit: str
    value: str
    low_limit: str
    high_limit: str
    nominal: str
    rule: str
    status: str
    datatype: str
    timestamp: str
    test_type: str
    engineering_hint: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_name": self.raw_name,
            "name": self.name,
            "section": self.section,
            "signal": self.signal,
            "reference_point": self.reference_point,
            "instrument": self.instrument,
            "instrument_device": self.instrument_device,
            "unit": self.unit,
            "value": self.value,
            "low_limit": self.low_limit,
            "high_limit": self.high_limit,
            "nominal": self.nominal,
            "rule": self.rule,
            "status": self.status,
            "datatype": self.datatype,
            "timestamp": self.timestamp,
            "test_type": self.test_type,
            "engineering_hint": self.engineering_hint,
        }


@dataclass
class TestRecord:
    sn: str
    model: str
    result: str
    fail_items: List[str]
    file_name: str
    file_path: str
    test_time: str
    source: str
    tester: str = ""
    runmode: str = ""
    total_test_time: str = ""
    test_items: List[TestItem] = field(default_factory=list)

    def to_dict(self, include_items: bool = True) -> Dict[str, Any]:
        data = {
            "sn": self.sn,
            "model": self.model,
            "result": self.result,
            "fail_items": self.fail_items,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "test_time": self.test_time,
            "source": self.source,
            "tester": self.tester,
            "runmode": self.runmode,
            "total_test_time": self.total_test_time,
            "test_count": len(self.test_items),
            "fail_count": len([i for i in self.test_items if i.status == "FAILED"]),
            "pass_count": len([i for i in self.test_items if i.status == "PASSED"]),
        }

        if include_items:
            data["test_items"] = [item.to_dict() for item in self.test_items]
        else:
            data["test_items"] = []

        return data


# ✅ 补回 MachineStatus，用于 app.py 中的 /api/machine/status
@dataclass
class MachineStatus:
    machine_id: str
    online: bool
    voltage: float
    current: float
    temperature: float
    status: str
    last_update: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "online": self.online,
            "voltage": self.voltage,
            "current": self.current,
            "temperature": self.temperature,
            "status": self.status,
            "last_update": self.last_update,
        }