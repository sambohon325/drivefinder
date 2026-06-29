import json
from functools import lru_cache
from typing import List, Optional

from . import config


@lru_cache(maxsize=1)
def load_inventory() -> List[dict]:
    with open(config.MOCK_DB_PATH, "r") as f:
        return json.load(f)


def get_by_id(record_id) -> Optional[dict]:
    try:
        record_id = int(record_id)
    except (TypeError, ValueError):
        return None
    for c in load_inventory():
        if c["id"] == record_id:
            return c
    return None


def find_by_make_model(make: str, model: str, color: Optional[str] = None) -> List[dict]:
    inventory = load_inventory()
    matches = [
        c for c in inventory
        if c["make"].lower() == make.lower() and c["model"].lower() == model.lower()
    ]
    if color and color.lower() not in ("none", "null", ""):
        color_matches = [c for c in matches if c["color"].lower() == color.lower()]
        if color_matches:
            return color_matches
    return matches


def best_match_for_lead(make: str, model: str, color: str) -> dict:
    """Same fallback cascade as the original CLI: exact match, then
    make+model only, then make only, then a generic placeholder."""
    inventory = load_inventory()

    exact = [
        c for c in inventory
        if c["make"].lower() == make.lower()
        and c["model"].lower() == model.lower()
        and c["color"].lower() == color.lower()
    ]
    if exact:
        return exact[0]

    by_model = [
        c for c in inventory
        if c["make"].lower() == make.lower() and c["model"].lower() == model.lower()
    ]
    if by_model:
        return by_model[0]

    by_make = [c for c in inventory if c["make"].lower() == make.lower()]
    if by_make:
        return by_make[0]

    return {
        "vin": "REGIONAL_LOCATOR_888",
        "dealer_id": "dealer_apex_101",
        "dealer_name": "Apex Auto Group",
        "dealer_rating": "4.8 (1,420 Reviews)",
        "year": 2026,
        "make": make,
        "model": model,
        "trim": "Premium Spec",
        "price": 45000,
        "mileage": 12,
        "condition": "New",
    }


def body_style_for_model(make: str, model: str) -> str:
    inventory = load_inventory()
    for c in inventory:
        if c["make"].lower() == make.lower() and c["model"].lower() == model.lower():
            return c.get("body_style", "Sedan").lower()
    return "sedan"
