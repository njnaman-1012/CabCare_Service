import pytest
from datetime import date

from cabcare import Driver, ServicePlan, Vehicle


def create_vehicle():
    driver = Driver("D001", "Test Driver", "9999999999")
    vehicle = Vehicle("V001", "MH12AB1234", "Maruti Dzire", driver)

    vehicle.set_service_plan(
        ServicePlan(
            interval_km=10000,
            interval_months=6
        )
    )

    return vehicle


# ---------------- ODOMETER TESTS ----------------

def test_odometer_accepts_valid_reading():
    vehicle = create_vehicle()

    vehicle.update_odometer(500)

    assert vehicle.odometer_km == 500


def test_odometer_rejects_string():
    vehicle = create_vehicle()

    with pytest.raises(TypeError):
        vehicle.update_odometer("45000")


def test_odometer_rejects_negative_value():
    vehicle = create_vehicle()

    with pytest.raises(ValueError):
        vehicle.update_odometer(-100)


def test_odometer_cannot_decrease():
    vehicle = create_vehicle()

    vehicle.update_odometer(500)

    with pytest.raises(ValueError):
        vehicle.update_odometer(400)


def test_odometer_rejects_unreasonable_jump():
    vehicle = create_vehicle()

    vehicle.update_odometer(500)

    # 500 -> 45000 is a 44,500 km jump.
    with pytest.raises(ValueError):
        vehicle.update_odometer(45000)


def test_odometer_rejects_typo_450000():
    vehicle = create_vehicle()

    vehicle.update_odometer(500)

    # Protects against an obvious extra-zero typo.
    with pytest.raises(ValueError):
        vehicle.update_odometer(450000)


# ---------------- KM SERVICE THRESHOLD ----------------

def test_service_due_when_km_threshold_reached():
    vehicle = create_vehicle()

    # Use smaller increments because the odometer
    # deliberately limits a single update.
    for km in range(1000, 10001, 1000):
        vehicle.update_odometer(km)

    assert vehicle.is_service_due() is True
    assert "kilometre" in vehicle.service_due_reason()


def test_service_not_due_before_km_threshold():
    vehicle = create_vehicle()

    for km in range(1000, 9001, 1000):
        vehicle.update_odometer(km)

    assert vehicle.is_service_due() is False


# ---------------- MONTH SERVICE THRESHOLD ----------------

def test_service_due_when_month_threshold_reached():
    vehicle = create_vehicle()

    # Simulate the last service being 6 months ago.
    vehicle.last_service_date = vehicle._add_months(date.today(), -6)

    assert vehicle.is_service_due() is True
    assert "month" in vehicle.service_due_reason()


def test_service_not_due_before_month_threshold():
    vehicle = create_vehicle()

    # Simulate the last service being 5 months ago.
    vehicle.last_service_date = vehicle._add_months(date.today(), -5)

    assert vehicle.is_service_due() is False


# ---------------- BOTH THRESHOLDS ----------------

def test_service_due_if_either_threshold_is_reached():
    vehicle = create_vehicle()

    # KM threshold is reached, but time threshold isn't.
    for km in range(1000, 10001, 1000):
        vehicle.update_odometer(km)

    vehicle.last_service_date = date.today()

    assert vehicle.is_service_due() is True


# ---------------- SERVICE RESET ----------------

def test_mark_serviced_resets_service_baseline():
    vehicle = create_vehicle()

    for km in range(1000, 10001, 1000):
        vehicle.update_odometer(km)

    assert vehicle.is_service_due() is True

    vehicle.mark_serviced()

    assert vehicle.last_service_km == 10000
    assert vehicle.last_service_date == date.today()
    assert vehicle.is_service_due() is False
