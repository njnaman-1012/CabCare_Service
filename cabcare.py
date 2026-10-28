"""CabCare Fleet - vehicle service plan and service-due alert module.

Keeps driver and vehicle records, a service plan per vehicle (interval in km
AND in months), checks odometer input, and raises an alert when whichever of
the two limits is reached first. Everything is kept in memory.

All names, plates and numbers used in the demo are made up.
"""

from dataclasses import dataclass, field
from datetime import date
import calendar
import re

MAX_ODOMETER_KM = 1_500_000   # no taxi should read more than this
MAX_KM_PER_DAY = 800          # a cab cannot honestly do more than this in a day
DUE_SOON_KM = 500             # warn this many km before the km limit
DUE_SOON_DAYS = 15            # warn this many days before the date limit

OK, DUE_SOON, OVERDUE = "OK", "DUE SOON", "OVERDUE"


class OdometerError(ValueError):
    """Bad or unbelievable odometer reading."""


class RecordError(ValueError):
    """Problem with a driver or vehicle record."""


def parse_km(value) -> int:
    """Turn user input into a whole, non-negative km number or raise OdometerError."""
    if isinstance(value, bool):
        raise OdometerError(f"Odometer must be a number, got {value!r}")
    if isinstance(value, int):
        km = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise OdometerError(f"Odometer must be a whole number, got {value!r}")
        km = int(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not re.fullmatch(r"\d+", cleaned):
            raise OdometerError(f"Odometer is not a valid number: {value!r}")
        km = int(cleaned)
    else:
        raise OdometerError(f"Odometer must be a number, got {type(value).__name__}")
    if km < 0:
        raise OdometerError(f"Odometer cannot be negative, got {km}")
    if km > MAX_ODOMETER_KM:
        raise OdometerError(f"Odometer {km} km is above the maximum of {MAX_ODOMETER_KM} km")
    return km


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a whole number above 0, got {value!r}")
    return value


def add_months(d: date, months: int) -> date:
    """Move a date forward by whole months, clamping to the month end (31 Aug + 6 = 28 Feb)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def normalise_plate(plate: str) -> str:
    """'ka 01 ab 1234' and 'KA01AB1234' are the same cab."""
    cleaned = re.sub(r"[\s-]", "", str(plate)).upper()
    if not cleaned:
        raise RecordError("Plate number cannot be empty")
    return cleaned


@dataclass
class Driver:
    driver_id: str
    name: str
    phone: str = ""
    licence_no: str = ""


@dataclass
class ServicePlan:
    interval_km: int
    interval_months: int
    last_service_km: int = 0
    last_service_date: date = field(default_factory=date.today)
    history: list = field(default_factory=list)

    def __post_init__(self):
        _positive_int(self.interval_km, "interval_km")
        _positive_int(self.interval_months, "interval_months")
        self.last_service_km = parse_km(self.last_service_km)

    @property
    def next_due_km(self) -> int:
        return self.last_service_km + self.interval_km

    @property
    def next_due_date(self) -> date:
        return add_months(self.last_service_date, self.interval_months)

    def record_service(self, odometer_km: int, on: date, note: str = ""):
        self.history.append((on, odometer_km, note))
        self.last_service_km = odometer_km
        self.last_service_date = on


@dataclass
class ServiceAlert:
    plate: str
    driver: str
    level: str          # DUE SOON or OVERDUE
    reasons: list

    def message(self) -> str:
        return f"[{self.level}] {self.plate} (driver: {self.driver}) - " + "; ".join(self.reasons)


@dataclass
class Vehicle:
    plate: str
    model: str
    odometer_km: int
    plan: ServicePlan
    reading_date: date = field(default_factory=date.today)
    driver: Driver = None

    def __post_init__(self):
        self.plate = normalise_plate(self.plate)
        self.odometer_km = parse_km(self.odometer_km)
        if self.plan.last_service_km > self.odometer_km:
            raise OdometerError(
                f"{self.plate}: last service at {self.plan.last_service_km} km is higher "
                f"than the current odometer {self.odometer_km} km")

    def update_odometer(self, new_km, on: date = None, force: bool = False) -> int:
        """Check and save a new reading. Nothing is saved if a check fails.

        1. must be a valid whole number
        2. cannot go backwards (force does not skip this)
        3. the increase must fit in the days since the last reading
           (MAX_KM_PER_DAY per day). force=True skips only this check,
           for a reading a supervisor has confirmed.
        """
        on = on or date.today()
        km = parse_km(new_km)
        if on < self.reading_date:
            raise OdometerError(f"{self.plate}: reading date {on} is before the last reading {self.reading_date}")
        if km < self.odometer_km:
            raise OdometerError(f"{self.plate}: odometer cannot go backwards ({km} < {self.odometer_km})")
        days = max((on - self.reading_date).days, 1)
        allowed = days * MAX_KM_PER_DAY
        jump = km - self.odometer_km
        if jump > allowed and not force:
            raise OdometerError(
                f"{self.plate}: +{jump} km in {days} day(s) is more than the {allowed} km allowed. "
                f"Looks like a typo - check the reading or confirm it with force=True")
        self.odometer_km = km
        self.reading_date = on
        return km

    def status(self, today: date = None):
        """Return (level, reasons). Whichever limit is hit first decides."""
        today = today or date.today()
        km_left = self.plan.next_due_km - self.odometer_km
        days_left = (self.plan.next_due_date - today).days
        overdue, soon = [], []
        if km_left <= 0:
            overdue.append(f"km limit passed by {-km_left} km (due at {self.plan.next_due_km} km)")
        elif km_left <= DUE_SOON_KM:
            soon.append(f"{km_left} km left before {self.plan.next_due_km} km")
        if days_left <= 0:
            overdue.append(f"time limit passed by {-days_left} days (due on {self.plan.next_due_date})")
        elif days_left <= DUE_SOON_DAYS:
            soon.append(f"{days_left} days left before {self.plan.next_due_date}")
        if overdue:
            return OVERDUE, overdue
        if soon:
            return DUE_SOON, soon
        return OK, []

    def service_alert(self, today: date = None):
        level, reasons = self.status(today)
        if level == OK:
            return None
        who = self.driver.name if self.driver else "unassigned"
        return ServiceAlert(self.plate, who, level, reasons)

    def complete_service(self, on: date = None, note: str = ""):
        self.plan.record_service(self.odometer_km, on or date.today(), note)


class Fleet:
    def __init__(self):
        self.drivers = {}
        self.vehicles = {}

    def add_driver(self, driver: Driver):
        if not driver.driver_id or not driver.name.strip():
            raise RecordError("Driver needs an ID and a name")
        if driver.driver_id in self.drivers:
            raise RecordError(f"Driver ID {driver.driver_id} already exists")
        self.drivers[driver.driver_id] = driver

    def add_vehicle(self, vehicle: Vehicle):
        if vehicle.plate in self.vehicles:
            raise RecordError(f"Vehicle {vehicle.plate} is already registered")
        self.vehicles[vehicle.plate] = vehicle

    def get_vehicle(self, plate: str) -> Vehicle:
        key = normalise_plate(plate)
        if key not in self.vehicles:
            raise RecordError(f"Unknown vehicle: {plate}")
        return self.vehicles[key]

    def assign_driver(self, plate: str, driver_id: str):
        """One driver drives one cab at a time. Moving a driver frees the old cab."""
        if driver_id not in self.drivers:
            raise RecordError(f"Unknown driver: {driver_id}")
        vehicle = self.get_vehicle(plate)
        driver = self.drivers[driver_id]
        for other in self.vehicles.values():
            if other is not vehicle and other.driver is driver:
                other.driver = None
        vehicle.driver = driver

    def update_odometer(self, plate: str, new_km, on: date = None, force: bool = False) -> int:
        return self.get_vehicle(plate).update_odometer(new_km, on, force)

    def due_alerts(self, today: date = None):
        """Overdue cabs first, then due-soon ones."""
        alerts = [v.service_alert(today) for v in self.vehicles.values()]
        alerts = [a for a in alerts if a]
        return sorted(alerts, key=lambda a: (a.level != OVERDUE, a.plate))


def demo():
    today = date(2026, 10, 27)
    fleet = Fleet()
    fleet.add_driver(Driver("D01", "Ravi Kumar", "90000 00001", "KA-TEST-0001"))
    fleet.add_driver(Driver("D02", "Anita Rao", "90000 00002", "KA-TEST-0002"))
    fleet.add_driver(Driver("D03", "Sameer Khan", "90000 00003", "KA-TEST-0003"))

    # every cab: service every 10,000 km or 6 months, whichever comes first
    def plan(km, served):
        return ServicePlan(10_000, 6, last_service_km=km, last_service_date=served)

    fleet.add_vehicle(Vehicle("KA01TX1001", "Sedan A", 41_200, plan(32_000, date(2026, 6, 1)), date(2026, 10, 20)))
    fleet.add_vehicle(Vehicle("KA01TX1002", "Sedan B", 15_000, plan(10_000, date(2026, 3, 1)), date(2026, 10, 20)))
    fleet.add_vehicle(Vehicle("KA01TX1003", "Hatch C", 22_000, plan(20_000, date(2026, 9, 1)), date(2026, 10, 20)))
    fleet.add_vehicle(Vehicle("KA01TX1004", "Sedan D", 58_100, plan(48_500, date(2026, 8, 10)), date(2026, 10, 20)))
    fleet.assign_driver("KA01TX1001", "D01")
    fleet.assign_driver("KA01TX1002", "D02")
    fleet.assign_driver("KA01TX1004", "D03")

    print(f"Service check on {today}")
    for a in fleet.due_alerts(today) or ["No alerts"]:
        print("  " + (a.message() if isinstance(a, ServiceAlert) else a))

    print("\nWeekly odometer readings:")
    readings = [("KA01TX1001", "42,350"), ("ka01 tx1003", "220000"), ("KA01TX1002", "14,000"), ("KA01TX1004", "abc")]
    for plate, raw in readings:
        try:
            km = fleet.update_odometer(plate, raw, on=today)
            print(f"  {plate}: saved {km} km")
        except OdometerError as e:
            print(f"  {plate}: REJECTED - {e}")

    print("\nAfter readings:")
    for a in fleet.due_alerts(today):
        print("  " + a.message())

    print("\nKA01TX1002 serviced today; re-check:")
    fleet.get_vehicle("KA01TX1002").complete_service(today, "oil, filters, brakes")
    for a in fleet.due_alerts(today):
        print("  " + a.message())


if __name__ == "__main__":
    demo()
