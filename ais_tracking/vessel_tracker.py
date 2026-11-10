from collections import defaultdict, deque
from datetime import datetime, timezone


class VesselTracker:
    def __init__(self, max_history=100):
        self.vessels = {}
        self.history = defaultdict(
            lambda: deque(maxlen=max_history)
        )

    def update(self, vessel):
        mmsi = vessel.get("mmsi")
        latitude = vessel.get("latitude")
        longitude = vessel.get("longitude")

        if mmsi is None or latitude is None or longitude is None:
            return False

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return False

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return False

        mmsi = str(mmsi).strip()
        if not mmsi:
            return False

        previous = self.vessels.get(mmsi, {})
        timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            **previous,
            **vessel,
            "mmsi": mmsi,
            "name": str(
                vessel.get("name")
                or previous.get("name")
                or "Unknown"
            ).strip(),
            "latitude": latitude,
            "longitude": longitude,
            "last_seen": timestamp,
        }

        self.vessels[mmsi] = record

        self.history[mmsi].append({
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp,
        })

        return True

    def get_vessels(self):
        return list(self.vessels.values())

    def get_history(self, mmsi):
        return list(self.history.get(str(mmsi), []))

    def vessel_count(self):
        return len(self.vessels)
