"""
Backfill weather data from Open-Meteo API.

Enriches readings with outdoor temperature, wind speed, humidity,
solar radiation, precipitation, pressure, and cloud cover.
Open-Meteo is free and requires no API key.

Usage:
    python scripts/enrich_weather.py --city Stockholm
    python scripts/enrich_weather.py --lat 59.33 --lon 18.07
"""

import argparse
import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "readings.db"

GEOCODING_URL = (
    "https://geocoding-api.open-meteo.com/v1/search"
    "?name={city}&count=1&language=en&format=json"
)

HOURLY_PARAMS = (
    "temperature_2m,relative_humidity_2m,wind_speed_10m,"
    "surface_pressure,precipitation,cloud_cover,"
    "shortwave_radiation"
)

OPEN_METEO_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude={lat}&longitude={lon}"
    "&start_date={start}&end_date={end}"
    "&hourly=" + HOURLY_PARAMS + "&timezone=UTC"
)

# Maps Open-Meteo field names -> our DB column names
FIELD_MAP = {
    "temperature_2m": "outdoor_temp",
    "wind_speed_10m": "wind_speed_kmh",
    "relative_humidity_2m": "humidity_pct",
    "shortwave_radiation": "solar_radiation_wm2",
    "precipitation": "precipitation_mm",
    "surface_pressure": "pressure_hpa",
    "cloud_cover": "cloud_cover_pct",
}


def get_date_range(db: sqlite3.Connection) -> tuple[str, str] | None:
    """Get the full date range of all readings."""
    row = db.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM readings"
    ).fetchone()
    if not row[0]:
        return None
    return row[0][:10], row[1][:10]


def fetch_weather(lat: float, lon: float, start: str, end: str) -> dict:
    """Fetch hourly weather data from Open-Meteo."""
    url = OPEN_METEO_URL.format(lat=lat, lon=lon, start=start, end=end)
    print(f"Fetching weather data from Open-Meteo: {start} to {end}")
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def build_weather_lookup(data: dict) -> dict[str, dict[str, float]]:
    """Build {ISO hour -> {field: value}} lookup from Open-Meteo response."""
    hourly = data["hourly"]
    times = hourly["time"]
    lookup = {}
    for i, t in enumerate(times):
        row = {}
        for meteo_key, db_col in FIELD_MAP.items():
            val = hourly[meteo_key][i]
            if val is not None:
                row[db_col] = val
        if row:
            lookup[t] = row
    return lookup


def enrich(db: sqlite3.Connection, lookup: dict[str, dict[str, float]]) -> int:
    """Update readings with weather data."""
    rows = db.execute("SELECT id, timestamp FROM readings").fetchall()

    updated = 0
    for row_id, ts in rows:
        dt = datetime.fromisoformat(ts)
        hour_key = dt.strftime("%Y-%m-%dT%H:00")
        weather = lookup.get(hour_key)
        if not weather:
            continue

        # Build SET clause for non-null weather fields
        sets = []
        vals = []
        for col, val in weather.items():
            if col == "outdoor_temp":
                # Only fill outdoor_temp if it's NULL (don't overwrite device data)
                sets.append(f"{col} = COALESCE({col}, ?)")
                vals.append(val)
                sets.append("outdoor_temp_source = CASE WHEN outdoor_temp IS NULL THEN 'weather_api' ELSE outdoor_temp_source END")
            else:
                sets.append(f"{col} = ?")
                vals.append(val)

        vals.append(row_id)
        db.execute(
            f"UPDATE readings SET {', '.join(sets)} WHERE id = ?",
            vals,
        )
        updated += 1

    db.commit()
    return updated


def geocode(city: str) -> tuple[float, float]:
    """Resolve a city name to lat/lon using Open-Meteo geocoding."""
    url = GEOCODING_URL.format(city=urllib.parse.quote(city))
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    results = data.get("results")
    if not results:
        raise ValueError(f"City not found: {city}")
    r = results[0]
    print(f"Resolved '{city}' to {r['name']}, {r.get('country', '')} ({r['latitude']}, {r['longitude']})")
    return r["latitude"], r["longitude"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", type=str, help="City name (e.g. Stockholm, London, Tokyo)")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--db", type=str, default=str(DB_PATH), help="Path to readings.db")
    args = parser.parse_args()

    if args.city:
        args.lat, args.lon = geocode(args.city)
    elif args.lat is None or args.lon is None:
        parser.error("Provide --city or both --lat and --lon")

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run the app with data logging enabled first.")
        return

    db = sqlite3.connect(str(db_path))

    # Run migrations to ensure weather columns exist
    from src.datalog import DataLogger
    dl = DataLogger()
    dl._db = db
    dl._migrate()
    db.commit()

    total = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    print(f"Database: {total} readings")

    date_range = get_date_range(db)
    if not date_range:
        print("No readings to enrich.")
        db.close()
        return

    data = fetch_weather(args.lat, args.lon, date_range[0], date_range[1])
    lookup = build_weather_lookup(data)
    updated = enrich(db, lookup)
    print(f"Enriched {updated}/{total} readings with weather data")
    print(f"Fields: {', '.join(FIELD_MAP.values())}")
    db.close()


if __name__ == "__main__":
    main()
