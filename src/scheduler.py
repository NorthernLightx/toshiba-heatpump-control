import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

SCHEDULES_FILE = Path(__file__).parent.parent / "schedules.json"

DAYS_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}
DAYS_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DEFAULT_PERIODS = [
    {"name": "Night", "hour": 22, "minute": 0, "temperature": 18, "mode": "HEAT", "power": "ON"},
    {"name": "Wake", "hour": 6, "minute": 30, "temperature": 22, "mode": "HEAT", "power": "ON"},
    {"name": "Away", "hour": 8, "minute": 30, "temperature": 18, "mode": "HEAT", "power": "ON"},
    {"name": "Home", "hour": 17, "minute": 0, "temperature": 22, "mode": "HEAT", "power": "ON"},
]


@dataclass
class Period:
    id: str
    name: str
    hour: int
    minute: int
    temperature: int
    mode: str
    power: str  # "ON" or "OFF"

    @property
    def time_str(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    @property
    def time_minutes(self) -> int:
        return self.hour * 60 + self.minute

    @property
    def summary(self) -> str:
        if self.power == "OFF":
            return "Off"
        return f"{self.temperature}\u00b0C"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "hour": self.hour,
            "minute": self.minute,
            "temperature": self.temperature,
            "mode": self.mode,
            "power": self.power,
        }


@dataclass
class DayProgram:
    days: list[str]  # ["mon", "tue", ...] or ["daily"]
    periods: list[Period]
    enabled: bool = True

    @property
    def days_str(self) -> str:
        if "daily" in self.days:
            return "Every day"
        if set(self.days) == {"mon", "tue", "wed", "thu", "fri"}:
            return "Weekdays"
        if set(self.days) == {"sat", "sun"}:
            return "Weekends"
        return ", ".join(DAYS_LABELS[DAYS_MAP[d]] for d in self.days if d in DAYS_MAP)

    @property
    def sorted_periods(self) -> list[Period]:
        return sorted(self.periods, key=lambda p: p.time_minutes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": self.days,
            "periods": [p.to_dict() for p in self.periods],
            "enabled": self.enabled,
        }


class ScheduleManager:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._programs: list[DayProgram] = []
        self._execute_callback = None

    @property
    def programs(self) -> list[DayProgram]:
        return self._programs

    def set_execute_callback(self, callback) -> None:
        self._execute_callback = callback

    def start(self) -> None:
        self._load()
        self._scheduler.start()
        self._sync_jobs()
        logger.info(
            "Scheduler started with %d programs, %d total periods",
            len(self._programs),
            sum(len(p.periods) for p in self._programs),
        )

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    def _expand_days(self, days: list[str]) -> set[str]:
        """Expand day list to individual day set. 'daily' becomes all 7 days."""
        if "daily" in days:
            return set(DAYS_MAP.keys())
        return {d for d in days if d in DAYS_MAP}

    def get_conflicting_days(self, new_days: list[str]) -> set[str]:
        """Check if new_days overlap with any existing enabled program."""
        new_set = self._expand_days(new_days)
        conflicts = set()
        for prog in self._programs:
            if not prog.enabled:
                continue
            existing_set = self._expand_days(prog.days)
            conflicts |= new_set & existing_set
        return conflicts

    def add_program(self, days: list[str]) -> DayProgram | None:
        conflicts = self.get_conflicting_days(days)
        if conflicts:
            conflict_names = ", ".join(
                DAYS_LABELS[DAYS_MAP[d]] for d in sorted(conflicts, key=lambda d: DAYS_MAP[d])
            )
            raise ValueError(f"Schedule conflict: {conflict_names} already have a program")

        periods = [
            Period(
                id=uuid.uuid4().hex[:8],
                name=d["name"],
                hour=d["hour"],
                minute=d["minute"],
                temperature=d["temperature"],
                mode=d["mode"],
                power=d["power"],
            )
            for d in DEFAULT_PERIODS
        ]
        program = DayProgram(days=days, periods=periods, enabled=True)
        self._programs.append(program)
        self._sync_jobs()
        self._save()
        return program

    def remove_program(self, index: int) -> bool:
        if 0 <= index < len(self._programs):
            prog = self._programs.pop(index)
            self._remove_program_jobs(prog, index)
            self._save()
            return True
        return False

    def toggle_program(self, index: int) -> bool:
        if 0 <= index < len(self._programs):
            prog = self._programs[index]
            prog.enabled = not prog.enabled
            self._sync_jobs()
            self._save()
            return True
        return False

    def add_period(
        self, program_index: int, name: str, hour: int, minute: int,
        temperature: int, mode: str, power: str = "ON",
    ) -> Period | None:
        if not (0 <= program_index < len(self._programs)):
            return None
        period = Period(
            id=uuid.uuid4().hex[:8],
            name=name,
            hour=hour,
            minute=minute,
            temperature=max(5, min(30, temperature)),
            mode=mode,
            power=power,
        )
        self._programs[program_index].periods.append(period)
        self._sync_jobs()
        self._save()
        return period

    def remove_period(self, program_index: int, period_id: str) -> bool:
        if not (0 <= program_index < len(self._programs)):
            return False
        prog = self._programs[program_index]
        prog.periods = [p for p in prog.periods if p.id != period_id]
        self._sync_jobs()
        self._save()
        return True

    def update_period(
        self, program_index: int, period_id: str,
        hour: int | None = None, minute: int | None = None,
        temperature: int | None = None, mode: str | None = None,
        power: str | None = None, name: str | None = None,
    ) -> bool:
        if not (0 <= program_index < len(self._programs)):
            return False
        for period in self._programs[program_index].periods:
            if period.id == period_id:
                if hour is not None:
                    period.hour = hour
                if minute is not None:
                    period.minute = minute
                if temperature is not None:
                    period.temperature = max(5, min(30, temperature))
                if mode is not None:
                    period.mode = mode
                if power is not None:
                    period.power = power
                if name is not None:
                    period.name = name
                self._sync_jobs()
                self._save()
                return True
        return False

    def _sync_jobs(self) -> None:
        """Rebuild all scheduler jobs from current programs."""
        # Remove all existing jobs
        self._scheduler.remove_all_jobs()

        # Add jobs for enabled programs
        for prog_idx, prog in enumerate(self._programs):
            if not prog.enabled:
                continue
            if "daily" in prog.days:
                day_of_week = "mon-sun"
            else:
                day_of_week = ",".join(prog.days)

            for period in prog.periods:
                job_id = f"prog{prog_idx}_{period.id}"
                trigger = CronTrigger(
                    hour=period.hour,
                    minute=period.minute,
                    day_of_week=day_of_week,
                )
                self._scheduler.add_job(
                    self._run_period,
                    trigger=trigger,
                    id=job_id,
                    args=[period],
                    replace_existing=True,
                )

    def _remove_program_jobs(self, prog: DayProgram, index: int) -> None:
        for period in prog.periods:
            job_id = f"prog{index}_{period.id}"
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

    async def _run_period(self, period: Period) -> None:
        logger.info(
            "Schedule: activating '%s' — %s %s",
            period.name, period.mode, period.summary,
        )
        if self._execute_callback:
            try:
                await self._execute_callback(period)
            except Exception:
                logger.exception("Failed to execute period '%s'", period.name)

    def _save(self) -> None:
        data = [p.to_dict() for p in self._programs]
        SCHEDULES_FILE.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        if not SCHEDULES_FILE.exists():
            return
        try:
            data = json.loads(SCHEDULES_FILE.read_text())
            if not isinstance(data, list):
                return
            for item in data:
                periods = [
                    Period(
                        id=p.get("id", uuid.uuid4().hex[:8]),
                        name=p["name"],
                        hour=p["hour"],
                        minute=p["minute"],
                        temperature=p["temperature"],
                        mode=p.get("mode", "HEAT"),
                        power=p.get("power", "ON"),
                    )
                    for p in item.get("periods", [])
                ]
                prog = DayProgram(
                    days=item["days"],
                    periods=periods,
                    enabled=item.get("enabled", True),
                )
                self._programs.append(prog)
        except Exception:
            logger.exception("Failed to load schedules")


schedule_manager = ScheduleManager()
