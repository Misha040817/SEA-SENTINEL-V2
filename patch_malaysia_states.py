from pathlib import Path
import re
import shutil
import py_compile

path = Path("ais_tracking/ais_dashboard.py")
backup = Path("ais_tracking/ais_dashboard_before_state_labels.py")

source = path.read_text(encoding="utf-8-sig")

if "SEA_SENTINEL_STATE_LABEL_LAYER" in source:
    print("State label patch already installed.")
    raise SystemExit(0)

if not path.exists() or not source.strip():
    raise SystemExit("Dashboard missing or empty. No changes made.")

shutil.copy2(path, backup)

state_code = '''
# SEA_SENTINEL_STATE_LABEL_LAYER
# Reference label positions, not official state boundaries.
STATE_LABELS = {
    "Perlis": (6.44, 100.20),
    "Kedah": (6.05, 100.65),
    "Pulau Pinang": (5.35, 100.30),
    "Perak": (4.60, 101.00),
    "Selangor": (3.10, 101.35),
    "Negeri Sembilan": (2.72, 102.10),
    "Melaka": (2.20, 102.25),
    "Johor": (2.00, 103.45),
    "Pahang": (3.85, 102.85),
    "Terengganu": (5.10, 103.05),
    "Kelantan": (5.95, 102.20),
    "Sabah": (5.55, 116.40),
    "Sarawak": (2.70, 113.00),
}

STATE_COASTAL_ZONES = {
    "Johor": (1.0, 2.55, 102.45, 104.7),
    "Melaka": (2.0, 2.6, 101.8, 102.6),
    "Negeri Sembilan": (2.4, 2.9, 101.4, 102.1),
    "Selangor": (2.65, 3.8, 100.6, 101.7),
    "Perak": (3.7, 5.05, 99.7, 101.25),
    "Pulau Pinang": (5.1, 5.7, 99.8, 100.75),
    "Kedah": (5.7, 6.45, 99.2, 100.9),
    "Perlis": (6.35, 6.75, 99.8, 100.5),
    "Pahang": (2.6, 4.25, 102.7, 105.1),
    "Terengganu": (4.15, 5.85, 102.5, 105.1),
    "Kelantan": (5.75, 7.0, 101.8, 104.6),
    "Sabah": (4.0, 8.0, 115.0, 120.5),
    "Sarawak": (0.5, 5.5, 108.0, 115.0),
}

def nearby_state(lat, lon):
    for name, (south, north, west, east) in STATE_COASTAL_ZONES.items():
        if south <= lat <= north and west <= lon <= east:
            return name
    return "Other / Offshore"

def state_label_layer():
    data = [
        {"name": name, "latitude": lat, "longitude": lon}
        for name, (lat, lon) in STATE_LABELS.items()
    ]
    return pdk.Layer(
        "TextLayer",
        data=data,
        get_position="[longitude, latitude]",
        get_text="name",
        get_size=15,
        size_min_pixels=10,
        size_max_pixels=18,
        get_color=[235, 247, 255, 255],
        get_background_color=[5, 22, 36, 210],
        background=True,
        get_alignment_baseline="center",
        get_text_anchor="middle",
        pickable=False
    )
'''

# Insert after imports, before the first Streamlit setup call.
anchor = "st.set_page_config("
if anchor not in source:
    raise SystemExit("Cannot find Streamlit setup. No changes made.")
source = source.replace(anchor, state_code + "\n" + anchor, 1)

# Make the new state dropdown filter use coastal zones.
old_filter = 'filtered = filtered[filtered["region"] == region]'
new_filter = '''if region in STATE_COASTAL_ZONES:
                filtered = filtered[
                    filtered.apply(
                        lambda r: nearby_state(
                            r["latitude"], r["longitude"]
                        ) == region,
                        axis=1
                    )
                ]
            else:
                filtered = filtered[filtered["region"] == region]'''

if old_filter not in source:
    raise SystemExit("Expected filter not found. No changes made.")
source = source.replace(old_filter, new_filter, 1)

# Include geographic labels alongside the vessel marker layer.
old_layers = "layers=[layer],"
new_layers = "layers=[layer, state_label_layer()],"

if old_layers not in source:
    raise SystemExit("Expected map layer not found. No changes made.")
source = source.replace(old_layers, new_layers, 1)

# Save to a temporary file, compile it, then replace the dashboard.
temp = path.with_name("ais_dashboard_state_test.py")
temp.write_text(source, encoding="utf-8")
try:
    py_compile.compile(str(temp), doraise=True)
    temp.replace(path)
    print("SUCCESS: Malaysian state labels and coastal filtering installed.")
except Exception:
    temp.unlink(missing_ok=True)
    print("Patch failed. Original dashboard remains unchanged.")
    raise
