"""SEA SENTINEL: independent AIS snapshot archiver. Run alongside receivers/combiner.

Only records real observations present in combined_vessels.json. Does not fabricate
positions, interpolate routes, or assert speed-only screening is a confirmed threat.
"""
import argparse
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'combined_vessels.json'
POSITION_DB = BASE / 'ais_position_history.sqlite3'
RISK_DB = BASE / 'ais_risk_assessments.sqlite3'


def observed_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def region(lat, lon):
    if .7 <= lat <= 2.5 and 103.1 <= lon <= 105.0: return 'Johor / Singapore'
    if 5.0 <= lat <= 7.6 and 115.0 <= lon <= 119.8: return 'Sabah'
    if .5 <= lat <= 5.0 and 109.0 <= lon <= 115.5: return 'Sarawak'
    if 5.5 <= lat <= 6.8 and 101.8 <= lon <= 103.5: return 'Kelantan'
    if 4.3 <= lat <= 5.8 and 102.5 <= lon <= 104.0: return 'Terengganu'
    if 3.2 <= lat <= 4.5 and 102.5 <= lon <= 104.3: return 'Pahang / Kuantan'
    if 2.5 <= lat <= 3.8 and 100.5 <= lon <= 101.8: return 'Port Klang / Selangor'
    if 4.8 <= lat <= 6.0 and 99.7 <= lon <= 100.9: return 'Penang'
    return 'Other'


def init_dbs():
    with sqlite3.connect(POSITION_DB, timeout=20) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''CREATE TABLE IF NOT EXISTS positions (
            mmsi TEXT NOT NULL, observed TEXT NOT NULL, name TEXT,
            latitude REAL NOT NULL, longitude REAL NOT NULL,
            region TEXT, source TEXT, speed_knots REAL,
            PRIMARY KEY (mmsi, observed))''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_positions_observed ON positions(observed)')
    with sqlite3.connect(RISK_DB, timeout=20) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('''CREATE TABLE IF NOT EXISTS assessments (
            mmsi TEXT NOT NULL, observed TEXT NOT NULL, hazard TEXT NOT NULL,
            name TEXT, region TEXT, source TEXT, speed_knots REAL,
            likelihood INTEGER, consequence INTEGER, risk_score INTEGER,
            level TEXT, reason TEXT, recommended_control TEXT,
            evidence_status TEXT, review_status TEXT DEFAULT 'Pending review',
            PRIMARY KEY(mmsi,observed,hazard))''')


def collect_once(advisory=15.0, elevated=25.0):
    if not DATA_FILE.exists():
        logging.warning('Missing %s; start the AIS receivers and combiner.', DATA_FILE)
        return 0, 0
    raw = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    records = raw.get('vessels', []) if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        raise ValueError('combined_vessels.json must contain a list of vessels')
    now = datetime.now(timezone.utc)
    positions, assessments = [], []
    for r in records:
        if not isinstance(r, dict):
            continue
        mmsi = str(r.get('mmsi') or '').strip()
        if not mmsi or mmsi.lower() in ('unknown', 'none', 'nan'):
            continue
        obs = observed_time(r.get('last_seen'))
        if obs is None or not 0 <= (now - obs).total_seconds() <= 1800:
            continue
        try:
            lat, lon = float(r.get('latitude')), float(r.get('longitude'))
        except (ValueError, TypeError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        name = str(r.get('name') or 'Unknown')
        source = str(r.get('source') or 'unknown')
        area = region(lat, lon)
        stamp = obs.isoformat()
        try:
            speed = float(r.get('speed_knots'))
            if not 0 <= speed <= 100:
                speed = None
        except (ValueError, TypeError):
            speed = None
        positions.append((mmsi, stamp, name, lat, lon, area, source, speed))
        if speed is None or speed < advisory:
            continue
        if speed >= elevated:
            hazard, likelihood, consequence = 'Elevated reported vessel speed', 3, 3
            reason = f'Reported speed {speed:.1f} kn meets high-speed screening threshold ({elevated:g} kn).'
            control = 'Verify AIS speed and vessel type; review traffic density and navigational context; continue monitoring.'
        else:
            hazard, likelihood, consequence = 'Speed warrants contextual review', 2, 2
            reason = f'Reported speed {speed:.1f} kn meets advisory threshold ({advisory:g} kn).'
            control = 'Check vessel type, local speed guidance and traffic conditions; monitor for changes.'
        score = likelihood * consequence
        level = 'Critical' if score >= 20 else 'High' if score >= 10 else 'Moderate' if score >= 5 else 'Low'
        assessments.append((mmsi, stamp, hazard, name, area, source, speed,
                            likelihood, consequence, score, level, reason, control,
                            'AIS speed only; context not verified'))
    with sqlite3.connect(POSITION_DB, timeout=20) as conn:
        before = conn.total_changes
        conn.executemany('INSERT OR IGNORE INTO positions VALUES (?,?,?,?,?,?,?,?)', positions)
        added_positions = conn.total_changes - before
    with sqlite3.connect(RISK_DB, timeout=20) as conn:
        before = conn.total_changes
        conn.executemany('''INSERT OR IGNORE INTO assessments
            (mmsi,observed,hazard,name,region,source,speed_knots,likelihood,
             consequence,risk_score,level,reason,recommended_control,evidence_status)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', assessments)
        added_assessments = conn.total_changes - before
    return added_positions, added_assessments


def main():
    parser = argparse.ArgumentParser(description='Archive real AIS snapshots into SQLite continuously')
    parser.add_argument('--interval', type=int, default=15, help='Polling interval seconds (default 15)')
    parser.add_argument('--once', action='store_true', help='Collect once and exit')
    args = parser.parse_args()
    if args.interval < 1:
        parser.error('--interval must be >= 1')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    init_dbs()
    logging.info('Collector started. Source: %s', DATA_FILE)
    try:
        while True:
            try:
                added, flagged = collect_once()
                logging.info('New real AIS positions: %d | New speed-screening records: %d', added, flagged)
            except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
                logging.warning('Collection retry: %s', exc)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logging.info('Collector stopped.')


if __name__ == '__main__':
    main()
