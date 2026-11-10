import asyncio
import json
import os
from collections import Counter
from datetime import datetime, timezone
import websockets

URL = "wss://stream.aisstream.io/v0/stream"

REGIONS = {
    "Johor / Singapore": (1.0, 3.0, 102.0, 105.0),
    "Selangor / Port Klang": (2.5, 3.6, 100.5, 102.0),
    "Penang / Perak": (4.0, 6.0, 99.0, 102.0),
    "Kelantan / Terengganu": (4.0, 7.5, 102.0, 105.5),
    "Pahang": (2.5, 4.5, 102.5, 105.5),
    "Sabah": (3.5, 8.0, 115.0, 120.5),
    "Sarawak": (0.5, 5.5, 108.0, 115.5),
}

SUBSCRIPTIONS = [
    [[1.0, 98.0], [7.0, 103.0]],
    [[1.0, 102.0], [3.0, 105.0]],
    [[2.0, 102.5], [7.5, 105.5]],
    [[0.5, 108.0], [5.5, 115.5]],
    [[3.5, 114.0], [8.0, 120.5]],
]

TYPES = [
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
]

async def main():
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not key:
        print("AISSTREAM_API_KEY is not set in this terminal.")
        return

    counts = Counter()
    unique = {name: set() for name in REGIONS}
    rejected = Counter()
    total = 0

    print("Connecting to AISStream...")
    try:
        async with websockets.connect(
            URL, compression="deflate",
            ping_interval=20, ping_timeout=20
        ) as ws:
            await ws.send(json.dumps({
                "APIKey": key,
                "BoundingBoxes": SUBSCRIPTIONS,
                "FilterMessageTypes": TYPES
            }))

            print("Monitoring incoming reports for 900 seconds...")
            end = asyncio.get_running_loop().time() + 900

            while True:
                remaining = end - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break

                msg = json.loads(raw)
                kind = msg.get("MessageType", "")

                if kind == "SubscriptionConfirmation":
                    print("Subscription confirmed.")
                    continue

                if kind not in TYPES:
                    rejected[kind or "Unknown"] += 1
                    if kind in ("Error", "SubscriptionError"):
                        print("AISStream error:", msg.get("Message"))
                    continue

                meta = msg.get("MetaData") or {}
                payload = (msg.get("Message") or {}).get(kind) or {}

                lat = payload.get("Latitude")
                lon = payload.get("Longitude")

                if lat is None:
                    lat = meta.get("latitude", meta.get("Latitude"))
                if lon is None:
                    lon = meta.get("longitude", meta.get("Longitude"))

                try:
                    lat, lon = float(lat), float(lon)
                except (ValueError, TypeError):
                    rejected["Invalid coordinates"] += 1
                    continue

                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    rejected["Invalid coordinates"] += 1
                    continue

                total += 1
                mmsi = str(meta.get("MMSI") or payload.get("UserID") or "")

                for name, (south, north, west, east) in REGIONS.items():
                    if south <= lat <= north and west <= lon <= east:
                        counts[name] += 1
                        if mmsi:
                            unique[name].add(mmsi)

    except Exception as exc:
        print("Connection/test error:", type(exc).__name__, str(exc))

    print("\n=== AISSTREAM COVERAGE RESULTS ===")
    print("Valid position reports:", total)
    print(f"{'Region':30} {'Reports':>8} {'Vessels':>9}")
    print("-" * 50)

    for name in REGIONS:
        print(f"{name:30} {counts[name]:8} {len(unique[name]):9}")

    print("\nOther message types / rejected:", dict(rejected))
    print("Completed:", datetime.now(timezone.utc).isoformat())

asyncio.run(main())


