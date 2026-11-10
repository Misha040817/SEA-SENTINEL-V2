
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone

import websockets

URL = "wss://stream.openseafeed.com/v1/stream"

REGIONS = {
    "Port Klang / Selangor": (2.5, 3.6, 100.5, 102.0),
    "Penang / Perak": (4.0, 6.0, 99.0, 102.0),
    "Kelantan / Terengganu": (4.0, 7.5, 102.0, 105.5),
    "Pahang": (2.5, 4.5, 102.5, 105.5),
    "Johor / Singapore": (1.0, 3.0, 102.0, 105.0),
    "Sarawak": (0.5, 5.5, 108.0, 115.5),
    "Sabah": (3.5, 8.0, 115.0, 120.5),
}

BOXES = [
    [[south, west], [north, east]]
    for south, north, west, east in REGIONS.values()
]

async def main():
    counts = Counter()
    vessels = {name: set() for name in REGIONS}
    types = Counter()
    fresh = Counter()
    received = 0

    print("Connecting to OpenSeaFeed...")

    try:
        async with websockets.connect(
            URL, open_timeout=20, ping_interval=20
        ) as ws:
            await ws.send(json.dumps({
                "BoundingBoxes": BOXES,
                "FilterMessageTypes": [
                    "PositionReport",
                    "StandardClassBPositionReport",
                    "ExtendedClassBPositionReport",
                ],
                "InitialState": True,
            }))

            print("Monitoring for 300 seconds...")
            end = asyncio.get_running_loop().time() + 300

            while asyncio.get_running_loop().time() < end:
                remaining = end - asyncio.get_running_loop().time()

                try:
                    raw = await asyncio.wait_for(
                        ws.recv(), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    break

                data = json.loads(raw)
                msg_type = data.get("MessageType", "Other")
                types[msg_type] += 1

                payload = data.get("Message", {}).get(msg_type, {})
                metadata = data.get("MetaData", {})

                if not isinstance(payload, dict):
                    continue

                try:
                    lat = float(payload["Latitude"])
                    lon = float(payload["Longitude"])
                except (KeyError, ValueError, TypeError):
                    continue

                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue

                received += 1
                mmsi = str(
                    metadata.get("MMSI")
                    or payload.get("UserID")
                    or ""
                )

                # A received/replayed position is not necessarily fresh.
                timestamp = (
                    metadata.get("time_utc")
                    or data.get("time_utc")
                    or metadata.get("Timestamp")
                )
                age_minutes = None
                if isinstance(timestamp, str):
                    try:
                        seen = datetime.fromisoformat(
                            timestamp.replace("Z", "+00:00")
                        )
                        if seen.tzinfo is not None:
                            age_minutes = (
                                datetime.now(timezone.utc) - seen
                            ).total_seconds() / 60
                    except ValueError:
                        pass

                for name, (south, north, west, east) in REGIONS.items():
                    if south <= lat <= north and west <= lon <= east:
                        counts[name] += 1
                        if mmsi:
                            vessels[name].add(mmsi)
                        if age_minutes is not None and 0 <= age_minutes <= 30:
                            fresh[name] += 1

    except Exception as error:
        print("Connection or parsing error:", repr(error))

    print("\n=== OPENSEAFEED RESULTS ===")
    print(f"Parsed positions: {received}")
    print(f"{'Region':28} {'Reports':>8} {'Vessels':>8} {'Fresh':>8}")
    print("-" * 58)

    for name in REGIONS:
        print(
            f"{name:28} {counts[name]:8} "
            f"{len(vessels[name]):8} {fresh[name]:8}"
        )

    print("Message types:", dict(types))
    print("Note: Fresh counts depend on recognized source timestamps.")

asyncio.run(main())
