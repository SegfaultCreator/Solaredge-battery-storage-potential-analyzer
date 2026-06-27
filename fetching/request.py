import requests
import json

SITE_ID = "2464985"

BASE = f"https://monitoringapi.solaredge.com/site/{SITE_ID}"

for endpoint in [
    "overview",
    "details",
    "inventory",
]:
    print(f"\n===== {endpoint} =====")

    r = requests.get(
        f"{BASE}/{endpoint}",
        params={"api_key": API_KEY},
        timeout=30,
    )

    print(r.status_code)

    try:
        print(json.dumps(r.json(), indent=2)[:5000])
    except Exception:
        print(r.text)

from datetime import datetime, timedelta

start = "2026-06-20 00:00:00"
end = "2026-06-20 23:59:59"

tests = [
    (
        "powerDetails",
        {
            "startTime": start,
            "endTime": end,
            "timeUnit": "QUARTER_OF_AN_HOUR",
        },
    ),
    (
        "storageData",
        {
            "startTime": start,
            "endTime": end,
        },
    ),
]

for endpoint, params in tests:
    print(f"\n===== {endpoint} =====")

    r = requests.get(
        f"{BASE}/{endpoint}",
        params={**params, "api_key": API_KEY},
        timeout=30,
    )

    print(r.status_code)

    try:
        print(json.dumps(r.json(), indent=2)[:5000])
    except Exception:
        print(r.text)