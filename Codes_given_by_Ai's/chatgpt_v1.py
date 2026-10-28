from datetime import date
from calendar import monthrange


class Driver:
    def __init__(self, driver_id, name, phone):
        self.driver_id = driver_id
        self.name = name
        self.phone = phone

    def __str__(self):
        return f"{self.name} ({self.phone})"


class ServicePlan:
    def __init__(self, interval_km, interval_months):
        self.interval_km = interval_km
        self.interval_months = interval_months


class Vehicle:
    def __init__(self, vehicle_id, registration_no, model, driver=None):
        self.vehicle_id = vehicle_id
        self.registration_no = registration_no
        self.model = model
        self.driver = driver

        self.odometer_km = 0
        self.last_service_km = 0
        self.last_service_date = date.today()

        self.service_plan = None

    def set_service_plan(self, plan):
        self.service_plan = plan

    def update_odometer(self, new_km):
        if new_km < self.odometer_km:
            raise ValueError("Odometer reading cannot decrease.")

        self.odometer_km = new_km

    def _add_months(self, start_date, months):
        month = start_date.month - 1 + months
        year = start_date.year + month // 12
        month = month % 12 + 1

        day = min(start_date.day, monthrange(year, month)[1])

        return date(year, month, day)

    def is_service_due(self):
        if self.service_plan is None:
            return False

        km_due = (
            self.odometer_km
            >= self.last_service_km + self.service_plan.interval_km
        )

        date_due = (
            date.today()
            >= self._add_months(
                self.last_service_date,
                self.service_plan.interval_months
            )
        )

        return km_due or date_due

    def service_due_reason(self):
        if self.service_plan is None:
            return "No service plan assigned."

        km_due = (
            self.odometer_km
            >= self.last_service_km + self.service_plan.interval_km
        )

        date_due = (
            date.today()
            >= self._add_months(
                self.last_service_date,
                self.service_plan.interval_months
            )
        )

        if km_due and date_due:
            return "Service due: both km and time thresholds reached."
        elif km_due:
            return "Service due: kilometre threshold reached."
        elif date_due:
            return "Service due: month threshold reached."

        return "Service not due."

    def mark_serviced(self):
        self.last_service_km = self.odometer_km
        self.last_service_date = date.today()

    def __str__(self):
        driver = self.driver.name if self.driver else "No driver"
        return (
            f"{self.registration_no} - {self.model} | "
            f"Odometer: {self.odometer_km} km | Driver: {driver}"
        )


class CabCare:
    def __init__(self):
        self.drivers = []
        self.vehicles = []

    def add_driver(self, driver):
        self.drivers.append(driver)

    def add_vehicle(self, vehicle):
        self.vehicles.append(vehicle)

    def check_service_alerts(self):
        print("\n--- Service Alerts ---")

        for vehicle in self.vehicles:
            if vehicle.is_service_due():
                print(
                    f"ALERT: {vehicle.registration_no} - "
                    f"{vehicle.service_due_reason()}"
                )
            else:
                print(
                    f"OK: {vehicle.registration_no} - "
                    f"{vehicle.service_due_reason()}"
                )


# ---------------- DEMO ----------------

if __name__ == "__main__":

    # Create CabCare system
    cabcare = CabCare()

    # Create drivers
    driver1 = Driver("D001", "Rahul Sharma", "9876543210")
    driver2 = Driver("D002", "Amit Verma", "9876501234")

    cabcare.add_driver(driver1)
    cabcare.add_driver(driver2)

    # Create vehicles
    car1 = Vehicle("V001", "MH12AB1234", "Maruti Dzire", driver1)
    car2 = Vehicle("V002", "MH12CD5678", "Hyundai Aura", driver2)

    # Add vehicles
    cabcare.add_vehicle(car1)
    cabcare.add_vehicle(car2)

    # Set service plans
    car1.set_service_plan(ServicePlan(10000, 6))
    car2.set_service_plan(ServicePlan(15000, 12))

    # Update odometers
    car1.update_odometer(9500)
    car2.update_odometer(16000)

    # Display vehicle information
    print(car1)
    print(car2)

    # Check service alerts
    cabcare.check_service_alerts()

    # Service car 2
    print("\nServicing", car2.registration_no)
    car2.mark_serviced()

    # Check again
    cabcare.check_service_alerts()