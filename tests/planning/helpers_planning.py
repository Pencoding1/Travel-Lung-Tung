"""Hand-authored synthetic fixtures for the OC-010 planning tests.

Every value here is synthetic. Nothing is the original thesis dataset and no
real place, price or route is described. These helpers only build plain dicts;
they never import the scheduler or validator.
"""

from __future__ import annotations

D1 = "2026-11-01"
D2 = "2026-11-02"


def iso(date: str, hm: str) -> str:
    return f"{date}T{hm}:00+07:00"


def cost(amount, unit: str = "per_party", currency: str = "VND") -> dict:
    return {"amount": str(amount), "currency": currency, "unit": unit}


def window(day_id: str, start: str, end: str) -> dict:
    return {"day_id": day_id, "start": start, "end": end}


def poi(poi_id: str, categories, visit_minutes: int = 60,
        cost_value=None, windows=None) -> dict:
    entry = {"poi_id": poi_id, "category_ids": list(categories),
             "visit_minutes": visit_minutes}
    if cost_value is not None:
        entry["cost"] = cost_value
    if windows is not None:
        entry["opening_windows"] = windows
    return entry


def make_day(day_id: str = "d1", date: str = D1, start: str = None,
             end: str = None, meal_windows=None, max_stops=None) -> dict:
    entry = {
        "day_id": day_id,
        "date": date,
        "window": {"start": start or iso(date, "08:00"),
                   "end": end or iso(date, "18:00")},
    }
    if meal_windows is not None:
        entry["meal_windows"] = meal_windows
    if max_stops is not None:
        entry["max_stops"] = max_stops
    return entry


def edge(from_id: str, to_id: str, duration_minutes: int = 10,
         distance_km: str = "1.0", mode: str = "car",
         provenance: str = "synthetic") -> dict:
    return {"from_poi_id": from_id, "to_poi_id": to_id,
            "duration_minutes": duration_minutes, "distance_km": distance_km,
            "transport_mode": mode, "provenance": provenance}


def make_scenario(pois, days, route_edges=(), **overrides) -> dict:
    base = {"scenario_id": "T", "seed": 1, "currency": "VND", "party_size": 2}
    base.update(overrides)
    base["pois"] = list(pois)
    base["days"] = list(days)
    base["route_edges"] = list(route_edges)
    return base
