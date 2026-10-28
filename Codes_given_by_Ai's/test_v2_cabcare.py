from datetime import date

import pytest

from v2_cabcare import (
    MAX_JUMP_KM,
    MAX_ODOMETER_KM,
    Driver,
    Fleet,
    OdometerError,
    ServicePlan,
    Vehicle,
    add_months,
    parse_km,
)

# Plan used throughout: due at 10,000 km or on 2026-07-01 (6 months after
# 2026-01-01), whichever comes first.
PLAN_START = date(2026, 1, 1)
DUE_DATE = date(2026, 7, 1)


def make_vehicle(odometer=5_000, driver=None):
    plan = ServicePlan(10_000, 6, last_service_km=0, last_service_date=PLAN_START)
    return Vehicle("KA01AB1234", "Toyota Etios", odometer, plan, driver)


# ---------- km threshold ----------

def test_no_alert_just_below_km_limit():
    v = make_vehicle(odometer=9_999)
    assert v.service_alert(today=date(2026, 2, 1)) is None


def test_alert_exactly_at_km_limit():
    v = make_vehicle(odometer=10_000)
    alert = v.service_alert(today=date(2026, 2, 1))
    assert alert is not None
    assert "km limit" in alert
    assert "time limit" not in alert


def test_alert_over_km_limit_reports_overshoot():
    v = make_vehicle(odometer=10_500)
    alert = v.service_alert(today=date(2026, 2, 1))
    assert "500 km over" in alert


def test_km_threshold_is_relative_to_last_service():
    plan = ServicePlan(10_000, 6, last_service_km=32_000,
                       last_service_date=PLAN_START)
    v = Vehicle("X", "Car", 41_999, plan)
    assert v.service_alert(today=date(2026, 2, 1)) is None
    v.update_odometer(42_000)
    assert "km limit" in v.service_alert(today=date(2026, 2, 1))


# ---------- months threshold ----------

def test_no_alert_day_before_due_date():
    v = make_vehicle(odometer=1_000)
    assert v.service_alert(today=date(2026, 6, 30)) is None


def test_alert_on_due_date():
    v = make_vehicle(odometer=1_000)
    alert = v.service_alert(today=DUE_DATE)
    assert alert is not None
    assert "time limit" in alert
    assert "km limit" not in alert


def test_alert_after_due_date_reports_days_over():
    v = make_vehicle(odometer=1_000)
    alert = v.service_alert(today=date(2026, 7, 11))
    assert "10 days over" in alert


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_either_threshold_alone_triggers_alert():
    # Months hit first
    assert make_vehicle(odometer=100).service_alert(today=DUE_DATE)
    # Km hit first
    assert make_vehicle(odometer=10_000).service_alert(today=date(2026, 1, 2))


def test_both_thresholds_reported_together():
    v = make_vehicle(odometer=10_000)
    alert = v.service_alert(today=DUE_DATE)
    assert "km limit" in alert and "time limit" in alert


def test_alert_includes_driver_name_or_unassigned():
    v = make_vehicle(odometer=10_000)
    assert "unassigned" in v.service_alert(today=date(2026, 2, 1))
    v.assign_driver(Driver("D1", "Ravi Kumar"))
    assert "Ravi Kumar" in v.service_alert(today=date(2026, 2, 1))


def test_complete_service_resets_both_thresholds():
    v = make_vehicle(odometer=10_500)
    assert v.service_alert(today=DUE_DATE)
    v.complete_service(on=DUE_DATE)
    assert v.plan.last_service_km == 10_500
    assert v.plan.last_service_date == DUE_DATE
    assert v.service_alert(today=DUE_DATE) is None


def test_plan_rejects_non_positive_intervals():
    with pytest.raises(ValueError):
        ServicePlan(0, 6)
    with pytest.raises(ValueError):
        ServicePlan(10_000, -1)


# ---------- odometer: parsing ----------

@pytest.mark.parametrize("raw, expected", [
    (45_000, 45_000),
    ("45000", 45_000),
    (" 45,000 ", 45_000),
    (45_000.0, 45_000),
    (0, 0),
])
def test_parse_km_accepts_valid_input(raw, expected):
    assert parse_km(raw) == expected


@pytest.mark.parametrize("raw", [
    "abc", "", "  ", "12.5", "-5", "4 5000",
    -1, 45_000.5, float("nan"), float("inf"),
    None, True, False, [45_000], {"km": 1},
])
def test_parse_km_rejects_invalid_input(raw):
    with pytest.raises(OdometerError):
        parse_km(raw)


def test_parse_km_rejects_above_absolute_maximum():
    assert parse_km(MAX_ODOMETER_KM) == MAX_ODOMETER_KM
    with pytest.raises(OdometerError):
        parse_km(MAX_ODOMETER_KM + 1)


def test_odometer_error_is_a_value_error():
    assert issubclass(OdometerError, ValueError)


# ---------- odometer: update_odometer ----------

def test_string_input_no_longer_crashes():
    v = make_vehicle(odometer=44_000)
    assert v.update_odometer("45000") == 45_000
    assert v.odometer_km == 45_000
    assert isinstance(v.odometer_km, int)


def test_formatted_string_input_is_accepted():
    v = make_vehicle(odometer=44_000)
    v.update_odometer("45,000")
    assert v.odometer_km == 45_000


def test_same_reading_is_allowed():
    v = make_vehicle(odometer=5_000)
    v.update_odometer(5_000)
    assert v.odometer_km == 5_000


def test_backwards_reading_rejected_and_state_unchanged():
    v = make_vehicle(odometer=5_000)
    with pytest.raises(OdometerError, match="backwards"):
        v.update_odometer(4_999)
    assert v.odometer_km == 5_000


def test_backwards_string_reading_rejected():
    v = make_vehicle(odometer=5_000)
    with pytest.raises(OdometerError, match="backwards"):
        v.update_odometer("100")
    assert v.odometer_km == 5_000


@pytest.mark.parametrize("bad", ["abc", None, True, -10, 5_000.5, "12.5"])
def test_invalid_input_rejected_and_state_unchanged(bad):
    v = make_vehicle(odometer=5_000)
    with pytest.raises(OdometerError):
        v.update_odometer(bad)
    assert v.odometer_km == 5_000


def test_typo_extra_zero_is_rejected():
    # 450000 typed instead of 45000
    v = make_vehicle(odometer=44_000)
    with pytest.raises(OdometerError, match="typo"):
        v.update_odometer(450_000)
    assert v.odometer_km == 44_000


def test_typo_as_string_is_also_rejected():
    v = make_vehicle(odometer=44_000)
    with pytest.raises(OdometerError):
        v.update_odometer("450000")
    assert v.odometer_km == 44_000


def test_jump_exactly_at_limit_is_accepted():
    v = make_vehicle(odometer=5_000)
    v.update_odometer(5_000 + MAX_JUMP_KM)
    assert v.odometer_km == 5_000 + MAX_JUMP_KM


def test_jump_one_over_limit_is_rejected():
    v = make_vehicle(odometer=5_000)
    with pytest.raises(OdometerError):
        v.update_odometer(5_000 + MAX_JUMP_KM + 1)
    assert v.odometer_km == 5_000


def test_force_overrides_jump_check():
    v = make_vehicle(odometer=5_000)
    v.update_odometer(50_000, force=True)
    assert v.odometer_km == 50_000


def test_force_does_not_override_backwards_check():
    v = make_vehicle(odometer=5_000)
    with pytest.raises(OdometerError):
        v.update_odometer(100, force=True)


def test_force_does_not_override_absolute_maximum():
    v = make_vehicle(odometer=5_000)
    with pytest.raises(OdometerError):
        v.update_odometer(MAX_ODOMETER_KM + 1, force=True)


def test_vehicle_constructor_validates_starting_odometer():
    plan = ServicePlan(10_000, 6, last_service_date=PLAN_START)
    with pytest.raises(OdometerError):
        Vehicle("X", "Car", "not a number", plan)
    assert Vehicle("X", "Car", "12,000", plan).odometer_km == 12_000


# ---------- Fleet ----------

def test_fleet_update_odometer_accepts_string_and_forwards_force():
    fleet = Fleet()
    v = make_vehicle(odometer=5_000)
    fleet.add_vehicle(v)
    assert fleet.update_odometer(v.plate, "6000") == 6_000
    with pytest.raises(OdometerError):
        fleet.update_odometer(v.plate, 60_000)
    fleet.update_odometer(v.plate, 60_000, force=True)
    assert v.odometer_km == 60_000


def test_fleet_unknown_plate_raises_key_error():
    with pytest.raises(KeyError):
        Fleet().update_odometer("NOPE", 1_000)


def test_fleet_due_alerts_lists_only_due_vehicles():
    fleet = Fleet()
    due = make_vehicle(odometer=10_000)
    ok = Vehicle("OK1", "Car", 100,
                 ServicePlan(10_000, 6, last_service_km=0,
                             last_service_date=PLAN_START))
    fleet.add_vehicle(due)
    fleet.add_vehicle(ok)
    alerts = fleet.due_alerts(today=date(2026, 2, 1))
    assert len(alerts) == 1
    assert due.plate in alerts[0]
