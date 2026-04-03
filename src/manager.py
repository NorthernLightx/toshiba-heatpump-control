import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


def _patch_toshiba_ac_library() -> None:
    """Monkey-patch toshiba-ac library to:
    1. Handle unknown raw values gracefully (KeyError on unknown bytes)
    2. Add HADA swing mode (0x60) which newer Toshiba units support
    """
    try:
        from toshiba_ac.device.fcu_state import ToshibaAcFcuState
        from toshiba_ac.device import (
            ToshibaAcStatus,
            ToshibaAcMode,
            ToshibaAcFanMode,
            ToshibaAcSwingMode,
            ToshibaAcPowerSelection,
            ToshibaAcMeritA,
            ToshibaAcMeritB,
            ToshibaAcAirPureIon,
            ToshibaAcSelfCleaning,
        )

        # Add HADA member to the library's ToshibaAcSwingMode enum (if not already added)
        # Access via ToshibaAcSwingMode["HADA"] (bracket notation)
        if "HADA" not in ToshibaAcSwingMode._member_map_:
            hada = object.__new__(ToshibaAcSwingMode)
            hada._name_ = "HADA"
            hada._value_ = 100
            ToshibaAcSwingMode._member_names_.append("HADA")
            ToshibaAcSwingMode._member_map_["HADA"] = hada
            ToshibaAcSwingMode._value2member_map_[100] = hada

        # Patch AcSwingMode from_raw/to_raw to include HADA (0x60)
        orig_swing_from = ToshibaAcFcuState.AcSwingMode.from_raw
        orig_swing_to = ToshibaAcFcuState.AcSwingMode.to_raw

        @staticmethod
        def swing_from_raw(raw: int):
            if raw == 0x60:
                return ToshibaAcSwingMode.HADA
            try:
                return orig_swing_from(raw)
            except KeyError:
                logger.warning("Unknown swing raw value %s (0x%02x)", raw, raw)
                return ToshibaAcSwingMode.NONE

        @staticmethod
        def swing_to_raw(swing_mode):
            if swing_mode == ToshibaAcSwingMode.HADA:
                return 0x60
            return orig_swing_to(swing_mode)

        ToshibaAcFcuState.AcSwingMode.from_raw = swing_from_raw
        ToshibaAcFcuState.AcSwingMode.to_raw = swing_to_raw

        # Patch all other from_raw methods for unknown value safety
        other_classes = [
            (ToshibaAcFcuState.AcFanMode, ToshibaAcFanMode.NONE),
            (ToshibaAcFcuState.AcMode, ToshibaAcMode.NONE),
            (ToshibaAcFcuState.AcStatus, ToshibaAcStatus.NONE),
            (ToshibaAcFcuState.AcPowerSelection, ToshibaAcPowerSelection.NONE),
            (ToshibaAcFcuState.AcMeritA, ToshibaAcMeritA.NONE),
            (ToshibaAcFcuState.AcMeritB, ToshibaAcMeritB.NONE),
            (ToshibaAcFcuState.AcAirPureIon, ToshibaAcAirPureIon.NONE),
            (ToshibaAcFcuState.AcSelfCleaning, ToshibaAcSelfCleaning.NONE),
        ]

        for cls, fallback in other_classes:
            original = cls.from_raw

            def make_safe(orig, fb):
                def safe_from_raw(raw: int):
                    try:
                        return orig(raw)
                    except KeyError:
                        logger.warning(
                            "Unknown raw value %s (0x%02x) for %s, defaulting to %s",
                            raw, raw, orig.__qualname__, fb,
                        )
                        return fb
                return staticmethod(safe_from_raw)

            cls.from_raw = make_safe(original, fallback)

        # Re-wrap request_api with a longer timeout (30s instead of 5s)
        # and shorter backoff (5s instead of 60s) since the Toshiba API is slow
        from toshiba_ac.utils.http_api import ToshibaAcHttpApi
        from toshiba_ac.utils import retry_with_timeout, retry_on_exception
        from toshiba_ac.utils.http_api import ToshibaAcHttpApiError

        # Get the original unwrapped function (through the decorator chain)
        original_fn = ToshibaAcHttpApi.request_api
        while hasattr(original_fn, "__wrapped__"):
            original_fn = original_fn.__wrapped__

        # Re-decorate with better timeouts
        patched = retry_with_timeout(timeout=30, retries=3, backoff=5)(
            retry_on_exception(exceptions=ToshibaAcHttpApiError, retries=3, backoff=5)(
                original_fn
            )
        )
        ToshibaAcHttpApi.request_api = patched

        logger.info("Patched toshiba-ac library (HADA swing + unknown values + 30s timeout)")
    except ImportError:
        pass  # Library not installed, nothing to patch


_patch_toshiba_ac_library()


class AcStatus(str, Enum):
    ON = "ON"
    OFF = "OFF"


class AcMode(str, Enum):
    AUTO = "AUTO"
    COOL = "COOL"
    HEAT = "HEAT"
    DRY = "DRY"
    FAN = "FAN"


class AcFanMode(str, Enum):
    AUTO = "AUTO"
    QUIET = "QUIET"
    LOW = "LOW"
    MEDIUM_LOW = "MEDIUM_LOW"
    MEDIUM = "MEDIUM"
    MEDIUM_HIGH = "MEDIUM_HIGH"
    HIGH = "HIGH"


class AcSwingMode(str, Enum):
    OFF = "OFF"
    SWING_VERTICAL = "SWING_VERTICAL"
    SWING_HORIZONTAL = "SWING_HORIZONTAL"
    SWING_VERTICAL_AND_HORIZONTAL = "SWING_VERTICAL_AND_HORIZONTAL"
    FIXED_1 = "FIXED_1"
    FIXED_2 = "FIXED_2"
    FIXED_3 = "FIXED_3"
    FIXED_4 = "FIXED_4"
    FIXED_5 = "FIXED_5"
    HADA = "HADA"


class AcPowerSelection(str, Enum):
    POWER_50 = "POWER_50"
    POWER_75 = "POWER_75"
    POWER_100 = "POWER_100"


class AcMeritA(str, Enum):
    HIGH_POWER = "HIGH_POWER"
    CDU_SILENT_1 = "CDU_SILENT_1"
    ECO = "ECO"
    HEATING_8C = "HEATING_8C"
    SLEEP_CARE = "SLEEP_CARE"
    FLOOR = "FLOOR"
    COMFORT = "COMFORT"
    CDU_SILENT_2 = "CDU_SILENT_2"
    OFF = "OFF"


class AcMeritB(str, Enum):
    FIREPLACE_1 = "FIREPLACE_1"
    FIREPLACE_2 = "FIREPLACE_2"
    OFF = "OFF"


class AcAirPureIon(str, Enum):
    ON = "ON"
    OFF = "OFF"


class AcSelfCleaning(str, Enum):
    ON = "ON"
    OFF = "OFF"


@dataclass
class SupportedFeatures:
    """Which controls the device actually supports."""
    modes: list[str] = field(default_factory=lambda: [e.value for e in AcMode])
    fan_modes: list[str] = field(default_factory=lambda: [e.value for e in AcFanMode])
    swing_modes: list[str] = field(default_factory=lambda: [e.value for e in AcSwingMode])
    power_selections: list[str] = field(default_factory=lambda: [e.value for e in AcPowerSelection])
    merit_a: list[str] = field(default_factory=lambda: [e.value for e in AcMeritA])
    merit_b: list[str] = field(default_factory=lambda: [e.value for e in AcMeritB])
    air_pure_ion: list[str] = field(default_factory=lambda: [e.value for e in AcAirPureIon])


@dataclass
class DeviceState:
    name: str = ""
    device_id: str = ""
    ac_status: AcStatus = AcStatus.OFF
    ac_mode: AcMode = AcMode.AUTO
    ac_temperature: int | None = None
    ac_fan_mode: AcFanMode = AcFanMode.AUTO
    ac_swing_mode: AcSwingMode = AcSwingMode.OFF
    ac_power_selection: AcPowerSelection = AcPowerSelection.POWER_100
    ac_merit_a: AcMeritA = AcMeritA.OFF
    ac_merit_b: AcMeritB = AcMeritB.OFF
    ac_air_pure_ion: AcAirPureIon = AcAirPureIon.OFF
    ac_indoor_temperature: int | None = None
    ac_outdoor_temperature: int | None = None
    ac_self_cleaning: AcSelfCleaning = AcSelfCleaning.OFF
    energy_wh: float | None = None
    fcu: str = ""
    cdu: str = ""
    firmware_version: str = ""
    connected: bool = False
    supported: SupportedFeatures = field(default_factory=SupportedFeatures)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "device_id": self.device_id,
            "ac_status": self.ac_status.value,
            "ac_mode": self.ac_mode.value,
            "ac_temperature": self.ac_temperature,
            "ac_fan_mode": self.ac_fan_mode.value,
            "ac_swing_mode": self.ac_swing_mode.value,
            "ac_power_selection": self.ac_power_selection.value,
            "ac_merit_a": self.ac_merit_a.value,
            "ac_merit_b": self.ac_merit_b.value,
            "ac_air_pure_ion": self.ac_air_pure_ion.value,
            "ac_indoor_temperature": self.ac_indoor_temperature,
            "ac_outdoor_temperature": self.ac_outdoor_temperature,
            "ac_self_cleaning": self.ac_self_cleaning.value,
            "energy_wh": self.energy_wh,
            "fcu": self.fcu,
            "cdu": self.cdu,
            "firmware_version": self.firmware_version,
            "connected": self.connected,
        }



def _enum_from_lib(lib_enum: Any, our_enum_cls: type[Enum], default: Enum) -> Enum:
    """Convert a toshiba-ac library enum value to our enum."""
    if lib_enum is None:
        return default
    name = lib_enum.name
    try:
        return our_enum_cls[name]
    except KeyError:
        return default


def _safe_get(device: Any, attr: str, default: Any = None) -> Any:
    """Safely read a device property that may raise KeyError for unknown raw values."""
    try:
        return getattr(device, attr)
    except (KeyError, ValueError):
        logger.warning("Unknown value for %s, using default", attr)
        return default


class HeatpumpManager:
    def __init__(self) -> None:
        self._device_manager: Any = None
        self._device: Any = None
        self._command_lock = asyncio.Lock()
        self.state = DeviceState()
        self._on_state_changed: Callable[
            [DeviceState], Coroutine[Any, Any, None]
        ] | None = None

    @property
    def on_state_changed(
        self,
    ) -> Callable[[DeviceState], Coroutine[Any, Any, None]] | None:
        return self._on_state_changed

    @on_state_changed.setter
    def on_state_changed(
        self, callback: Callable[[DeviceState], Coroutine[Any, Any, None]]
    ) -> None:
        self._on_state_changed = callback

    async def connect(self, username: str, password: str) -> None:
        from toshiba_ac.device_manager import ToshibaAcDeviceManager

        self._device_manager = ToshibaAcDeviceManager(username, password)
        await self._device_manager.connect()

        devices = await self._device_manager.get_devices()
        if not devices:
            raise RuntimeError("No devices found on your Toshiba account")

        self._device = devices[0]
        self._device.on_state_changed_callback.add(self._handle_state_change)
        self._device.on_energy_consumption_changed_callback.add(
            self._handle_state_change
        )

        # Add HADA to the device's supported swing modes
        try:
            from toshiba_ac.device import ToshibaAcSwingMode as LibSwingMode
            hada_member = LibSwingMode._member_map_.get("HADA")
            if hada_member and hada_member not in self._device.supported.ac_swing_mode:
                self._device.supported._ac_swing_mode.append(hada_member)
                logger.info("Added HADA to supported swing modes")
        except Exception:
            logger.warning("Could not add HADA to supported swing modes")

        self._sync_state()
        self._sync_supported_features()
        self.state.connected = True
        logger.info("Connected to %s (%s)", self.state.name, self.state.device_id)

    def _sync_supported_features(self) -> None:
        """Read supported features from the device and store for UI filtering."""
        try:
            sup = self._device.supported
            # Filter NONE values — they're internal sentinels, not real options
            self.state.supported = SupportedFeatures(
                modes=[
                    e.name for e in sup.ac_mode
                    if e.name != "NONE" and e.name in AcMode.__members__
                ],
                fan_modes=[
                    e.name for e in sup.ac_fan_mode
                    if e.name != "NONE" and e.name in AcFanMode.__members__
                ],
                swing_modes=[
                    e.name for e in sup.ac_swing_mode
                    if e.name != "NONE" and e.name in AcSwingMode.__members__
                ],
                power_selections=[
                    e.name for e in sup.ac_power_selection
                    if e.name != "NONE" and e.name in AcPowerSelection.__members__
                ],
                merit_a=[
                    e.name for e in sup.ac_merit_a
                    if e.name != "NONE" and e.name in AcMeritA.__members__
                ],
                merit_b=[
                    e.name for e in sup.ac_merit_b
                    if e.name != "NONE" and e.name in AcMeritB.__members__
                ],
                air_pure_ion=[
                    e.name for e in sup.ac_air_pure_ion
                    if e.name != "NONE" and e.name in AcAirPureIon.__members__
                ],
            )
            logger.info("Supported features: %s", self.state.supported)
        except Exception:
            logger.exception("Could not read supported features, showing all")

    def _sync_state(self) -> None:
        d = self._device
        self.state.name = d.name or "Heat Pump"
        self.state.device_id = d.ac_unique_id or ""
        self.state.ac_status = _enum_from_lib(
            _safe_get(d, "ac_status"), AcStatus, AcStatus.OFF
        )
        self.state.ac_mode = _enum_from_lib(
            _safe_get(d, "ac_mode"), AcMode, AcMode.AUTO
        )
        self.state.ac_temperature = _safe_get(d, "ac_temperature")
        self.state.ac_fan_mode = _enum_from_lib(
            _safe_get(d, "ac_fan_mode"), AcFanMode, AcFanMode.AUTO
        )
        self.state.ac_swing_mode = _enum_from_lib(
            _safe_get(d, "ac_swing_mode"), AcSwingMode, AcSwingMode.OFF
        )
        self.state.ac_power_selection = _enum_from_lib(
            _safe_get(d, "ac_power_selection"), AcPowerSelection, AcPowerSelection.POWER_100
        )
        self.state.ac_merit_a = _enum_from_lib(
            _safe_get(d, "ac_merit_a"), AcMeritA, AcMeritA.OFF
        )
        self.state.ac_merit_b = _enum_from_lib(
            _safe_get(d, "ac_merit_b"), AcMeritB, AcMeritB.OFF
        )
        self.state.ac_air_pure_ion = _enum_from_lib(
            _safe_get(d, "ac_air_pure_ion"), AcAirPureIon, AcAirPureIon.OFF
        )
        self.state.ac_indoor_temperature = _safe_get(d, "ac_indoor_temperature")
        self.state.ac_outdoor_temperature = _safe_get(d, "ac_outdoor_temperature")
        self.state.ac_self_cleaning = _enum_from_lib(
            _safe_get(d, "ac_self_cleaning"), AcSelfCleaning, AcSelfCleaning.OFF
        )
        self.state.fcu = d.fcu or ""
        self.state.cdu = d.cdu or ""
        self.state.firmware_version = d.firmware_version or ""

        energy = _safe_get(d, "ac_energy_consumption")
        if energy is not None:
            self.state.energy_wh = energy.energy_wh
        else:
            self.state.energy_wh = None

    async def _handle_state_change(self, _device: Any = None) -> None:
        self._sync_state()
        if self._on_state_changed:
            await self._on_state_changed(self.state)

    def _get_lib_enum(self, category: str, value: str) -> Any:
        """Get the toshiba-ac library enum for a given value."""
        import toshiba_ac.device as tac_device

        enum_map = {
            "status": tac_device.ToshibaAcStatus,
            "mode": tac_device.ToshibaAcMode,
            "fan_mode": tac_device.ToshibaAcFanMode,
            "swing_mode": tac_device.ToshibaAcSwingMode,
            "power_selection": tac_device.ToshibaAcPowerSelection,
            "merit_a": tac_device.ToshibaAcMeritA,
            "merit_b": tac_device.ToshibaAcMeritB,
            "air_pure_ion": tac_device.ToshibaAcAirPureIon,
        }
        return enum_map[category][value]

    def _ensure_connected(self) -> None:
        if self._device is None:
            raise RuntimeError("Not connected to heat pump")

    async def set_power(self, value: str) -> None:
        status = AcStatus(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("status", value)
            await self._device.set_ac_status(lib_val)
            self.state.ac_status = status

    async def set_mode(self, value: str) -> None:
        mode = AcMode(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("mode", value)
            await self._device.set_ac_mode(lib_val)
            self.state.ac_mode = mode

    async def set_temperature(self, value: int) -> None:
        if not 5 <= value <= 30:
            raise ValueError("Temperature must be between 5 and 30")
        async with self._command_lock:
            self._ensure_connected()
            await self._device.set_ac_temperature(value)
            self.state.ac_temperature = value

    async def set_fan_mode(self, value: str) -> None:
        fan = AcFanMode(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("fan_mode", value)
            await self._device.set_ac_fan_mode(lib_val)
            self.state.ac_fan_mode = fan

    async def set_swing_mode(self, value: str) -> None:
        swing = AcSwingMode(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("swing_mode", value)
            await self._device.set_ac_swing_mode(lib_val)
            self.state.ac_swing_mode = swing

    async def set_power_selection(self, value: str) -> None:
        power = AcPowerSelection(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("power_selection", value)
            await self._device.set_ac_power_selection(lib_val)
            self.state.ac_power_selection = power

    async def set_merit_a(self, value: str) -> None:
        merit = AcMeritA(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("merit_a", value)
            await self._device.set_ac_merit_a(lib_val)
            self.state.ac_merit_a = merit

    async def set_merit_b(self, value: str) -> None:
        merit = AcMeritB(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("merit_b", value)
            await self._device.set_ac_merit_b(lib_val)
            self.state.ac_merit_b = merit

    async def set_air_pure_ion(self, value: str) -> None:
        ion = AcAirPureIon(value)
        async with self._command_lock:
            self._ensure_connected()
            lib_val = self._get_lib_enum("air_pure_ion", value)
            await self._device.set_ac_air_pure_ion(lib_val)
        self.state.ac_air_pure_ion = ion

    async def reconnect(self, username: str, password: str) -> None:
        """Disconnect (if needed) then connect again."""
        await self.disconnect()
        await self.connect(username, password)

    async def disconnect(self) -> None:
        self.state.connected = False
        if self._device_manager:
            try:
                await self._device_manager.shutdown()
            except Exception:
                logger.exception("Error during shutdown")
            self._device_manager = None
            self._device = None


manager = HeatpumpManager()
