from vessel_tracker import VesselTracker
from live_store import save_snapshot

import asyncio
import json
import os

import websockets
from websockets.exceptions import ConnectionClosed

AIS_URL = "wss://stream.aisstream.io/v0/stream"

# Approximate Port Klang / Strait of Malacca region
# Regional AIS monitoring boxes: [southwest, northeast]
# Coordinates are approximate monitoring regions, not legal maritime boundaries.
MALAYSIA_AIS_REGIONS = {
    "Strait of Malacca / West Coast": [[1.0, 98.0], [7.0, 103.0]],
    "Southern Peninsula / Johor": [[1.0, 102.0], [3.0, 105.0]],
    "East Coast Peninsula": [[2.0, 102.5], [7.5, 105.5]],
    "Sarawak / Northwest Borneo": [[0.5, 108.0], [5.5, 115.5]],
    "Sabah / Northeast Borneo": [[3.5, 114.0], [8.0, 120.5]],
}

BOUNDING_BOXES = list(MALAYSIA_AIS_REGIONS.values())


async def receive_ais():
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()

    if not api_key or api_key == "^V":
        print("ERROR: Enter your actual AISStream API key.")
        return

    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": BOUNDING_BOXES,
        "FilterMessageTypes": ["PositionReport"],
    }

    tracker = VesselTracker()

    while True:
        try:
            print("Connecting to AISStream...")

            async with websockets.connect(
                AIS_URL,
                ping_interval=20,
                ping_timeout=20,
                open_timeout=20,
            ) as websocket:

                await websocket.send(json.dumps(subscription))
                print("Subscription sent. Waiting for AIS messages...")

                async for raw_message in websocket:
                    data = json.loads(raw_message)

                    message_type = data.get("MessageType")
                    if message_type != "PositionReport":
                        print("Received message type:", message_type)
                        continue

                    metadata = data.get("MetaData", {})
                    position = data.get("Message", {}).get(
                        "PositionReport", {}
                    )

                    if not position:
                        continue

                    vessel = {
                        "mmsi": metadata.get("MMSI"),
                        "name": metadata.get("ShipName"),
                        "latitude": position.get("Latitude"),
                        "longitude": position.get("Longitude"),
                        "speed_knots": position.get("Sog"),
                        "course": position.get("Cog"),
                    }

                    if tracker.update(vessel):
                        save_snapshot(tracker.get_vessels())
                        print("VESSEL:", vessel)
                        print("Unique vessels tracked:", tracker.vessel_count())

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
