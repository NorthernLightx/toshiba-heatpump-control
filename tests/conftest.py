import asyncio
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.manager import (
    AcAirPureIon,
    AcFanMode,
    AcMeritA,
    AcMeritB,
    AcMode,
    AcPowerSelection,
    AcSelfCleaning,
    AcStatus,
    AcSwingMode,
    DeviceState,
    HeatpumpManager,
    manager,
)
from src.routes import app


def _make_lib_enum(name: str, members: dict[str, int]):
    """Create a mock enum mimicking toshiba-ac library enums."""
    return Enum(name, {k: v for k, v in members.items()})


# Mock toshiba-ac library enums
MockToshibaAcStatus = _make_lib_enum("ToshibaAcStatus", {"ON": 0, "OFF": 1, "NONE": 2})
MockToshibaAcMode = _make_lib_enum(
    "ToshibaAcMode", {"AUTO": 0, "COOL": 1, "HEAT": 2, "DRY": 3, "FAN": 4, "NONE": 5}
)
MockToshibaAcFanMode = _make_lib_enum(
    "ToshibaAcFanMode",
    {
        "AUTO": 0, "QUIET": 1, "LOW": 2, "MEDIUM_LOW": 3,
        "MEDIUM": 4, "MEDIUM_HIGH": 5, "HIGH": 6, "NONE": 7,
    },
)
MockToshibaAcSwingMode = _make_lib_enum(
    "ToshibaAcSwingMode",
    {
        "OFF": 0, "SWING_VERTICAL": 1, "SWING_HORIZONTAL": 2,
        "SWING_VERTICAL_AND_HORIZONTAL": 3,
        "FIXED_1": 4, "FIXED_2": 5, "FIXED_3": 6, "FIXED_4": 7, "FIXED_5": 8,
        "NONE": 9,
    },
)
MockToshibaAcPowerSelection = _make_lib_enum(
    "ToshibaAcPowerSelection", {"POWER_50": 0, "POWER_75": 1, "POWER_100": 2, "NONE": 3}
)
MockToshibaAcMeritA = _make_lib_enum(
    "ToshibaAcMeritA",
    {
        "HIGH_POWER": 0, "CDU_SILENT_1": 1, "ECO": 2, "HEATING_8C": 3,
        "SLEEP_CARE": 4, "FLOOR": 5, "COMFORT": 6, "CDU_SILENT_2": 7,
        "OFF": 8, "NONE": 9,
    },
)
MockToshibaAcMeritB = _make_lib_enum(
    "ToshibaAcMeritB", {"FIREPLACE_1": 0, "FIREPLACE_2": 1, "OFF": 2, "NONE": 3}
)
MockToshibaAcAirPureIon = _make_lib_enum(
    "ToshibaAcAirPureIon", {"ON": 0, "OFF": 1, "NONE": 2}
)
MockToshibaAcSelfCleaning = _make_lib_enum(
    "ToshibaAcSelfCleaning", {"ON": 0, "OFF": 1, "NONE": 2}
)


@pytest.fixture
def mock_device():
    """Create a mock toshiba-ac device."""
    device = MagicMock()
    device.name = "Test Heat Pump"
    device.ac_unique_id = "test-device-123"
    device.ac_status = MockToshibaAcStatus.ON
    device.ac_mode = MockToshibaAcMode.HEAT
    device.ac_temperature = 22
    device.ac_fan_mode = MockToshibaAcFanMode.AUTO
    device.ac_swing_mode = MockToshibaAcSwingMode.OFF
    device.ac_power_selection = MockToshibaAcPowerSelection.POWER_100
    device.ac_merit_a = MockToshibaAcMeritA.OFF
    device.ac_merit_b = MockToshibaAcMeritB.OFF
    device.ac_air_pure_ion = MockToshibaAcAirPureIon.OFF
    device.ac_indoor_temperature = 21
    device.ac_outdoor_temperature = 8
    device.ac_self_cleaning = MockToshibaAcSelfCleaning.OFF
    device.ac_energy_consumption = None
    device.fcu = "RAS-B10N4KVRG-E"
    device.cdu = "RAS-10PAVPG-ND"
    device.firmware_version = "12.34"
    device.on_state_changed_callback = None
    device.on_energy_consumption_changed_callback = None

    # Async setters
    device.set_ac_status = AsyncMock()
    device.set_ac_mode = AsyncMock()
    device.set_ac_temperature = AsyncMock()
    device.set_ac_fan_mode = AsyncMock()
    device.set_ac_swing_mode = AsyncMock()
    device.set_ac_power_selection = AsyncMock()
    device.set_ac_merit_a = AsyncMock()
    device.set_ac_merit_b = AsyncMock()
    device.set_ac_air_pure_ion = AsyncMock()

    return device


@pytest.fixture
def connected_manager(mock_device):
    """Set up the global manager with a mock device in connected state."""
    manager._device = mock_device
    manager._device_manager = MagicMock()
    manager._device_manager.shutdown = AsyncMock()

    # Sync state from mock device
    manager.state = DeviceState(
        name="Test Heat Pump",
        device_id="test-device-123",
        ac_status=AcStatus.ON,
        ac_mode=AcMode.HEAT,
        ac_temperature=22,
        ac_fan_mode=AcFanMode.AUTO,
        ac_swing_mode=AcSwingMode.OFF,
        ac_power_selection=AcPowerSelection.POWER_100,
        ac_merit_a=AcMeritA.OFF,
        ac_merit_b=AcMeritB.OFF,
        ac_air_pure_ion=AcAirPureIon.OFF,
        ac_indoor_temperature=21,
        ac_outdoor_temperature=8,
        ac_self_cleaning=AcSelfCleaning.OFF,
        energy_wh=None,
        fcu="RAS-B10N4KVRG-E",
        cdu="RAS-10PAVPG-ND",
        firmware_version="12.34",
        connected=True,
    )

    yield manager

    # Reset
    manager._device = None
    manager._device_manager = None
    manager.state = DeviceState()


@pytest_asyncio.fixture
async def client(connected_manager):
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
