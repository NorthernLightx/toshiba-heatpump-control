import csv
import io
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "readings.db"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    indoor_temp REAL,
    outdoor_temp REAL,
    outdoor_temp_source TEXT DEFAULT 'device',
    target_temp REAL,
    energy_wh REAL,
    energy_delta_wh REAL,
    ac_status TEXT,
    ac_mode TEXT,
    fan_mode TEXT,
    power_selection TEXT,
    wind_speed_kmh REAL,
    humidity_pct REAL,
    solar_radiation_wm2 REAL,
    precipitation_mm REAL,
    pressure_hpa REAL,
    cloud_cover_pct REAL
)
"""

INSERT_READING = """
INSERT INTO readings (
    timestamp, indoor_temp, outdoor_temp, outdoor_temp_source,
    target_temp, energy_wh, energy_delta_wh, ac_status, ac_mode, fan_mode, power_selection
) VALUES (?, ?, ?, 'device', ?, ?, ?, ?, ?, ?, ?)
"""

WEATHER_COLUMNS = [
    "energy_delta_wh REAL",
    "wind_speed_kmh REAL",
    "humidity_pct REAL",
    "solar_radiation_wm2 REAL",
    "precipitation_mm REAL",
    "pressure_hpa REAL",
    "cloud_cover_pct REAL",
]


class DataLogger:
    def __init__(self) -> None:
        self._enabled = False
        self._db: sqlite3.Connection | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if value:
            self._ensure_db()
            logger.info("Data logging enabled")
        else:
            logger.info("Data logging disabled")

    def _ensure_db(self) -> None:
        if self._db is not None:
            return
        DATA_DIR.mkdir(exist_ok=True)
        self._db = sqlite3.connect(str(DB_PATH))
        self._db.execute(CREATE_TABLE)
        self._migrate()
        self._db.commit()
        logger.info("Data logger initialized at %s", DB_PATH)

    def _migrate(self) -> None:
        """Add columns that may be missing from older databases."""
        columns = {
            row[1]
            for row in self._db.execute("PRAGMA table_info(readings)").fetchall()
        }
        for col_def in WEATHER_COLUMNS:
            col_name = col_def.split()[0]
            if col_name not in columns:
                self._db.execute(f"ALTER TABLE readings ADD COLUMN {col_def}")
                logger.info("Migrated: added %s column", col_name)

    def _calc_energy_delta(self, current_wh: float | None) -> float | None:
        """Calculate energy consumed since last reading.

        Returns None if:
        - current energy is unknown
        - no previous reading exists
        - time gap > 10 minutes (app was off — delta would span the gap)
        - energy counter reset (negative delta, e.g. new year)
        """
        if current_wh is None:
            return None
        row = self._db.execute(
            "SELECT energy_wh, timestamp FROM readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None or row[0] is None:
            return None
        prev_wh, prev_ts = row
        # Check time gap — skip if > 10 minutes (app was restarted)
        try:
            prev_time = datetime.fromisoformat(prev_ts)
            gap = (datetime.now(timezone.utc) - prev_time).total_seconds()
            if gap > 600:
                return None
        except (ValueError, TypeError):
            return None
        delta = current_wh - prev_wh
        # Negative delta means counter reset (e.g. new year) — skip
        return delta if delta >= 0 else None

    def record(self, state: Any) -> None:
        """Record a snapshot of the current device state."""
        if not self._enabled:
            return
        if not state.connected:
            return
        self._ensure_db()
        now = datetime.now(timezone.utc).isoformat()
        delta = self._calc_energy_delta(state.energy_wh)
        self._db.execute(INSERT_READING, (
            now,
            state.ac_indoor_temperature,
            state.ac_outdoor_temperature,
            state.ac_temperature,
            state.energy_wh,
            delta,
            state.ac_status.value,
            state.ac_mode.value,
            state.ac_fan_mode.value,
            state.ac_power_selection.value,
        ))
        self._db.commit()

    def get_readings(
        self, limit: int = 1000, offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return readings as list of dicts, newest first."""
        if self._db is None:
            self._ensure_db()
        cursor = self._db.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        """Return basic stats about the logged data."""
        if self._db is None:
            self._ensure_db()
        row = self._db.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM readings"
        ).fetchone()
        return {
            "total_readings": row[0],
            "first_reading": row[1],
            "last_reading": row[2],
        }

    def export_csv(self) -> str:
        """Export all readings as a CSV string."""
        self._ensure_db()
        cursor = self._db.execute("SELECT * FROM readings ORDER BY id ASC")
        columns = [desc[0] for desc in cursor.description]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(cursor.fetchall())
        return output.getvalue()

    def close(self) -> None:
        if self._db:
            self._db.close()
            self._db = None


data_logger = DataLogger()
