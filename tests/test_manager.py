import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import types
from enum import Enum

from src.manager import (
    AcAirPureIon,
    AcFanMode,
    AcMeritA,
    AcMeritB,
    AcMode,
    AcPowerSelection,
    AcStatus,
    AcSwingMode,
    AcSelfCleaning,
    DeviceState,
    HeatpumpManager,
    _enum_from_lib,
)

pytestmark = pytest.mark.asyncio


# --- DeviceState tests ---


def test_device_state_defaults():
    state = DeviceState()
    assert state.ac_status == AcStatus.OFF
    assert state.ac_mode == AcMode.AUTO
    assert state.ac_temperature is None
    assert state.connected is False


def test_device_state_to_dict():
    state = DeviceState(
        name="Test",
        device_id="123",
        ac_status=AcStatus.ON,
        ac_mode=AcMode.HEAT,
        ac_temperature=22,
        ac_indoor_temperature=21,
        ac_outdoor_temperature=8,
        connected=True,
    )
    d = state.to_dict()
    assert d["name"] == "Test"
    assert d["ac_status"] == "ON"
    assert d["ac_mode"] == "HEAT"
    assert d["ac_temperature"] == 22
    assert d["connected"] is True


def test_device_state_to_dict_has_all_fields():
    state = DeviceState()
    d = state.to_dict()
    expected_keys = {
        "name", "device_id", "ac_status", "ac_mode", "ac_temperature",
        "ac_fan_mode", "ac_swing_mode", "ac_power_selection",
        "ac_merit_a", "ac_merit_b", "ac_air_pure_ion",
        "ac_indoor_temperature", "ac_outdoor_temperature",
        "ac_self_cleaning", "energy_wh", "fcu", "cdu",
        "firmware_version", "connected",
    }
    assert set(d.keys()) == expected_keys


# --- Enum conversion tests ---


def test_enum_from_lib_valid():
    MockEnum = Enum("MockEnum", {"HEAT": 1, "COOL": 2})
    result = _enum_from_lib(MockEnum.HEAT, AcMode, AcMode.AUTO)
    assert result == AcMode.HEAT


def test_enum_from_lib_none_returns_default():
    result = _enum_from_lib(None, AcMode, AcMode.AUTO)
    assert result == AcMode.AUTO


def test_enum_from_lib_unknown_returns_default():
    MockEnum = Enum("MockEnum", {"UNKNOWN_VALUE": 99})
    result = _enum_from_lib(MockEnum.UNKNOWN_VALUE, AcMode, AcMode.AUTO)
    assert result == AcMode.AUTO


# --- HeatpumpManager tests ---


def test_manager_initial_state():
    mgr = HeatpumpManager()
    assert mgr.state.connected is False
    assert mgr._device is None


async def test_manager_set_temperature_valid():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_temperature = AsyncMock()

    await mgr.set_temperature(22)
    mgr._device.set_ac_temperature.assert_called_once_with(22)


async def test_manager_set_temperature_too_low():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()

    with pytest.raises(ValueError, match="between 5 and 30"):
        await mgr.set_temperature(3)


async def test_manager_set_temperature_too_high():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()

    with pytest.raises(ValueError, match="between 5 and 30"):
        await mgr.set_temperature(35)


async def test_manager_set_temperature_boundary_low():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_temperature = AsyncMock()

    await mgr.set_temperature(5)
    mgr._device.set_ac_temperature.assert_called_once_with(5)


async def test_manager_set_temperature_boundary_high():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_temperature = AsyncMock()

    await mgr.set_temperature(30)
    mgr._device.set_ac_temperature.assert_called_once_with(30)


async def test_manager_set_power_valid():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_status = AsyncMock()

    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        await mgr.set_power("ON")
    mgr._device.set_ac_status.assert_called_once()


async def test_manager_set_power_invalid():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()

    with pytest.raises(ValueError):
        await mgr.set_power("INVALID")


async def test_manager_set_mode_valid():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_mode = AsyncMock()

    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        await mgr.set_mode("COOL")
    mgr._device.set_ac_mode.assert_called_once()


async def test_manager_set_fan_mode_valid():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_fan_mode = AsyncMock()

    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        await mgr.set_fan_mode("QUIET")
    mgr._device.set_ac_fan_mode.assert_called_once()


async def test_manager_set_swing_mode_valid():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_swing_mode = AsyncMock()

    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        await mgr.set_swing_mode("SWING_VERTICAL")
    mgr._device.set_ac_swing_mode.assert_called_once()


async def test_manager_set_merit_a_valid():
    mgr = HeatpumpManager()
    mgr._device = MagicMock()
    mgr._device.set_ac_merit_a = AsyncMock()

    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        await mgr.set_merit_a("ECO")
    mgr._device.set_ac_merit_a.assert_called_once()


async def test_manager_disconnect():
    mgr = HeatpumpManager()
    mgr._device_manager = MagicMock()
    mgr._device_manager.shutdown = AsyncMock()
    mgr._device = MagicMock()
    mgr.state.connected = True

    await mgr.disconnect()

    assert mgr.state.connected is False
    assert mgr._device is None
    assert mgr._device_manager is None


async def test_manager_disconnect_handles_error():
    mgr = HeatpumpManager()
    mgr._device_manager = MagicMock()
    mgr._device_manager.shutdown = AsyncMock(side_effect=RuntimeError("fail"))
    mgr._device = MagicMock()

    # Should not raise
    await mgr.disconnect()
    assert mgr._device is None


async def test_manager_state_changed_callback():
    mgr = HeatpumpManager()
    callback = AsyncMock()
    mgr.on_state_changed = callback
    mgr._device = MagicMock()
    mgr._device.name = "Test"
    mgr._device.ac_unique_id = "123"
    mgr._device.ac_status = None
    mgr._device.ac_mode = None
    mgr._device.ac_temperature = 20
    mgr._device.ac_fan_mode = None
    mgr._device.ac_swing_mode = None
    mgr._device.ac_power_selection = None
    mgr._device.ac_merit_a = None
    mgr._device.ac_merit_b = None
    mgr._device.ac_air_pure_ion = None
    mgr._device.ac_indoor_temperature = 19
    mgr._device.ac_outdoor_temperature = 5
    mgr._device.ac_self_cleaning = None
    mgr._device.ac_energy_consumption = None
    mgr._device.fcu = "FCU"
    mgr._device.cdu = "CDU"
    mgr._device.firmware_version = "1.0"

    await mgr._handle_state_change()

    callback.assert_called_once_with(mgr.state)
    assert mgr.state.name == "Test"
    assert mgr.state.ac_temperature == 20


# --- Helpers ---


def _mock_tac_device():
    """Create mock toshiba_ac package and device module, return dict for sys.modules patching."""
    pkg = types.ModuleType("toshiba_ac")
    mod = types.ModuleType("toshiba_ac.device")
    mod.ToshibaAcStatus = Enum("ToshibaAcStatus", {"ON": 0, "OFF": 1, "NONE": 2})
    mod.ToshibaAcMode = Enum(
        "ToshibaAcMode", {"AUTO": 0, "COOL": 1, "HEAT": 2, "DRY": 3, "FAN": 4, "NONE": 5}
    )
    mod.ToshibaAcFanMode = Enum(
        "ToshibaAcFanMode",
        {"AUTO": 0, "QUIET": 1, "LOW": 2, "MEDIUM_LOW": 3, "MEDIUM": 4, "MEDIUM_HIGH": 5, "HIGH": 6, "NONE": 7},
    )
    mod.ToshibaAcSwingMode = Enum(
        "ToshibaAcSwingMode",
        {
            "OFF": 0, "SWING_VERTICAL": 1, "SWING_HORIZONTAL": 2,
            "SWING_VERTICAL_AND_HORIZONTAL": 3,
            "FIXED_1": 4, "FIXED_2": 5, "FIXED_3": 6, "FIXED_4": 7, "FIXED_5": 8, "NONE": 9,
        },
    )
    mod.ToshibaAcPowerSelection = Enum(
        "ToshibaAcPowerSelection", {"POWER_50": 0, "POWER_75": 1, "POWER_100": 2, "NONE": 3}
    )
    mod.ToshibaAcMeritA = Enum(
        "ToshibaAcMeritA",
        {
            "HIGH_POWER": 0, "CDU_SILENT_1": 1, "ECO": 2, "HEATING_8C": 3,
            "SLEEP_CARE": 4, "FLOOR": 5, "COMFORT": 6, "CDU_SILENT_2": 7, "OFF": 8, "NONE": 9,
        },
    )
    mod.ToshibaAcMeritB = Enum(
        "ToshibaAcMeritB", {"FIREPLACE_1": 0, "FIREPLACE_2": 1, "OFF": 2, "NONE": 3}
    )
    mod.ToshibaAcAirPureIon = Enum(
        "ToshibaAcAirPureIon", {"ON": 0, "OFF": 1, "NONE": 2}
    )
    pkg.device = mod
    return {"toshiba_ac": pkg, "toshiba_ac.device": mod}
