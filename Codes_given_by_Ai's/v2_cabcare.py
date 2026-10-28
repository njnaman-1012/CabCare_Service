"""CabCare fleet servicing module (v2: safer odometer input).

Tracks drivers, vehicles, per-vehicle service plans and odometer readings,
and raises a service-due alert when EITHER the km interval OR the month
interval is reached, whichever comes first. In-memory only, no database.
"""

from dataclasses import dataclass, field
from datetime import date
import calendar
import re

# Odometer safety limits.
MAX_ODOMETER_KM = 1_500_000      # no taxi should ever read more than this
MAX_JUMP_KM = 2_000              # largest increase accepted in one update


class OdometerError(ValueError):
    """Raised when an odometer reading is invalid or implausible."""


def parse_km(value) -> int:
    """Turn user input into a whole, non-negative number of km.

    Accepts ints, whole-number floats (45000.0) and digit strings
    ("45000", " 45,000 "). Rejects bools, None, fractions, negatives,
    text and anything above MAX_ODOMETER_KM.
    """
    if isinstance(value, bool):
        raise OdometerError(f"Odometer must be a number, got {value!r}")

    if isinstance(value, int):
        km = value
    elif isinstance(value, float):
        if not value.is_integer():   # also rejects nan and inf
            raise OdometerError(f"Odometer must be a whole number, got {value!r}")
        km = int(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not re.fullmatch(r"\d+", cleaned):
            raise OdometerError(f"Odometer is not a valid number: {value!r}")
        km = int(cleaned)
    else:
        raise OdometerError(
            f"Odometer must be a number, got {type(value).__name__}")

    if km < 0:
        raise OdometerError(f"Odometer cannot be negative, got {km}")
    if km > MAX_ODOMETER_KM:
        raise OdometerError(
            f"Odometer {km} km exceeds the maximum of {MAX_ODOMETER_KM} km")
    return km


def add_months(d: date, months: int) -> date:
    """Return d shifted forward by `months`, clamping the day to month end."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass
class Driver:
    driver_id: str
    name: str
    phone: str = ""
    license_no: str = ""


@dataclass
class ServicePlan:
    interval_km: int
    interval_months: int
    last_service_km: int = 0
    last_service_date: date = field(default_factory=date.today)

    def __post_init__(self):
        if self.interval_km <= 0 or self.interval_months <= 0:
            raise ValueError("Service intervals must be positive")
        self.last_service_km = parse_km(self.last_service_km)

    @property
    def next_due_km(self) -> int:
        return self.last_service_km + self.interval_km

    @property
    def next_due_date(self) -> date:
        return add_months(self.last_service_date, self.interval_months)

    def record_service(self, odometer_km: int, on: date = None):
        """Reset the plan after a service is done."""
        self.last_service_km = parse_km(odometer_km)
        self.last_service_date = on or date.today()


@dataclass
class Vehicle:
    plate: str
    model: str
    odometer_km: int
    plan: ServicePlan
    driver: Driver = None

    def __post_init__(self):
        self.odometer_km = parse_km(self.odometer_km)

    def assign_driver(self, driver: Driver):
        self.driver = driver

    def update_odometer(self, new_km, force: bool = False) -> int:
        """Validate and store a new odometer reading; return the stored value.

        Checks, in order:
          1. the input is a valid whole number (strings like "45000" are OK),
          2. the reading is not lower than the current one,
          3. the increase is at most MAX_JUMP_KM (catches typos such as
             450000 instead of 45000). Pass force=True to override this
             check after confirming the reading is genuine.
        The stored value is left unchanged if any check fails.
        """
        km = parse_km(new_km)

        if km < self.odometer_km:
            raise OdometerError(
                f"{self.plate}: odometer cannot go backwards "
                f"({km} < {self.odometer_km})")

        jump = km - self.odometer_km
        if jump > MAX_JUMP_KM and not force:
            raise OdometerError(
                f"{self.plate}: reading {km} is {jump} km above the current "
                f"{self.odometer_km} (limit {MAX_JUMP_KM} per update). "
                f"Check for a typo, or pass force=True if it is correct.")

        self.odometer_km = km
        return km

    def service_alert(self, today: date = None):
        """Return an alert message if service is due, else None.

        Fires when the km threshold OR the months threshold is hit,
        whichever comes first.
        """
        today = today or date.today()
        reasons = []
        if self.odometer_km >= self.plan.next_due_km:
            over = self.odometer_km - self.plan.next_due_km
            reasons.append(f"km limit reached ({over} km over)")
        if today >= self.plan.next_due_date:
            over = (today - self.plan.next_due_date).days
            reasons.append(f"time limit reached ({over} days over)")
        if not reasons:
            return None
        who = self.driver.name if self.driver else "unassigned"
        return (f"SERVICE DUE: {self.plate} ({self.model}), driver {who} - "
                + "; ".join(reasons))

    def complete_service(self, on: date = None):
        self.plan.record_service(self.odometer_km, on)


class Fleet:
    def __init__(self):
        self.drivers = {}
        self.vehicles = {}

    def add_driver(self, driver: Driver):
        self.drivers[driver.driver_id] = driver

    def add_vehicle(self, vehicle: Vehicle):
        self.vehicles[vehicle.plate] = vehicle

    def update_odometer(self, plate: str, new_km, force: bool = False) -> int:
        if plate not in self.vehicles:
            raise KeyError(f"Unknown vehicle: {plate}")
        return self.vehicles[plate].update_odometer(new_km, force=force)

    def due_alerts(self, today: date = None):
        alerts = (v.service_alert(today) for v in self.vehicles.values())
        return [a for a in alerts if a]


if __name__ == "__main__":
    fleet = Fleet()

    ravi = Driver("D1", "Ravi Kumar", "9800000001", "KA01-2020-1234")
    anita = Driver("D2", "Anita Rao", "9800000002", "KA05-2019-5678")
    fleet.add_driver(ravi)
    fleet.add_driver(anita)

    # Service every 10,000 km or 6 months, whichever comes first.
    car1 = Vehicle("KA01AB1234", "Toyota Etios", 41_000,
                   ServicePlan(10_000, 6, last_service_km=32_000,
                               last_service_date=date(2026, 6, 1)))
    car2 = Vehicle("KA05CD5678", "Maruti Dzire", 15_000,
                   ServicePlan(10_000, 6, last_service_km=10_000,
                               last_service_date=date(2026, 3, 1)))
    car3 = Vehicle("KA03EF9012", "Hyundai Aura", 22_000,
                   ServicePlan(10_000, 6, last_service_km=20_000,
                               last_service_date=date(2026, 9, 1)))
    car1.assign_driver(ravi)
    car2.assign_driver(anita)
    for c in (car1, car2, car3):
        fleet.add_vehicle(c)

    today = date(2026, 10, 27)

    print("Initial check (car2 is due by months; car1 not yet):")
    for a in fleet.due_alerts(today) or ["No alerts"]:
        print(" ", a)

    print("\nOdometer update: car1 -> '42,500' (string input is fine)")
    fleet.update_odometer("KA01AB1234", "42,500")
    for a in fleet.due_alerts(today):
        print(" ", a)

    print("\nBad odometer inputs:")
    for bad in ("abc", -5, 450_000, 40_000):
        try:
            fleet.update_odometer("KA01AB1234", bad)
        except OdometerError as e:
            print(f"  rejected {bad!r}: {e}")

    print("\nCar1 serviced; re-check:")
    car1.complete_service(today)
    for a in fleet.due_alerts(today):
        print(" ", a)
