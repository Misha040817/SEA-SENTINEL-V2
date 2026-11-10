
import json
import math
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

AISSTREAM_FILE = BASE_DIR / "vessels_live.json"
OPENWATERS_FILE = BASE_DIR / "openwaters_vessels.json"
OUTPUT_FILE = BASE_DIR / "combined_vessels.json"

MAX_AGE_MINUTES = 30


def parse_timestamp(value):
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def load_vessels(path):
    if not path.exists():
        print(f"File missing: {path.name}")
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")

        vessels = data.get("vessels", [])
        if not isinstance(vessels, list):
            raise ValueError("Expected a vessel list")

        return vessels

    except (OSError, ValueError) as error:
        print(f"Unable to read {path.name}: {error}")
        return []


def classify_region(lat, lon):
    """Approximate monitoring boxes, not official maritime boundaries."""
    if 0.7 <= lat <= 2.5 and 103.1 <= lon <= 105.0:
        return "Johor / Singapore"
    if 5.0 <= lat <= 7.6 and 115.0 <= lon <= 119.8:
        return "Sabah"
    if 0.5 <= lat <= 5.0 and 109.0 <= lon <= 115.5:
        return "Sarawak"
    if 5.5 <= lat <= 6.8 and 101.8 <= lon <= 103.5:
        return "Kelantan"
    if 4.3 <= lat <= 5.8 and 102.5 <= lon <= 104.0:
        return "Terengganu"
    if 3.2 <= lat <= 4.5 and 102.5 <= lon <= 104.3:
        return "Pahang / Kuantan"
    if 2.5 <= lat <= 3.8 and 100.5 <= lon <= 101.8:
        return "Port Klang / Selangor"
    if 4.8 <= lat <= 6.0 and 99.7 <= lon <= 100.9:
        return "Penang"
    return "Other / Unclassified"


def main():
    now = datetime.now(timezone.utc)
    combined = {}
    source_counts = {"aisstream": 0, "openwaters": 0}

    sources = [
        ("aisstream", AISSTREAM_FILE),
        ("openwaters", OPENWATERS_FILE),
    ]

    for source_name, path in sources:
        vessels = load_vessels(path)

        for vessel in vessels:
            if not isinstance(vessel, dict):
                continue

            mmsi = str(vessel.get("mmsi") or "").strip()
            seen = parse_timestamp(vessel.get("last_seen"))

            if not mmsi or seen is None:
                continue

            age_seconds = (now - seen).total_seconds()

            if not 0 <= age_seconds <= MAX_AGE_MINUTES * 60:
                continue

            try:
                lat = float(vessel["latitude"])
                lon = float(vessel["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            if not (math.isfinite(lat) and math.isfinite(lon)):
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            record = dict(vessel)
            record["mmsi"] = mmsi
            record["latitude"] = lat
            record["longitude"] = lon
            record["last_seen"] = seen.isoformat()
            record["source"] = source_name
            record["region"] = classify_region(lat, lon)

            previous = combined.get(mmsi)

            if previous is None or (
                seen > parse_timestamp(previous["last_seen"])
            ):
                combined[mmsi] = record

    for vessel in combined.values():
        source_counts[vessel["source"]] += 1

    snapshot = {
        "updated_at": now.isoformat(),
        "max_age_minutes": MAX_AGE_MINUTES,
        "total_vessels": len(combined),
        "sources": source_counts,
        "vessels": list(combined.values()),
    }

    temporary_file = OUTPUT_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(snapshot, indent=2),
        encoding="utf-8"
    )
    temporary_file.replace(OUTPUT_FILE)

    print("SEA SENTINEL V2 - Combined AIS Data")
    print("--------------------------------")
    print("AISStream vessels:", source_counts["aisstream"])
    print("Open Waters vessels:", source_counts["openwaters"])
    print("Total unique recent vessels:", len(combined))
    print("Saved to:", OUTPUT_FILE)
    region_counts = {}
    for vessel in combined.values():
        area = vessel["region"]
        region_counts[area] = region_counts.get(area, 0) + 1
    print("Regions:")
    for area, count in sorted(region_counts.items()):
        print(f"  {area}: {count}")


if __name__ == "__main__":
    main()
