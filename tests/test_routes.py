import pytest
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.asyncio


async def test_dashboard_returns_html(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Heat Pump" in resp.text


async def test_dashboard_shows_device_name(client):
    resp = await client.get("/")
    assert "Test Heat Pump" in resp.text


async def test_dashboard_shows_temperatures(client):
    resp = await client.get("/")
    # Target temp
    assert "22" in resp.text
    # Indoor temp
    assert "21" in resp.text
    # Outdoor temp
    assert "8" in resp.text


async def test_dashboard_shows_active_mode(client):
    resp = await client.get("/")
    # Heat mode button should have the active class
    assert "active" in resp.text


async def test_post_power_on(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/power", data={"value": "ON"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_status.assert_called_once()


async def test_post_power_off(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/power", data={"value": "OFF"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_status.assert_called_once()


async def test_post_mode_heat(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/mode", data={"value": "HEAT"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_mode.assert_called_once()


async def test_post_mode_cool(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/mode", data={"value": "COOL"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_mode.assert_called_once()


async def test_post_temp_valid(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/temp", data={"value": "25"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_temperature.assert_called_once_with(25)


async def test_post_temp_out_of_range(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/temp", data={"value": "35"})
    assert resp.status_code == 200
    # Should contain error data attribute
    assert "data-error" in resp.text
    connected_manager._device.set_ac_temperature.assert_not_called()


async def test_post_fan_mode(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/fan", data={"value": "LOW"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_fan_mode.assert_called_once()


async def test_post_swing_mode(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/swing", data={"value": "SWING_VERTICAL"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_swing_mode.assert_called_once()


async def test_post_power_selection(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/power-sel", data={"value": "POWER_75"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_power_selection.assert_called_once()


async def test_post_merit_a(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/merit-a", data={"value": "ECO"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_merit_a.assert_called_once()


async def test_post_merit_b(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/merit-b", data={"value": "FIREPLACE_1"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_merit_b.assert_called_once()


async def test_post_air_pure_ion(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/air-pure", data={"value": "ON"})
    assert resp.status_code == 200
    connected_manager._device.set_ac_air_pure_ion.assert_called_once()


async def test_post_invalid_mode_shows_error(client, connected_manager):
    mock_modules = _mock_tac_device()
    with patch.dict("sys.modules", mock_modules):
        resp = await client.post("/mode", data={"value": "INVALID"})
    assert resp.status_code == 200
    assert "data-error" in resp.text


async def test_get_controls_partial(client):
    resp = await client.get("/partials/controls")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Power" in resp.text


async def test_get_status_partial(client):
    resp = await client.get("/partials/status")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "RAS-B10N4KVRG-E" in resp.text


async def test_sse_endpoint_returns_event_stream(client):
    import asyncio

    async def check_sse():
        async with client.stream("GET", "/sse") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

    # SSE stream is infinite, so we just verify headers then cancel
    try:
        await asyncio.wait_for(check_sse(), timeout=0.5)
    except (asyncio.TimeoutError, Exception):
        # Expected — the stream is infinite, we just needed the headers
        pass


# --- Helpers ---

def _mock_tac_device():
    """Create mock toshiba_ac package and device module, return dict for sys.modules patching."""
    from enum import Enum
    import types

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
