"""SEA SENTINEL V2 AISStream receiver: process Class A and Class B positions."""
from vessel_tracker import VesselTracker
from live_store import save_snapshot

import asyncio
import json
import os
import math

import websockets
from websockets.exceptions import ConnectionClosed

AIS_URL = "wss://stream.aisstream.io/v0/stream"

# Approximate monitoring regions, not legal maritime boundaries.
MALAYSIA_AIS_REGIONS = {
    "Strait of Malacca / West Coast": [[1.0, 98.0], [7.0, 103.0]],
    "Southern Peninsula / Johor": [[1.0, 102.0], [3.0, 105.0]],
    "East Coast Peninsula": [[2.0, 102.5], [7.5, 105.5]],
    "Sarawak / Northwest Borneo": [[0.5, 108.0], [5.5, 115.5]],
    "Sabah / Northeast Borneo": [[3.5, 114.0], [8.0, 120.5]],
}
BOUNDING_BOXES = list(MALAYSIA_AIS_REGIONS.values())
POSITION_TYPES = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
)


def extract_position(data):
    """Normalize AISStream Class A/B position payloads for VesselTracker."""
    message_type = data.get("MessageType")
    if message_type not in POSITION_TYPES:
        return None
    metadata = data.get("MetaData") or {}
    payload = (data.get("Message") or {}).get(message_type) or {}
    if not isinstance(payload, dict):
        return None

    lat = payload.get("Latitude")
    lon = payload.get("Longitude")
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    # AIS uses 91/181 for unavailable positions; geographic range check excludes them.
    mmsi = metadata.get("MMSI") or payload.get("UserID")
    if not mmsi:
        return None
    name = metadata.get("ShipName") or payload.get("Name") or "Unknown"
    return {
        "mmsi": mmsi,
        "name": name,
        "latitude": lat,
        "longitude": lon,
        "speed_knots": payload.get("Sog"),
        "course": payload.get("Cog"),
    }


async def receive_ais():
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()
    if not api_key or api_key == "^V":
        print("ERROR: Set AISSTREAM_API_KEY in this PowerShell session first.")
        return

    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": BOUNDING_BOXES,
        "FilterMessageTypes": list(POSITION_TYPES),
    }
    tracker = VesselTracker()
    counts = {message_type: 0 for message_type in POSITION_TYPES}

    while True:
        try:
            print("Connecting to AISStream (Malaysia monitoring regions)...")
            async with websockets.connect(
                AIS_URL, ping_interval=20, ping_timeout=20, open_timeout=20
            ) as websocket:
                await websocket.send(json.dumps(subscription))
                print("Subscription sent; waiting for AIS position reports...")
                async for raw_message in websocket:
                    data = json.loads(raw_message)
                    message_type = data.get("MessageType")
                    if message_type == "SubscriptionConfirmation":
                        print("Subscription confirmed")
                        continue
                    vessel = extract_position(data)
                    if vessel is None:
                        if message_type in POSITION_TYPES:
                            print("Skipped invalid position:", message_type)
                        continue
                    counts[message_type] += 1
                    if tracker.update(vessel):
                        save_snapshot(tracker.get_vessels())
                        print(f"VESSEL [{message_type}]: {vessel['name']} | MMSI {vessel['mmsi']} | "
                              f"{vessel['latitude']:.5f}, {vessel['longitude']:.5f}")
                        print("Unique vessels:", tracker.vessel_count(), "| Messages by type:", counts)
        except ConnectionClosed as error:
            print("Connection closed:", error)
        except (OSError, TimeoutError) as error:
            print("Network connection error:", error)
        except json.JSONDecodeError as error:
            print("Invalid JSON message:", error)
        print("Retrying in 10 seconds...")
        await asyncio.sleep(10)


if __name__ == "__main__":
    try:
        asyncio.run(receive_ais())
    except KeyboardInterrupt:
        print("\nAIS tracking stopped.")
