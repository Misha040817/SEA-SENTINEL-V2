"""SEA SENTINEL V2: compatible AIS combiner with Malaysian coastal coverage diagnostics.

Reads existing AISStream/OpenWaters JSON snapshots; does NOT fetch new AIS data.
Only <=30 minute observations are written to combined_vessels.json.
Coastal-area hints are approximate bounding boxes, not official state boundaries.
"""
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
AISSTREAM_FILE = BASE_DIR / 'vessels_live.json'
OPENWATERS_FILE = BASE_DIR / 'openwaters_vessels.json'
OUTPUT_FILE = BASE_DIR / 'combined_vessels.json'
REPORT_FILE = BASE_DIR / 'malaysia_ais_coverage_report.json'
MAX_AGE_MINUTES = 30

# Detailed *coastal monitoring boxes*, not state maritime boundaries.
# Priority matters when boxes overlap. Adjust only after inspecting actual observations.
COASTAL_BOXES = [
    ('Johor / Singapore Strait', 0.7, 2.2, 103.1, 105.0, 'Johor / Singapore'),
    ('Sabah / East Coast', 4.0, 7.6, 117.0, 120.5, 'Sabah'),
    ('Sabah / West Coast', 4.0, 7.6, 115.0, 117.0, 'Sabah'),
    ('Labuan / Brunei Bay', 4.7, 5.7, 114.5, 115.5, 'Sabah'),
    ('Sarawak / Miri', 3.5, 5.0, 112.8, 115.5, 'Sarawak'),
    ('Sarawak / Bintulu', 2.5, 4.0, 112.0, 114.0, 'Sarawak'),
    ('Sarawak / Kuching', 0.5, 2.6, 108.0, 112.0, 'Sarawak'),
    ('Kelantan / Kota Bharu', 5.5, 7.0, 101.8, 103.5, 'Kelantan'),
    ('Terengganu / East Coast', 4.3, 5.5, 102.5, 104.0, 'Terengganu'),
    ('Pahang / Kuantan', 3.2, 4.5, 102.5, 104.3, 'Pahang / Kuantan'),
    ('Penang / Kedah', 5.0, 6.6, 99.7, 101.0, 'Penang'),
    ('Perlis / Langkawi', 6.2, 7.0, 99.0, 100.8, 'Penang'),
    ('Perak / West Coast', 3.7, 5.0, 99.5, 101.2, 'Other / Unclassified'),
    ('Port Klang / Selangor', 2.5, 3.8, 100.5, 101.8, 'Port Klang / Selangor'),
    ('Melaka / Negeri Sembilan Coast', 2.0, 2.9, 101.5, 103.0, 'Other / Unclassified'),
    ('Johor / West Coast', 1.1, 2.4, 102.5, 103.5, 'Johor / Singapore'),
]


def parse_timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None


def load_vessels(path):
    if not path.exists():
        print(f'Missing input: {path.name}')
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        records = data.get('vessels', []) if isinstance(data, dict) else data
        if not isinstance(records, list):
            raise ValueError('Expected vessels list')
        return records
    except (OSError, ValueError) as exc:
        print(f'Unable to read {path.name}: {exc}')
        return []


def classify_coastal_area(lat, lon):
    for name, south, north, west, east, dashboard_region in COASTAL_BOXES:
        if south <= lat <= north and west <= lon <= east:
            return name, dashboard_region
    return 'Other / Unclassified', 'Other / Unclassified'


def main():
    now = datetime.now(timezone.utc)
    combined = {}
    diagnostics = {}
    for source, path in [('aisstream', AISSTREAM_FILE), ('openwaters', OPENWATERS_FILE)]:
        records = load_vessels(path)
        stats = Counter(input_records=len(records))
        for vessel in records:
            if not isinstance(vessel, dict):
                stats['invalid_record'] += 1
                continue
            mmsi = str(vessel.get('mmsi') or '').strip()
            observed = parse_timestamp(vessel.get('last_seen'))
            if not mmsi or observed is None:
                stats['missing_identity_or_time'] += 1
                continue
            try:
                lat, lon = float(vessel['latitude']), float(vessel['longitude'])
            except (KeyError, TypeError, ValueError):
                stats['invalid_position'] += 1
                continue
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                stats['invalid_position'] += 1
                continue
            age = (now - observed).total_seconds()
            if not 0 <= age <= MAX_AGE_MINUTES * 60:
                stats['stale_or_future'] += 1
                continue
            stats['fresh_valid'] += 1
            coastal_area, dashboard_region = classify_coastal_area(lat, lon)
            record = dict(vessel)
            record.update(mmsi=mmsi, latitude=lat, longitude=lon,
                          last_seen=observed.isoformat(), source=source,
                          region=dashboard_region, coastal_area=coastal_area)
            previous = combined.get(mmsi)
            if previous is None or observed > parse_timestamp(previous['last_seen']):
                combined[mmsi] = record
        diagnostics[source] = dict(stats)

    vessels = sorted(combined.values(), key=lambda r: r['last_seen'], reverse=True)
    source_counts = Counter(v['source'] for v in vessels)
    region_counts = Counter(v['region'] for v in vessels)
    coastal_counts = Counter(v['coastal_area'] for v in vessels)
    snapshot = {
        'updated_at': now.isoformat(), 'max_age_minutes': MAX_AGE_MINUTES,
        'total_vessels': len(vessels), 'sources': dict(source_counts), 'vessels': vessels,
    }
    report = {
        'updated_at': now.isoformat(), 'freshness_minutes': MAX_AGE_MINUTES,
        'note': 'Approximate coastal monitoring boxes; not official state boundaries or proof of receiver coverage.',
        'input_diagnostics': diagnostics,
        'total_unique_fresh_vessels': len(vessels),
        'dashboard_regions': dict(sorted(region_counts.items())),
        'coastal_areas': [
            {'area': name, 'fresh_vessels': coastal_counts.get(name, 0),
             'status': 'Fresh observations present' if coastal_counts.get(name, 0) else 'No fresh observations in input files'}
            for name, *_ in COASTAL_BOXES
        ],
        'unclassified_fresh_vessels': coastal_counts.get('Other / Unclassified', 0),
    }
    for target, content in [(OUTPUT_FILE, snapshot), (REPORT_FILE, report)]:
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding='utf-8')
        temp.replace(target)
    print('\nSEA SENTINEL V2 — Malaysia AIS Coverage')
    print('Fresh unique vessels:', len(vessels))
    print('AISStream:', source_counts.get('aisstream', 0), '| Open Waters:', source_counts.get('openwaters', 0))
    print('\nCOASTAL MONITORING AREAS (not state boundaries)')
    for row in report['coastal_areas']:
        print(f"  {row['area']:<37} {row['fresh_vessels']:>5} fresh")
    print('Unclassified:', report['unclassified_fresh_vessels'])
    print('Dashboard data:', OUTPUT_FILE)
    print('Coverage report:', REPORT_FILE)


if __name__ == '__main__':
    main()
