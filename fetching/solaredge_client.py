from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

import pandas as pd
import requests


def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    text = value.strip()
    if len(text) == 10 and "T" not in text and " " not in text:
        return datetime.fromisoformat(text).replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
    return datetime.fromisoformat(text.replace(" ", "T")).replace(tzinfo=timezone.utc)


def coerce_end_datetime(value: str | datetime) -> datetime:
    dt = parse_datetime(value)
    if isinstance(value, str) and len(value.strip()) == 10:
        return dt.replace(hour=23, minute=59, second=59)
    return dt


def format_api_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def month_range(start: datetime, end: datetime):
    cur = datetime(start.year, start.month, 1, tzinfo=start.tzinfo)
    while cur <= end:
        yield cur.year, cur.month
        if cur.month == 12:
            cur = datetime(cur.year + 1, 1, 1, tzinfo=start.tzinfo)
        else:
            cur = datetime(cur.year, cur.month + 1, 1, tzinfo=start.tzinfo)


def month_start_end(year: int, month: int, tzinfo: timezone | None = None) -> tuple[datetime, datetime]:
    tz = tzinfo or timezone.utc
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=tz) - timedelta(seconds=1)
    else:
        end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=tz) - timedelta(seconds=1)
    return start, end


def iter_day_ranges(start: datetime, end: datetime):
    current = start.date()
    last = end.date()
    while current <= last:
        day_start = datetime.combine(current, time(0, 0, 0), tzinfo=start.tzinfo)
        day_end = min(datetime.combine(current + timedelta(days=1), time(0, 0, 0), tzinfo=start.tzinfo) - timedelta(seconds=1), end)
        yield day_start, day_end
        current += timedelta(days=1)


def fetch_power_details(api_key: str, site_id: str, start: datetime, end: datetime) -> Any:
    base = f"https://monitoringapi.solaredge.com/site/{site_id}"
    params = {
        "api_key": api_key,
        "startTime": format_api_datetime(start),
        "endTime": format_api_datetime(end),
        "timeUnit": "QUARTER_OF_AN_HOUR",
    }
    resp = requests.get(f"{base}/powerDetails", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def flatten_power_details_payload(payload: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return pd.DataFrame(columns=["timestamp", "meter_type", "value"])

    power_details = payload.get("powerDetails", {})
    meters = power_details.get("meters", [])
    if not isinstance(meters, list):
        return pd.DataFrame(columns=["timestamp", "meter_type", "value"])

    for meter in meters:
        if not isinstance(meter, dict):
            continue
        meter_type = meter.get("type", "unknown")
        values = meter.get("values", [])
        if not isinstance(values, list):
            continue
        for entry in values:
            if not isinstance(entry, dict) or "date" not in entry:
                continue
            timestamp = pd.to_datetime(entry.get("date"), errors="coerce")
            if pd.isna(timestamp):
                continue
            value = entry.get("value")
            if value in (None, ""):
                value = pd.NA
            else:
                value = pd.to_numeric(value, errors="coerce")
            rows.append({"timestamp": timestamp, "meter_type": meter_type, "value": value})

    if not rows:
        return pd.DataFrame(columns=["timestamp", "meter_type", "value"])

    frame = pd.DataFrame(rows)
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    frame = frame.reset_index(drop=True)
    return frame


def _is_daylight_timestamp(timestamp: Any, start_hour: int = 5, end_hour: int = 21) -> bool:
    if isinstance(timestamp, pd.Timestamp):
        dt = timestamp.to_pydatetime()
    else:
        dt = pd.to_datetime(timestamp, errors="coerce")
        if pd.isna(dt):
            return False
        dt = dt.to_pydatetime()

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    hour = dt.hour
    return start_hour <= hour < end_hour


def _apply_daylight_filter(flat: pd.DataFrame) -> pd.DataFrame:
    flat = flat.copy()
    flat["production"] = flat["production"].where(flat["timestamp"].apply(_is_daylight_timestamp), 0.0)
    return flat


def build_monthly_time_series(payload: dict[str, Any]) -> pd.DataFrame:
    flat = flatten_power_details_payload(payload)
    if flat.empty:
        return pd.DataFrame(columns=["timestamp", "consumption", "production", "FeedIn", "Purchased", "SelfConsumption"])

    flat = flat.copy()
    flat["value"] = pd.to_numeric(flat["value"], errors="coerce").fillna(0.0) / 1000.0
    flat["meter_type"] = flat["meter_type"].astype(str).str.lower()

    flat["consumption"] = 0.0
    flat["production"] = 0.0
    flat["FeedIn"] = 0.0
    flat["Purchased"] = 0.0
    flat["SelfConsumption"] = 0.0

    flat.loc[flat["meter_type"].str.contains("production", na=False), "production"] = flat["value"]
    flat.loc[flat["meter_type"].str.contains("consumption", na=False), "consumption"] = flat["value"]
    flat.loc[
        flat["meter_type"].str.contains("feed", na=False) | flat["meter_type"].str.contains("export", na=False),
        "FeedIn",
    ] = flat["value"]
    flat.loc[
        flat["meter_type"].str.contains("purchased", na=False) | flat["meter_type"].str.contains("grid import", na=False),
        "consumption",
    ] = flat["value"]

    # map purchased and self-consumption where available
    flat.loc[flat["meter_type"].str.contains("purchased", na=False), "Purchased"] = flat["value"]
    flat.loc[
        flat["meter_type"].str.contains("self", na=False) | flat["meter_type"].str.contains("selfconsumption", na=False),
        "SelfConsumption",
    ] = flat["value"]

    grouped = flat[["timestamp", "consumption", "production", "FeedIn", "Purchased", "SelfConsumption"]].groupby(
        "timestamp", as_index=False
    ).sum()
    grouped = grouped.sort_values("timestamp").reset_index(drop=True)
    return grouped


def fetch_monthly_time_series(api_key: str, site_id: str, start: datetime, end: datetime) -> pd.DataFrame:
    # Fetch primary powerDetails payload
    power_payload = fetch_power_details(api_key, site_id, start, end)

    # Attempt to fetch storageData as well; include any discovered timestamp/value pairs
    storage_payload = {}
    try:
        base = f"https://monitoringapi.solaredge.com/site/{site_id}"
        params = {
            "api_key": api_key,
            "startTime": format_api_datetime(start),
            "endTime": format_api_datetime(end),
        }
        resp = requests.get(f"{base}/storageData", params=params, timeout=60)
        if resp.status_code == 200:
            try:
                storage_payload = resp.json()
            except Exception:
                storage_payload = {}
    except Exception:
        storage_payload = {}

    # Flatten both payloads and merge
    flat_power = flatten_power_details_payload(power_payload)
    flat_storage = _flatten_generic_value_lists(storage_payload, default_type="Storage")

    if flat_power.empty and flat_storage.empty:
        return pd.DataFrame(columns=["timestamp", "consumption", "production", "FeedIn", "Purchased", "SelfConsumption"])

    combined = pd.concat([flat_power, flat_storage], axis=0, ignore_index=True)

    # Build monthly series from the combined flattened frame
    return build_monthly_time_series_from_flat(combined)


def _flatten_generic_value_lists(payload: Any, default_type: str = "unknown") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def walk(obj: Any, parent_type: str | None = None):
        if isinstance(obj, dict):
            # detect a typed container
            p_type = obj.get("type") or parent_type
            for k, v in obj.items():
                if k == "values" and isinstance(v, list):
                    for entry in v:
                        if isinstance(entry, dict) and "date" in entry:
                            ts = pd.to_datetime(entry.get("date"), errors="coerce")
                            val = entry.get("value")
                            if val in (None, ""):
                                val = pd.NA
                            else:
                                val = pd.to_numeric(val, errors="coerce")
                            rows.append({"timestamp": ts, "meter_type": p_type or default_type, "value": val})
                else:
                    walk(v, p_type)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, parent_type)

    walk(payload, None)
    if not rows:
        return pd.DataFrame(columns=["timestamp", "meter_type", "value"])
    frame = pd.DataFrame(rows)
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return frame


def build_monthly_time_series_from_flat(flat: pd.DataFrame) -> pd.DataFrame:
    if flat.empty:
        return pd.DataFrame(columns=["timestamp", "consumption", "production", "FeedIn", "Purchased", "SelfConsumption"])

    flat = flat.copy()
    flat["value"] = pd.to_numeric(flat["value"], errors="coerce").fillna(0.0) / 1000.0
    flat["meter_type"] = flat["meter_type"].astype(str).str.lower()

    flat["consumption"] = 0.0
    flat["production"] = 0.0
    flat["FeedIn"] = 0.0
    flat["Purchased"] = 0.0
    flat["SelfConsumption"] = 0.0

    flat.loc[flat["meter_type"].str.contains("production", na=False), "production"] = flat["value"]
    flat.loc[flat["meter_type"].str.contains("consumption", na=False), "consumption"] = flat["value"]
    flat.loc[
        flat["meter_type"].str.contains("feed", na=False) | flat["meter_type"].str.contains("export", na=False),
        "FeedIn",
    ] = flat["value"]
    flat.loc[
        flat["meter_type"].str.contains("purchased", na=False) | flat["meter_type"].str.contains("grid import", na=False),
        "consumption",
    ] = flat["value"]

    flat.loc[flat["meter_type"].str.contains("purchased", na=False), "Purchased"] = flat["value"]
    flat.loc[
        flat["meter_type"].str.contains("self", na=False) | flat["meter_type"].str.contains("selfconsumption", na=False),
        "SelfConsumption",
    ] = flat["value"]

    grouped = flat[["timestamp", "consumption", "production", "FeedIn", "Purchased", "SelfConsumption"]].groupby(
        "timestamp", as_index=False
    ).sum()
    grouped = grouped.sort_values("timestamp").reset_index(drop=True)
    return grouped


def _iter_meter_value_lists(json_obj: Any):
    if not isinstance(json_obj, dict):
        return
    power_details = json_obj.get("powerDetails", {})
    meters = power_details.get("meters", [])
    for meter in meters:
        values = meter.get("values", [])
        if isinstance(values, list):
            yield values


def _response_spans_range(json_obj: Any, start: datetime, end: datetime) -> bool:
    all_dates: list[pd.Timestamp] = []
    for values in _iter_meter_value_lists(json_obj):
        for entry in values:
            if isinstance(entry, dict) and "date" in entry:
                try:
                    parsed = pd.to_datetime(entry["date"], errors="coerce")
                except Exception:
                    parsed = pd.NaT
                if pd.notna(parsed):
                    all_dates.append(parsed)
    if not all_dates:
        return False
    parsed_dates = pd.to_datetime(all_dates, errors="coerce").dropna()
    if parsed_dates.empty:
        return False
    return parsed_dates.min() <= start and parsed_dates.max() >= end


def _merge_power_details(dst: dict[str, Any], src: dict[str, Any]) -> None:
    if not isinstance(src, dict):
        return
    src_power = src.get("powerDetails", {})
    if not isinstance(src_power, dict):
        return
    dst_power = dst.setdefault("powerDetails", {})
    dst_power.setdefault("timeUnit", src_power.get("timeUnit", "QUARTER_OF_AN_HOUR"))
    dst_power.setdefault("unit", src_power.get("unit", "W"))

    dst_meters = dst_power.setdefault("meters", [])
    src_meters = src_power.get("meters", [])
    if not isinstance(src_meters, list):
        return

    for src_meter in src_meters:
        if not isinstance(src_meter, dict):
            continue
        meter_type = src_meter.get("type")
        target = next((meter for meter in dst_meters if meter.get("type") == meter_type), None)
        if target is None:
            dst_meters.append({"type": meter_type, "values": list(src_meter.get("values", []))})
        else:
            target.setdefault("values", []).extend(src_meter.get("values", []))


def fetch_monthly_power_details(api_key: str, site_id: str, start: datetime, end: datetime) -> dict[str, Any]:
    try:
        payload = fetch_power_details(api_key, site_id, start, end)
        if _response_spans_range(payload, start, end):
            return payload
    except Exception:
        pass

    combined: dict[str, Any] = {"powerDetails": {"timeUnit": "QUARTER_OF_AN_HOUR", "unit": "W", "meters": []}}
    for day_start, day_end in iter_day_ranges(start, end):
        daily_payload = fetch_power_details(api_key, site_id, day_start, day_end)
        _merge_power_details(combined, daily_payload)
    return combined
