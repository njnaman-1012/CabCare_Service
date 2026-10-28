# CabCare Fleet - Service Plan and Service-Due Alert Module

A small Python module for a taxi company that keeps driver and vehicle records,
stores a service plan for each cab (interval in km and in months), checks
odometer input, and raises an alert when whichever limit comes first is reached.

All data in the demo and tests is made up. No real drivers or vehicles.

## How to run

Needs Python 3.10 or newer.

```
pip install pytest
python cabcare.py          # runs the demo
python -m pytest -v        # runs the tests
```

## Main rules

* Service is due at `last service km + interval km` OR `last service date + interval months`, whichever comes first.
* A "DUE SOON" warning shows 500 km or 15 days before a limit.
* Odometer readings must be whole numbers, cannot go backwards, and cannot rise
by more than 800 km per day since the last reading (catches typos like an extra zero).
A supervisor can confirm a genuine big jump with `force=True`.
* Plates are stored in one format (`ka01 tx1001` = `KA01TX1001`), duplicate plates
and driver IDs are refused, and a driver can only be on one cab at a time.

