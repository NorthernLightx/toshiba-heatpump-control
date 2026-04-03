import pytest
from unittest.mock import patch
from pathlib import Path

from src.datalog import DataLogger
from src.manager import (
    AcFanMode,
    AcMode,
    AcPowerSelection,
    AcStatus,
    DeviceState,
)


@pytest.fixture
def logger(tmp_path):
    """Create a DataLogger using a temporary database."""
    db_path = tmp_path / "test.db"
    data_dir = tmp_path
    with patch("src.datalog.DB_PATH", db_path), \
         patch("src.datalog.DATA_DIR", data_dir):
        dl = DataLogger()
        dl.enabled = True
        yield dl
        dl.close()


def _connected_state(**overrides) -> DeviceState:
    defaults = dict(
        name="Test",
        device_id="123",
        ac_status=AcStatus.ON,
        ac_mode=AcMode.HEAT,
        ac_temperature=22,
        ac_fan_mode=AcFanMode.AUTO,
        ac_power_selection=AcPowerSelection.POWER_100,
        ac_indoor_temperature=21,
        ac_outdoor_temperature=8,
        energy_wh=1500.0,
        connected=True,
    )
    defaults.update(overrides)
    return DeviceState(**defaults)


def test_record_inserts_row(logger):
    state = _connected_state()
    logger.record(state)
    readings = logger.get_readings()
    assert len(readings) == 1
    assert readings[0]["indoor_temp"] == 21
    assert readings[0]["outdoor_temp"] == 8
    assert readings[0]["target_temp"] == 22
    assert readings[0]["energy_wh"] == 1500.0
    assert readings[0]["ac_status"] == "ON"
    assert readings[0]["ac_mode"] == "HEAT"


def test_record_skips_when_disabled(logger):
    logger.enabled = False
    logger.record(_connected_state())
    logger.enabled = True
    assert logger.get_readings() == []


def test_record_skips_when_disconnected(logger):
    state = _connected_state(connected=False)
    logger.record(state)
    assert logger.get_readings() == []


def test_multiple_readings(logger):
    logger.record(_connected_state(ac_indoor_temperature=20))
    logger.record(_connected_state(ac_indoor_temperature=21))
    logger.record(_connected_state(ac_indoor_temperature=22))
    readings = logger.get_readings()
    assert len(readings) == 3
    # Newest first
    assert readings[0]["indoor_temp"] == 22
    assert readings[2]["indoor_temp"] == 20


def test_get_stats(logger):
    logger.record(_connected_state())
    logger.record(_connected_state())
    stats = logger.get_stats()
    assert stats["total_readings"] == 2
    assert stats["first_reading"] is not None
    assert stats["last_reading"] is not None


def test_get_stats_empty(logger):
    stats = logger.get_stats()
    assert stats["total_readings"] == 0


def test_readings_with_limit_and_offset(logger):
    for i in range(10):
        logger.record(_connected_state(ac_indoor_temperature=i))
    readings = logger.get_readings(limit=3, offset=2)
    assert len(readings) == 3
    # Newest first, skip 2
    assert readings[0]["indoor_temp"] == 7


def test_export_csv(logger):
    logger.record(_connected_state(ac_indoor_temperature=20))
    logger.record(_connected_state(ac_indoor_temperature=21))
    csv_data = logger.export_csv()
    lines = csv_data.strip().split("\n")
    assert len(lines) == 3  # header + 2 rows
    header = lines[0]
    assert "timestamp" in header
    assert "indoor_temp" in header
    assert "outdoor_temp" in header
    assert "20.0" in lines[1]
    assert "21.0" in lines[2]


def test_export_csv_empty(logger):
    csv_data = logger.export_csv()
    lines = csv_data.strip().split("\n")
    assert len(lines) == 1  # header only


def test_energy_delta_first_reading_is_none(logger):
    logger.record(_connected_state(energy_wh=1000.0))
    readings = logger.get_readings()
    assert readings[0]["energy_delta_wh"] is None


def test_energy_delta_calculated(logger):
    logger.record(_connected_state(energy_wh=1000.0))
    logger.record(_connected_state(energy_wh=1050.0))
    logger.record(_connected_state(energy_wh=1120.0))
    readings = logger.get_readings()  # newest first
    assert readings[0]["energy_delta_wh"] == 70.0
    assert readings[1]["energy_delta_wh"] == 50.0
    assert readings[2]["energy_delta_wh"] is None  # first reading


def test_energy_delta_counter_reset(logger):
    logger.record(_connected_state(energy_wh=50000.0))
    logger.record(_connected_state(energy_wh=100.0))  # new year reset
    readings = logger.get_readings()
    assert readings[0]["energy_delta_wh"] is None  # negative = skip


def test_energy_delta_skips_after_long_gap(logger):
    """If app was off and restarted, delta should be None (gap > 10 min)."""
    logger.record(_connected_state(energy_wh=1000.0))
    # Backdate the first reading to simulate a long gap
    logger._db.execute(
        "UPDATE readings SET timestamp = '2020-01-01T00:00:00+00:00' WHERE id = 1"
    )
    logger._db.commit()
    logger.record(_connected_state(energy_wh=2000.0))
    readings = logger.get_readings()  # newest first
    assert readings[0]["energy_delta_wh"] is None  # gap too large


def test_energy_delta_none_energy(logger):
    logger.record(_connected_state(energy_wh=1000.0))
    logger.record(_connected_state(energy_wh=None))
    readings = logger.get_readings()
    assert readings[0]["energy_delta_wh"] is None


def test_record_handles_none_values(logger):
    state = _connected_state(
        ac_indoor_temperature=None,
        ac_outdoor_temperature=None,
        energy_wh=None,
    )
    logger.record(state)
    readings = logger.get_readings()
    assert len(readings) == 1
    assert readings[0]["indoor_temp"] is None
    assert readings[0]["outdoor_temp"] is None
    assert readings[0]["energy_wh"] is None
