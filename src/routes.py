import asyncio
import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.datalog import data_logger
from src.manager import (
    AcAirPureIon,
    AcFanMode,
    AcMeritA,
    AcMeritB,
    AcMode,
    AcPowerSelection,
    AcStatus,
    AcSwingMode,
    DeviceState,
    manager,
)
from src.scheduler import Period, schedule_manager
from src.sse import broadcaster

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Toshiba Heat Pump Control")

# Template context helpers
ENUM_LABELS = {
    "ac_status": {
        AcStatus.ON: "ON",
        AcStatus.OFF: "OFF",
    },
    "ac_mode": {
        AcMode.AUTO: "Auto",
        AcMode.COOL: "Cool",
        AcMode.HEAT: "Heat",
        AcMode.DRY: "Dry",
        AcMode.FAN: "Fan",
    },
    "ac_fan_mode": {
        AcFanMode.AUTO: "Auto",
        AcFanMode.QUIET: "Quiet",
        AcFanMode.LOW: "Low",
        AcFanMode.MEDIUM_LOW: "M-Lo",
        AcFanMode.MEDIUM: "Med",
        AcFanMode.MEDIUM_HIGH: "M-Hi",
        AcFanMode.HIGH: "High",
    },
    "ac_swing_mode": {
        AcSwingMode.OFF: "Off",
        AcSwingMode.SWING_VERTICAL: "Vert",
        AcSwingMode.SWING_HORIZONTAL: "Horiz",
        AcSwingMode.SWING_VERTICAL_AND_HORIZONTAL: "Both",
        AcSwingMode.FIXED_1: "1",
        AcSwingMode.FIXED_2: "2",
        AcSwingMode.FIXED_3: "3",
        AcSwingMode.FIXED_4: "4",
        AcSwingMode.FIXED_5: "5",
        AcSwingMode.HADA: "HADA",
    },
    "ac_power_selection": {
        AcPowerSelection.POWER_50: "50%",
        AcPowerSelection.POWER_75: "75%",
        AcPowerSelection.POWER_100: "100%",
    },
    "ac_merit_a": {
        AcMeritA.HIGH_POWER: "Hi Pwr",
        AcMeritA.CDU_SILENT_1: "Silent 1",
        AcMeritA.ECO: "Eco",
        AcMeritA.HEATING_8C: "Heat 8C",
        AcMeritA.SLEEP_CARE: "Sleep",
        AcMeritA.FLOOR: "Floor",
        AcMeritA.COMFORT: "Comfort",
        AcMeritA.CDU_SILENT_2: "Silent 2",
        AcMeritA.OFF: "Off",
    },
    "ac_merit_b": {
        AcMeritB.FIREPLACE_1: "Fire 1",
        AcMeritB.FIREPLACE_2: "Fire 2",
        AcMeritB.OFF: "Off",
    },
    "ac_air_pure_ion": {
        AcAirPureIon.ON: "ON",
        AcAirPureIon.OFF: "OFF",
    },
}


def _build_context(request: Request) -> dict:
    state = manager.state
    return {
        "request": request,
        "state": state,
        "labels": ENUM_LABELS,
        "AcStatus": AcStatus,
        "AcMode": AcMode,
        "AcFanMode": AcFanMode,
        "AcSwingMode": AcSwingMode,
        "AcPowerSelection": AcPowerSelection,
        "AcMeritA": AcMeritA,
        "AcMeritB": AcMeritB,
        "AcAirPureIon": AcAirPureIon,
        "programs": schedule_manager.programs,
        "data_logging": data_logger.enabled,
        "data_stats": data_logger.get_stats() if data_logger.enabled else None,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    ctx = _build_context(request)
    return templates.TemplateResponse("index.html", ctx)


@app.get("/sse")
async def sse_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        async for data in broadcaster.subscribe():
            if await request.is_disconnected():
                break
            yield data

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/reconnect", response_class=HTMLResponse)
async def reconnect(request: Request) -> HTMLResponse:
    """Attempt to reconnect to the Toshiba cloud."""
    try:
        await manager.reconnect(settings.toshiba_user, settings.toshiba_pass)
        logger.info("Reconnected successfully")
    except Exception:
        logger.exception("Reconnect failed")
    # Return the full page so connection status + controls all refresh
    ctx = _build_context(request)
    return templates.TemplateResponse("index.html", ctx)


@app.post("/logging/toggle", response_class=HTMLResponse)
async def toggle_logging(request: Request) -> HTMLResponse:
    data_logger.enabled = not data_logger.enabled
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/status.html", ctx)


@app.get("/api/readings", response_class=JSONResponse)
async def get_readings(
    limit: int = Query(default=1000, le=10000),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    return JSONResponse(data_logger.get_readings(limit=limit, offset=offset))


@app.get("/api/readings/export.csv")
async def export_readings_csv() -> PlainTextResponse:
    """Download all readings as a CSV file."""
    csv_data = data_logger.export_csv()
    return PlainTextResponse(
        csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=readings.csv"},
    )


@app.get("/api/readings/stats", response_class=JSONResponse)
async def get_readings_stats() -> JSONResponse:
    return JSONResponse(data_logger.get_stats())


@app.get("/api/state", response_class=PlainTextResponse)
async def get_state() -> PlainTextResponse:
    """Return a compact state string for change detection polling."""
    s = manager.state
    return PlainTextResponse(
        f"{s.ac_status.value}|{s.ac_mode.value}|{s.ac_temperature}|"
        f"{s.ac_fan_mode.value}|{s.ac_swing_mode.value}|{s.ac_power_selection.value}|"
        f"{s.ac_merit_a.value}|{s.ac_merit_b.value}|{s.ac_air_pure_ion.value}|"
        f"{s.ac_indoor_temperature}|{s.ac_outdoor_temperature}|{s.connected}"
    )


@app.get("/partials/controls", response_class=HTMLResponse)
async def get_controls(request: Request) -> HTMLResponse:
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/controls.html", ctx)


@app.get("/partials/status", response_class=HTMLResponse)
async def get_status(request: Request) -> HTMLResponse:
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/status.html", ctx)


async def _handle_command(request: Request, coro) -> HTMLResponse:
    """Execute a command and return updated controls partial."""
    try:
        await coro
    except Exception as e:
        logger.exception("Command failed")
        ctx = _build_context(request)
        ctx["error"] = str(e)
        return templates.TemplateResponse("partials/controls.html", ctx)
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/controls.html", ctx)


@app.post("/power", response_class=HTMLResponse)
async def set_power(request: Request, value: Annotated[str, Form()]) -> HTMLResponse:
    return await _handle_command(request, manager.set_power(value))


@app.post("/mode", response_class=HTMLResponse)
async def set_mode(request: Request, value: Annotated[str, Form()]) -> HTMLResponse:
    return await _handle_command(request, manager.set_mode(value))


@app.post("/temp", response_class=HTMLResponse)
async def set_temp(request: Request, value: Annotated[int, Form()]) -> HTMLResponse:
    return await _handle_command(request, manager.set_temperature(value))


@app.post("/fan", response_class=HTMLResponse)
async def set_fan(request: Request, value: Annotated[str, Form()]) -> HTMLResponse:
    return await _handle_command(request, manager.set_fan_mode(value))


@app.post("/swing", response_class=HTMLResponse)
async def set_swing(request: Request, value: Annotated[str, Form()]) -> HTMLResponse:
    return await _handle_command(request, manager.set_swing_mode(value))


@app.post("/power-sel", response_class=HTMLResponse)
async def set_power_sel(
    request: Request, value: Annotated[str, Form()]
) -> HTMLResponse:
    return await _handle_command(request, manager.set_power_selection(value))


@app.post("/merit-a", response_class=HTMLResponse)
async def set_merit_a(request: Request, value: Annotated[str, Form()]) -> HTMLResponse:
    return await _handle_command(request, manager.set_merit_a(value))


@app.post("/merit-b", response_class=HTMLResponse)
async def set_merit_b(request: Request, value: Annotated[str, Form()]) -> HTMLResponse:
    return await _handle_command(request, manager.set_merit_b(value))


@app.post("/air-pure", response_class=HTMLResponse)
async def set_air_pure(
    request: Request, value: Annotated[str, Form()]
) -> HTMLResponse:
    return await _handle_command(request, manager.set_air_pure_ion(value))


@app.get("/partials/schedules", response_class=HTMLResponse)
async def get_schedules(request: Request) -> HTMLResponse:
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/schedules.html", ctx)


@app.post("/program/add", response_class=HTMLResponse)
async def add_program(
    request: Request,
    days: Annotated[str, Form()],
) -> HTMLResponse:
    day_list = [d.strip() for d in days.split(",") if d.strip()]
    if not day_list:
        day_list = ["daily"]
    error = None
    try:
        schedule_manager.add_program(day_list)
    except ValueError as e:
        error = str(e)
    ctx = _build_context(request)
    if error:
        ctx["schedule_error"] = error
    return templates.TemplateResponse("partials/schedules.html", ctx)


@app.post("/program/delete", response_class=HTMLResponse)
async def delete_program(
    request: Request, index: Annotated[int, Form()]
) -> HTMLResponse:
    schedule_manager.remove_program(index)
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/schedules.html", ctx)


@app.post("/program/toggle", response_class=HTMLResponse)
async def toggle_program(
    request: Request, index: Annotated[int, Form()]
) -> HTMLResponse:
    schedule_manager.toggle_program(index)
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/schedules.html", ctx)


@app.post("/period/add", response_class=HTMLResponse)
async def add_period(
    request: Request,
    program: Annotated[int, Form()],
    name: Annotated[str, Form()],
    time: Annotated[str, Form()],
    temperature: Annotated[int, Form()],
    mode: Annotated[str, Form()] = "HEAT",
) -> HTMLResponse:
    try:
        hour, minute = map(int, time.split(":"))
        schedule_manager.add_period(
            program, name.strip() or "Period", hour, minute, temperature, mode,
        )
    except Exception:
        logger.exception("Failed to add period")
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/schedules.html", ctx)


@app.post("/period/update", response_class=HTMLResponse)
async def update_period(
    request: Request,
    program: Annotated[int, Form()],
    id: Annotated[str, Form()],
    time: Annotated[str, Form()],
    name: Annotated[str, Form()],
    temperature: Annotated[int, Form()],
    mode: Annotated[str, Form()] = "HEAT",
) -> HTMLResponse:
    try:
        hour, minute = map(int, time.split(":"))
        schedule_manager.update_period(
            program, id,
            hour=hour, minute=minute,
            temperature=temperature, mode=mode,
            name=name.strip() or "Period",
        )
    except Exception:
        logger.exception("Failed to update period")
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/schedules.html", ctx)


@app.post("/period/delete", response_class=HTMLResponse)
async def delete_period(
    request: Request,
    program: Annotated[int, Form()],
    id: Annotated[str, Form()],
) -> HTMLResponse:
    schedule_manager.remove_period(program, id)
    ctx = _build_context(request)
    return templates.TemplateResponse("partials/schedules.html", ctx)


async def _execute_period(period: Period) -> None:
    """Execute a scheduled period by setting power, mode, and temperature."""
    if not manager.state.connected:
        logger.warning("Skipping period '%s': device not connected", period.name)
        return

    await manager.set_power(period.power)
    if period.power == "ON":
        await manager.set_mode(period.mode)
        await manager.set_temperature(period.temperature)

    # Push state update to UI via SSE
    await broadcaster.broadcast("state-update", manager.state.to_dict())


schedule_manager.set_execute_callback(_execute_period)


async def _on_state_changed(state: DeviceState) -> None:
    await broadcaster.broadcast("state-update", state.to_dict())


async def heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(30)
        await broadcaster.send_heartbeat()


async def datalog_loop() -> None:
    """Record device state every 5 minutes."""
    await asyncio.sleep(10)  # short delay for initial connection
    while True:
        try:
            data_logger.record(manager.state)
        except Exception:
            logger.exception("Data logging failed")
        await asyncio.sleep(300)


manager.on_state_changed = _on_state_changed
