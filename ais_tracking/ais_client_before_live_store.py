from vessel_tracker import VesselTracker

import asyncio
import json
import os

import websockets
from websockets.exceptions import ConnectionClosed

AIS_URL = "wss://stream.aisstream.io/v0/stream"

# Approximate Port Klang / Strait of Malacca region
BOUNDING_BOX = [[1.0, 99.0], [5.0, 104.5]]


async def receive_ais():
    api_key = os.getenv("AISSTREAM_API_KEY", "").strip()

    if not api_key or api_key == "^V":
        print("ERROR: Enter your actual AISStream API key.")
        return

    subscription = {
        "APIKey": api_key,
        "BoundingBoxes": [BOUNDING_BOX],
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
