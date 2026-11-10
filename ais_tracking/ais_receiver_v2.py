import json
import os
import random
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import websockets

from ais_tracking.live_store import save_snapshot, load_snapshot

URL = "wss://stream.aisstream.io/v0/stream"
# Geographic monitoring windows, not national maritime boundaries.
REGIONS = {
    "West Coast / Strait of Malacca": [[1.0, 98.0], [7.0, 103.0]],
    "Johor / Singapore Strait": [[1.0, 102.0], [3.0, 105.0]],
    "East Coast / Kelantan / Terengganu / Pahang": [[2.0, 102.5], [7.5, 105.5]],
    "Sarawak": [[0.5, 108.0], [5.5, 115.5]],
    "Sabah": [[3.5, 114.0], [8.0, 120.5]],
}
MAX_AGE_HOURS = 24
SAVE_INTERVAL_SECONDS = 5

def parse_timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None

def load_previous():
    result = {}
    now = datetime.now(timezone.utc)
    for item in load_snapshot().get("vessels", []):
        if not isinstance(item, dict):
            continue
        seen = parse_timestamp(item.get("last_seen"))
        mmsi = str(item.get("mmsi", "")).strip()
        if mmsi and seen and 0 <= (now - seen).total_seconds() <= MAX_AGE_HOURS * 3600:
            result[mmsi] = item
    return result

def valid_position(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)

async def receive_ais():
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not key:
        raise SystemExit("AISSTREAM_API_KEY missing. Set it in this terminal using Read-Host.")
    vessels = load_previous()
    print(f"Recovered {len(vessels)} recent vessel positions from saved snapshot")
    backoff = 2
    while True:
        try:
            print("Connecting to AISStream (compressed WebSocket)...")
            async with websockets.connect(
                URL, compression="deflate", ping_interval=20,
                ping_timeout=20, max_size=4 * 1024 * 1024
            ) as socket:
                await socket.send(json.dumps({
                    "APIKey": key,
                    "BoundingBoxes": list(REGIONS.values()),
                    "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"]
                }))
                backoff = 2
                last_save = asyncio.get_running_loop().time()
                received = 0
                while True:
                    raw = await socket.recv()
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    msg = json.loads(raw)
                    kind = msg.get("MessageType")
                    if kind == "SubscriptionConfirmation":
                        print("Subscription accepted:", msg.get("Message", {}))
                        continue
                    if kind not in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"):
                        if kind in ("Error", "SubscriptionError"):
                            print("AIS service message:", msg)
                        continue
                    meta = msg.get("MetaData") or {}
                    payload = (msg.get("Message") or {}).get(kind) or {}
                    # Class B variants may have nested position objects; use metadata as fallback.
                    lat = payload.get("Latitude", meta.get("latitude", meta.get("Latitude")))
                    lon = payload.get("Longitude", meta.get("longitude", meta.get("Longitude")))
                    if not valid_position(lat, lon):
                        continue
                    mmsi = str(meta.get("MMSI") or payload.get("UserID") or "").strip()
                    if not mmsi:
                        continue
                    previous = vessels.get(mmsi, {})
                    name = str(meta.get("ShipName") or previous.get("name") or "Unknown").strip()
                    vessels[mmsi] = {
                        "mmsi": mmsi, "name": name,
                        "latitude": float(lat), "longitude": float(lon),
                        "speed_knots": payload.get("Sog", previous.get("speed_knots")),
                        "course": payload.get("Cog", previous.get("course")),
                        "last_seen": datetime.now(timezone.utc).isoformat(),
                    }
                    received += 1
                    now = asyncio.get_running_loop().time()
                    if now - last_save >= SAVE_INTERVAL_SECONDS:
                        cutoff = datetime.now(timezone.utc)
                        vessels = {k: v for k, v in vessels.items() if
                            (t := parse_timestamp(v.get("last_seen"))) is not None and
                            0 <= (cutoff - t).total_seconds() <= MAX_AGE_HOURS * 3600}
                        save_snapshot(list(vessels.values()))
                        print(f"AIS reports: {received} | saved vessels: {len(vessels)}", flush=True)
                        last_save = now
        except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError, ValueError) as exc:
            print(f"AIS connection interrupted: {type(exc).__name__}: {exc}", flush=True)
        except Exception as exc:
            print(f"Unexpected receiver error: {type(exc).__name__}: {exc}", flush=True)
        save_snapshot(list(vessels.values()))
        delay = min(backoff, 60) + random.uniform(0, 1)
        print(f"Reconnecting in {delay:.1f}s...", flush=True)
        await asyncio.sleep(delay)
        backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    asyncio.run(receive_ais())
