import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "vessels_live.json"


def save_snapshot(vessels):
    """Safely save current AIS vessel data."""
    if isinstance(vessels, dict):
        vessels = list(vessels.values())

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "vessels": vessels,
    }

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_FILE.parent,
            suffix=".tmp",
            delete=False,
        ) as file:
            json.dump(payload, file, indent=2, default=str)
            temp_path = file.name

        os.replace(temp_path, DATA_FILE)

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def load_snapshot():
    """Load the latest saved AIS vessel data."""
    if not DATA_FILE.exists():
        return {"updated_at": None, "vessels": []}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return {
                "updated_at": data.get("updated_at"),
                "vessels": data.get("vessels", []),
            }

        if isinstance(data, list):
            return {"updated_at": None, "vessels": data}

    except (OSError, ValueError, TypeError):
        pass

    return {"updated_at": None, "vessels": []}
