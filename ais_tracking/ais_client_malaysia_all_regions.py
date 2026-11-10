"""SEA SENTINEL V2 — Malaysian coastal AISStream receiver.

Save as ais_tracking/ais_client.py after backing up the existing receiver.
AIS coverage depends on the upstream feed; no vessel locations are fabricated.
"""
from vessel_tracker import VesselTracker
from live_store import save_snapshot

import asyncio
import json
import os

import websockets
from websockets.exceptions import ConnectionClosed

AIS_URL = 'wss://stream.aisstream.io/v0/stream'

# Bounding boxes use [latitude, longitude] southwest/northeast corners.
# Monitoring areas are approximate, not official maritime/state boundaries.
MALAYSIA_AIS_REGIONS = {
    'Strait of Malacca / West Coast': [[1.0, 98.0], [7.0, 103.0]],
    'Southern Peninsula / Johor': [[1.0, 102.0], [3.0, 105.0]],
    'East Coast Peninsula': [[2.0, 102.5], [7.5, 105.5]],
    'Sarawak / Northwest Borneo': [[0.5, 108.0], [5.5, 115.5]],
    'Sabah / Northeast Borneo': [[3.5, 114.0], [8.0, 120.5]],
}

POSITION_TYPES = (
    'PositionReport',
    'StandardClassBPositionReport',
    'ExtendedClassBPositionReport',
)


def position_from_message(data):
    """Parse real Class A / Class B dynamic AIS positions."""
    message_type = data.get('MessageType')
    if message_type not in POSITION_TYPES:
        return None
    metadata = data.get('MetaData') or {}
    payload = (data.get('Message') or {}).get(message_type) or {}
    if not isinstance(payload, dict):
        return None

    latitude = payload.get('Latitude')
    longitude = payload.get('Longitude')
    mmsi = metadata.get('MMSI') or payload.get('UserID')
    try:
        lat, lon = float(latitude), float(longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
    except (ValueError, TypeError):
        return None
    if mmsi is None:
        return None

    return {
        'mmsi': mmsi,
        'name': metadata.get('ShipName') or payload.get('Name') or 'Unknown',
        'latitude': lat,
        'longitude': lon,
        'speed_knots': payload.get('Sog'),
        'course': payload.get('Cog'),
    }


async def receive_ais():
    api_key = os.getenv('AISSTREAM_API_KEY', '').strip()
    if not api_key or api_key == '^V':
        print('ERROR: Set AISSTREAM_API_KEY in this PowerShell session before starting.')
        return

    subscription = {
        'APIKey': api_key,
        'BoundingBoxes': list(MALAYSIA_AIS_REGIONS.values()),
        'FilterMessageTypes': list(POSITION_TYPES),
    }
    tracker = VesselTracker()
    print(f'Configured {len(MALAYSIA_AIS_REGIONS)} Malaysian coastal monitoring regions:')
    for name in MALAYSIA_AIS_REGIONS:
        print(' -', name)

    while True:
        try:
            print('Connecting to AISStream...')
            async with websockets.connect(
                AIS_URL, ping_interval=20, ping_timeout=20, open_timeout=20,
            ) as websocket:
                await websocket.send(json.dumps(subscription))
                print('Subscription sent; waiting for real AIS position messages...')
                async for raw_message in websocket:
                    try:
                        data = json.loads(raw_message)
                    except (ValueError, TypeError):
                        print('Skipped malformed AIS message')
                        continue
                    if data.get('MessageType') == 'SubscriptionConfirmation':
                        print('AISStream subscription confirmed')
                        continue
                    if data.get('MessageType') not in POSITION_TYPES:
                        print('Received message type:', data.get('MessageType'))
                        continue
                    vessel = position_from_message(data)
                    if vessel:
                        lat = vessel["latitude"]
                        lon = vessel["longitude"]
                        if lat > 2.0 or lon < 103.0:
                            print(
                                "OUTSIDE SINGAPORE DIAGNOSTIC AREA:",
                                vessel["name"], lat, lon,
                                flush=True,
                            )
                    if vessel and tracker.update(vessel):
                        save_snapshot(tracker.get_vessels())
                        print('VESSEL:', vessel)
                        print('Unique vessels tracked:', tracker.vessel_count())
        except ConnectionClosed as error:
            print('Connection closed:', error)
        except (OSError, TimeoutError) as error:
            print('Network connection error:', error)
        except Exception as error:
            # Avoid silently exiting the long-running receiver.
            print('Receiver error:', type(error).__name__, str(error))
        print('Retrying in 10 seconds...')
        await asyncio.sleep(10)


if __name__ == '__main__':
    try:
        asyncio.run(receive_ais())
    except KeyboardInterrupt:
        print('\nAIS tracking stopped.')
