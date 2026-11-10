from ais_tracking.live_store import load_snapshot
from datetime import datetime, timezone

ZONES = {
 "Johor / Singapore Strait": (1.0, 2.5, 102.5, 104.5),
 "Selangor / Port Klang": (2.5, 3.8, 100.5, 102.0),
 "Penang / Northern Strait": (4.0, 6.5, 99.0, 101.5),
 "Kelantan": (5.3, 7.5, 102.0, 104.5),
 "Terengganu": (4.0, 5.3, 102.5, 105.5),
 "Pahang": (2.5, 4.0, 102.5, 105.5),
 "Sabah": (4.0, 8.0, 115.0, 120.5),
 "Sarawak": (0.5, 5.5, 108.0, 115.5),
}
now = datetime.now(timezone.utc)
counts = {k: {"recent":0, "older":0} for k in ZONES}
for v in load_snapshot().get("vessels", []):
    try:
        lat, lon = float(v["latitude"]), float(v["longitude"])
        dt = datetime.fromisoformat(v["last_seen"].replace("Z", "+00:00"))
        recent = 0 <= (now - dt).total_seconds() <= 1800
    except (ValueError, TypeError, KeyError):
        continue
    for name, (s, n, w, e) in ZONES.items():
        if s <= lat <= n and w <= lon <= e:
            counts[name]["recent" if recent else "older"] += 1
            break
print("Regional AIS coverage (approximate, not legal boundaries)")
for name, values in counts.items():
    print(f"{name:30} recent <=30m: {values['recent']:4} | older: {values['older']:4}")
