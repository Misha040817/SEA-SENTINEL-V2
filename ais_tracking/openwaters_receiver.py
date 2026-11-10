
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Open Waters AIS API
API_URL = "https://ais.openwaters.io/v1/vessels"

# Bounding box order: south, west, north, east
REGIONS = {
    "Port Klang / Selangor": [2.7, 100.8, 3.5, 101.6],
    "Penang": [5.1, 100.0, 5.7, 100.6],
    "Sarawak / Kuching": [1.2, 109.5, 2.0, 111.0],
    "Sarawak / Bintulu": [3.0, 112.5, 3.8, 113.5],
    "Kelantan": [5.7, 102.0, 6.5, 103.0],
    "Terengganu": [4.5, 102.5, 5.8, 103.8],
    "Pahang / Kuantan": [3.5, 103.0, 4.3, 104.0],
    "Sabah / Kota Kinabalu": [5.5, 115.5, 6.3, 116.5],
}

MAX_AGE_MINUTES = 30
OUTPUT_FILE = Path(__file__).resolve().parent / "openwaters_vessels.json"


def parse_timestamp(value):
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (AttributeError, ValueError, TypeError):
        return None


def parse_coordinates(feature):
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")

    # Open Waters returns coordinates as "longitude latitude".
    if isinstance(coordinates, str):
        parts = coordinates.split()
    elif isinstance(coordinates, (list, tuple)):
        parts = coordinates
    else:
        return None

    if len(parts) != 2:
        return None

    try:
        lon, lat = float(parts[0]), float(parts[1])
    except (ValueError, TypeError):
        return None

    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    return lat, lon


def fetch_region(name, bbox):
    query = urlencode({"bbox": ",".join(map(str, bbox))})
    request = Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "SeaSentinelV2/1.0"}
    )

    with urlopen(request, timeout=30) as response:
        data = json.load(response)

    features = data.get("features", [])

    if not isinstance(features, list):
        raise ValueError("Unexpected API response format")

    return features


def main():
    now = datetime.now(timezone.utc)
    vessels = {}
    region_stats = {}
    successful_regions = 0

    print("SEA SENTINEL V2 - Open Waters AIS Receiver")
    print("Fetching vessel positions...\n")

    for region, bbox in REGIONS.items():
        try:
            features = fetch_region(region, bbox)
            successful_regions += 1
        except Exception as error:
            print(f"{region}: API error - {error}")
            region_stats[region] = {
                "total": 0,
                "recent": 0,
                "status": "error"
            }
            continue

        recent_count = 0

        for feature in features:
            if not isinstance(feature, dict):
                continue

            properties = feature.get("properties") or {}
            coordinates = parse_coordinates(feature)
            seen = parse_timestamp(properties.get("seen"))

            if coordinates is None or seen is None:
                continue

            age_seconds = (now - seen).total_seconds()

            if not (0 <= age_seconds <= MAX_AGE_MINUTES * 60):
                continue

            mmsi = str(properties.get("mmsi") or "").strip()

            if not mmsi:
                continue

            recent_count += 1
            lat, lon = coordinates

            vessel = {
                "mmsi": mmsi,
                "name": properties.get("name") or "Unknown",
                "latitude": lat,
                "longitude": lon,
                "speed_knots": properties.get("sog"),
                "course": properties.get("cog"),
                "last_seen": seen.isoformat(),
                "source": "openwaters",
                "region": region,
            }

            previous = vessels.get(mmsi)

            if previous is None or (
                vessel["last_seen"] > previous["last_seen"]
            ):
                vessels[mmsi] = vessel

        region_stats[region] = {
            "total": len(features),
            "recent": recent_count,
            "status": "ok"
        }

        print(
            f"{region}: {len(features)} total, "
            f"{recent_count} recent"
        )

        # Small delay between requests
        time.sleep(1)

    snapshot = {
        "source": "openwaters",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "max_age_minutes": MAX_AGE_MINUTES,
        "regions": region_stats,
        "vessels": list(vessels.values()),
    }

    # Avoid overwriting a good snapshot if every request failed.
    if successful_regions == 0:
        print("\nAll API requests failed. Existing snapshot preserved.")
        return

    temporary_file = OUTPUT_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(snapshot, indent=2),
        encoding="utf-8"
    )
    temporary_file.replace(OUTPUT_FILE)

    print("\n--------------------------------")
    print("Unique recent vessels:", len(vessels))
    print("Saved to:", OUTPUT_FILE)
    print("--------------------------------")


if __name__ == "__main__":
    main()
