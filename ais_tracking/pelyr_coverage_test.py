
import os
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_URL = "https://api.pelyr.com/v1/vessels"

REGIONS = {
    "Port Klang / Selangor": "100.5,2.5,102.0,3.6",
    "Penang / Perak": "99.0,4.0,102.0,6.0",
    "Johor / Singapore": "102.0,1.0,105.0,3.0",
    "Kelantan / Terengganu": "102.0,4.0,105.5,7.5",
    "Pahang / Kuantan": "102.5,2.5,105.5,4.5",
    "Sarawak": "108.0,0.5,115.5,5.5",
    "Sabah": "115.0,3.5,120.5,8.0",
}
def test_region(name, bbox, api_key):
    print(f"\n=== {name} ===")

    request = Request(
        f"{API_URL}?bbox={bbox}&max=1000",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)

        vessels = data.get("vessels", [])
        now = datetime.now(timezone.utc)
        recent = 0
        ages = []

        for vessel in vessels:
            position = vessel.get("position") or {}
            timestamp = position.get("ts")

            if not timestamp:
                continue

            try:
                seen = datetime.fromisoformat(
                    timestamp.replace("Z", "+00:00")
                )
                age = (now - seen).total_seconds() / 60
                ages.append(age)

                if 0 <= age <= 30:
                    recent += 1
            except (ValueError, TypeError):
                continue

        print("Total vessels:", len(vessels))
        print("Recent vessels (30 min):", recent)
        print("Truncated:", data.get("truncated"))

        if ages:
            print("Newest age (minutes):", round(min(ages), 1))
            print("Oldest age (minutes):", round(max(ages), 1))

    except HTTPError as error:
        print("HTTP error:", error.code)
        print("Response:", error.read().decode("utf-8")[:500])
    except (URLError, TimeoutError) as error:
        print("Connection error:", error)

def main():
    api_key = os.getenv("PELYR_API_KEY", "").strip()

    if not api_key:
        print("ERROR: PELYR_API_KEY is not set.")
        return

    print("SEA SENTINEL V2 - Pelyr AIS Coverage Test")

    # First test only Port Klang to stay within free limits.
    name = "Johor / Singapore"
    test_region(name, REGIONS[name], api_key)

if __name__ == "__main__":
    main()
