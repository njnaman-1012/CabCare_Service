"""Tests for cabcare.py. Run with:  python -m pytest -v"""
from datetime import date

import pytest

from cabcare import (DUE_SOON, OK, OVERDUE, Driver, Fleet, OdometerError,
                     RecordError, ServicePlan, Vehicle, add_months, parse_km)

START = date(2026, 1, 1)          # last service date
DUE = date(2026, 7, 1)            # 6 months later


def cab(odo=5_000, last_km=0, reading=START, plate="KA01TX9999"):
    return Vehicle(plate, "Test cab", odo, ServicePlan(10_000, 6, last_km, START), reading)


# AC1 - whichever threshold comes first

def test_ok_when_far_from_both_limits():
    assert cab(5_000).status(date(2026, 2, 1))[0] == OK


def test_km_limit_fires_first():
    level, reasons = cab(10_000).status(date(2026, 2, 1))
    assert level == OVERDUE and "km limit" in reasons[0]


def test_month_limit_fires_first():
    level, reasons = cab(1_000).status(DUE)
    assert level == OVERDUE and "time limit" in reasons[0]


def test_both_limits_reported():
    level, reasons = cab(10_000).status(DUE)
    assert level == OVERDUE and len(reasons) == 2


def test_km_limit_counts_from_last_service():
    c = cab(41_999, last_km=32_000)
    assert c.status(date(2026, 2, 1))[0] == DUE_SOON
    c.update_odometer(42_000, on=date(2026, 2, 1))
    assert c.status(date(2026, 2, 1))[0] == OVERDUE


def test_add_months_month_end():
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)


# AC2 - early warning

def test_due_soon_by_km():
    assert cab(9_600).status(date(2026, 2, 1))[0] == DUE_SOON


def test_due_soon_by_days():
    assert cab(1_000).status(date(2026, 6, 20))[0] == DUE_SOON


def test_overdue_beats_due_soon():
    assert cab(10_100).status(date(2026, 6, 20))[0] == OVERDUE


# AC3 - wrong odometer input

@pytest.mark.parametrize("raw, km", [(45_000, 45_000), ("45000", 45_000), (" 45,000 ", 45_000), (45_000.0, 45_000)])
def test_parse_valid(raw, km):
    assert parse_km(raw) == km


@pytest.mark.parametrize("raw", ["abc", "", "12.5", "-5", -1, 1.5, None, True, [1]])
def test_parse_invalid(raw):
    with pytest.raises(OdometerError):
        parse_km(raw)


def test_backwards_reading_rejected_and_nothing_saved():
    c = cab(5_000)
    with pytest.raises(OdometerError, match="backwards"):
        c.update_odometer(4_000, on=date(2026, 1, 5))
    assert c.odometer_km == 5_000


def test_typo_extra_zero_rejected():
    c = cab(44_000)
    with pytest.raises(OdometerError, match="typo"):
        c.update_odometer(440_000, on=date(2026, 1, 8))
    assert c.odometer_km == 44_000


def test_real_week_of_heavy_driving_is_accepted():
    # the AI version rejected this: 7 days x 320 km = 2,240 km
    c = cab(41_000)
    assert c.update_odometer(43_240, on=date(2026, 1, 8)) == 43_240


def test_force_skips_only_the_jump_check():
    c = cab(5_000)
    c.update_odometer(50_000, on=date(2026, 1, 2), force=True)
    with pytest.raises(OdometerError):
        c.update_odometer(100, on=date(2026, 1, 3), force=True)


def test_reading_date_cannot_go_back():
    c = cab(5_000, reading=date(2026, 1, 10))
    with pytest.raises(OdometerError):
        c.update_odometer(5_100, on=date(2026, 1, 5))


def test_last_service_above_odometer_rejected():
    with pytest.raises(OdometerError):
        cab(1_000, last_km=40_000)


@pytest.mark.parametrize("km, months", [(0, 6), (10_000, 0), (10_000, 1.5), ("10000", 6)])
def test_bad_intervals_rejected(km, months):
    with pytest.raises(ValueError):
        ServicePlan(km, months)


# AC4 - driver and vehicle records

def make_fleet():
    f = Fleet()
    f.add_driver(Driver("D01", "Test Driver One"))
    f.add_driver(Driver("D02", "Test Driver Two"))
    f.add_vehicle(cab(plate="KA01TX0001"))
    f.add_vehicle(cab(plate="KA01TX0002"))
    return f


def test_duplicate_plate_rejected_even_if_typed_differently():
    f = make_fleet()
    with pytest.raises(RecordError):
        f.add_vehicle(cab(plate="ka01 tx0001"))


def test_duplicate_driver_rejected():
    f = make_fleet()
    with pytest.raises(RecordError):
        f.add_driver(Driver("D01", "Someone Else"))


def test_unknown_driver_or_vehicle_gives_clear_error():
    f = make_fleet()
    with pytest.raises(RecordError):
        f.assign_driver("KA01TX0001", "D99")
    with pytest.raises(RecordError):
        f.update_odometer("NOPE", 1_000)


def test_driver_moves_to_new_cab():
    f = make_fleet()
    f.assign_driver("KA01TX0001", "D01")
    f.assign_driver("KA01TX0002", "D01")
    assert f.get_vehicle("KA01TX0001").driver is None
    assert f.get_vehicle("KA01TX0002").driver.name == "Test Driver One"


def test_alert_names_driver_and_overdue_listed_first():
    f = make_fleet()
    f.assign_driver("KA01TX0001", "D01")
    f.update_odometer("KA01TX0001", 10_500, on=date(2026, 1, 20))
    f.update_odometer("KA01TX0002", 9_700, on=date(2026, 1, 20))
    alerts = f.due_alerts(date(2026, 1, 20))
    assert [a.level for a in alerts] == [OVERDUE, DUE_SOON]
    assert "Test Driver One" in alerts[0].message()


# AC5 - service resets the plan

def test_service_resets_both_limits_and_keeps_history():
    c = cab(10_500)
    c.complete_service(DUE, "oil change")
    assert c.status(DUE)[0] == OK
    assert c.plan.next_due_km == 20_500
    assert c.plan.next_due_date == date(2027, 1, 1)
    assert len(c.plan.history) == 1
