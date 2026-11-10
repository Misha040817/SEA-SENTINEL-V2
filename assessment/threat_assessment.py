"""Explainable, rule-based maritime operational risk screening.

Inputs are AIS-derived observations, not YOLO classification confidence.
Risk scores are illustrative screening weights, NOT validated threat probabilities.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping, Iterable
import math

@dataclass(frozen=True)
class AssessmentConfig:
    max_ais_age_minutes: float = 15.0
    speed_limit_knots: float = 25.0  # context-dependent: adjust for local area and vessel type
    loitering_minutes: float = 45.0
    route_deviation_nm: float = 3.0
    moderate_score: int = 25
    high_score: int = 60

WEIGHTS = {
    "restricted_zone_entry": 35,
    "speed_exceeded": 15,
    "ais_gap": 15,
    "route_deviation": 15,
    "loitering": 10,
    "visual_ais_mismatch": 10,
}

def _utc_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Timestamp must be ISO 8601 string or datetime")
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include timezone (e.g. +00:00 or Z)")
    return dt.astimezone(timezone.utc)

def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(n) or not low <= n <= high:
        raise ValueError(f"{name} must be finite and between {low} and {high}")
    return n

def assess_vessel(record: Mapping[str, Any], config: AssessmentConfig | None = None,
                  now: datetime | None = None) -> dict[str, Any]:
    """Assess one AIS observation. Explicit None means unknown, not false.

    Expected keys: mmsi, timestamp, latitude, longitude, sog_knots,
    restricted_zone_entry, route_deviation_nm, loitering_minutes,
    visual_ais_mismatch. Zone entry and mismatch must come from independently
    verified geospatial/camera matching pipelines, not guesses.
    """
    cfg = config or AssessmentConfig()
    now_utc = _utc_time(now or datetime.now(timezone.utc))
    identifier = str(record.get("mmsi") or "UNKNOWN")
    reasons: list[dict[str, Any]] = []
    missing: list[str] = []
    data_errors: list[str] = []
    def add(code: str, detail: str):
        reasons.append({"code": code, "points": WEIGHTS[code], "evidence": detail})
    def numeric_field(key: str, low: float, high: float):
        v = record.get(key)
        if v is None or v == "":
            missing.append(key)
            return None
        try:
            return _number(v, key, low, high)
        except ValueError as exc:
            data_errors.append(str(exc))
            return None
    lat = numeric_field("latitude", -90, 90)
    lon = numeric_field("longitude", -180, 180)
    speed = numeric_field("sog_knots", 0, 100)
    timestamp = record.get("timestamp")
    age = None
    if timestamp is None or timestamp == "":
        missing.append("timestamp")
    else:
        try:
            age = (now_utc - _utc_time(timestamp)).total_seconds() / 60
            if age < -2:
                data_errors.append("AIS timestamp is in the future")
        except ValueError as exc:
            data_errors.append(str(exc))
    if age is not None and age > cfg.max_ais_age_minutes:
        add("ais_gap", f"Latest AIS observation {age:.1f} minutes old (limit {cfg.max_ais_age_minutes:.1f})")
    if speed is not None and speed > cfg.speed_limit_knots:
        add("speed_exceeded", f"SOG {speed:.1f} kn exceeds configured {cfg.speed_limit_knots:.1f} kn")
    for key in ("restricted_zone_entry", "visual_ais_mismatch"):
        value = record.get(key)
        if value is None or value == "":
            missing.append(key)
        elif type(value) is not bool:
            data_errors.append(f"{key} must be true, false, or null")
        elif value:
            if key == "restricted_zone_entry" and (lat is None or lon is None):
                data_errors.append("Restricted-zone entry requires valid coordinates")
            else:
                add(key, "Verified zone entry" if key == "restricted_zone_entry" else "Unresolved camera/AIS association")
    route = numeric_field("route_deviation_nm", 0, 10000)
    if route is not None and route > cfg.route_deviation_nm:
        add("route_deviation", f"Route deviation {route:.1f} nm exceeds {cfg.route_deviation_nm:.1f} nm")
    loiter = numeric_field("loitering_minutes", 0, 100000)
    if loiter is not None and loiter > cfg.loitering_minutes:
        add("loitering", f"Loitering {loiter:.1f} min exceeds {cfg.loitering_minutes:.1f} min")
    score = sum(r["points"] for r in reasons)
    # No Low/Moderate/High verdict if required contextual evidence is missing or invalid.
    # AIS gap can still be shown as an alert indicator even when the record is stale.
    essential = {"timestamp", "latitude", "longitude", "sog_knots", "restricted_zone_entry",
                 "route_deviation_nm", "loitering_minutes", "visual_ais_mismatch"}
    if data_errors or essential.intersection(missing):
        level = "Insufficient Data"
    else:
        level = "High" if score >= cfg.high_score else "Moderate" if score >= cfg.moderate_score else "Low"
    return {
        "mmsi": identifier, "risk_level": level, "score": score,
        "indicators": reasons, "missing_fields": sorted(set(missing)),
        "data_errors": data_errors, "assessed_at": now_utc.isoformat(),
        "ais_age_minutes": round(age, 2) if age is not None else None,
        "policy": "Illustrative operational screening; human review required; not a threat probability",
    }

def assess_many(records: Iterable[Mapping[str, Any]], config: AssessmentConfig | None = None,
                now: datetime | None = None) -> list[dict[str, Any]]:
    return [assess_vessel(record, config, now) for record in records]
