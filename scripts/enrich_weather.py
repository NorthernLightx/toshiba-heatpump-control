"""
Backfill missing outdoor temperatures from Open-Meteo weather API.

Fills NULL outdoor_temp values in the readings database using historical
weather data. Open-Meteo is free and requires no API key.

Usage:
    python scripts/enrich_weather.py --lat 59.33 --lon 18.07

Latitude/longitude default to Stockholm, Sweden. Adjust for your location.
"""

import argparse
import json
import sqlite3
import urllib.request
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "readings.db"

OPEN_METEO_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude={lat}&longitude={lon}"
    "&start_date={start}&end_date={end}"
    "&hourly=temperature_2m&timezone=UTC"
)


def get_null_date_range(db: sqlite3.Connection) -> tuple[str, str] | None:
    """Get the date range of readings with NULL outdoor_temp."""
    row = db.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM readings "
        "WHERE outdoor_temp IS NULL"
    ).fetchone()
    if not row[0]:
        return None
    return row[0][:10], row[1][:10]


def fetch_weather(lat: float, lon: float, start: str, end: str) -> dict:
    """Fetch hourly temperature data from Open-Meteo."""
    url = OPEN_METEO_URL.format(lat=lat, lon=lon, start=start, end=end)
    print(f"Fetching weather data from Open-Meteo: {start} to {end}")
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def build_temp_lookup(data: dict) -> dict[str, float]:
    """Build a {ISO hour -> temp} lookup from Open-Meteo response."""
    times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    return {t: v for t, v in zip(times, temps) if v is not None}


def enrich(db: sqlite3.Connection, lookup: dict[str, float]) -> int:
    """Update NULL outdoor_temp rows using the weather lookup."""
    rows = db.execute(
        "SELECT id, timestamp FROM readings WHERE outdoor_temp IS NULL"
    ).fetchall()

    updated = 0
    for row_id, ts in rows:
        # Round timestamp to nearest hour for lookup
        dt = datetime.fromisoformat(ts)
        hour_key = dt.strftime("%Y-%m-%dT%H:00")
        temp = lookup.get(hour_key)
        if temp is not None:
            db.execute(
                "UPDATE readings SET outdoor_temp = ?, outdoor_temp_source = 'weather_api' "
                "WHERE id = ?",
                (temp, row_id),
            )
            updated += 1

    db.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=59.33, help="Latitude (default: Stockholm)")
    parser.add_argument("--lon", type=float, default=18.07, help="Longitude (default: Stockholm)")
    parser.add_argument("--db", type=str, default=str(DB_PATH), help="Path to readings.db")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run the app with data logging enabled first.")
        return

    db = sqlite3.connect(str(db_path))
    total = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    nulls = db.execute("SELECT COUNT(*) FROM readings WHERE outdoor_temp IS NULL").fetchone()[0]
    print(f"Database: {total} readings, {nulls} with missing outdoor temp")

    if nulls == 0:
        print("Nothing to backfill.")
        db.close()
        return

    date_range = get_null_date_range(db)
    if not date_range:
        db.close()
        return

    data = fetch_weather(args.lat, args.lon, date_range[0], date_range[1])
    lookup = build_temp_lookup(data)
    updated = enrich(db, lookup)
    print(f"Updated {updated}/{nulls} readings with weather API data")
    db.close()


if __name__ == "__main__":
    main()
