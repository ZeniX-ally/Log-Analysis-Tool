import random
import time
import json
import urllib.request
from datetime import datetime


SERVER_URL = "http://127.0.0.1:5000/api/machine/status"

MACHINE_IDS = [
    "FCT-01",
    "FCT-02",
    "BURNIN-01",
    "BOX1-01",
]


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=data,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=5) as response:
        return response.read().decode("utf-8")


def build_mock_status(machine_id):
    online = random.random() > 0.05

    voltage = round(random.uniform(11.8, 12.3), 3)
    current = round(random.uniform(0.5, 2.5), 3)
    temperature = round(random.uniform(28.0, 45.0), 2)

    status = "RUNNING"

    if not online:
        status = "OFFLINE"
        voltage = 0
        current = 0
    elif voltage < 11.9 or voltage > 12.25:
        status = "VOLTAGE_WARNING"
    elif temperature > 42:
        status = "TEMP_WARNING"

    return {
        "machine_id": machine_id,
        "online": online,
        "voltage": voltage,
        "current": current,
        "temperature": temperature,
        "status": status,
        "client_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    print("Mock machine agent started.")
    print(f"Target server: {SERVER_URL}")

    while True:
        for machine_id in MACHINE_IDS:
            payload = build_mock_status(machine_id)

            try:
                response = post_json(SERVER_URL, payload)
                print(f"[OK] {machine_id} -> {response}")
            except Exception as e:
                print(f"[ERROR] {machine_id}: {e}")

        time.sleep(3)


if __name__ == "__main__":
    main()