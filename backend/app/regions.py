"""US states and Canadian provinces/territories, plus a lightweight free-text
detector. This is still a text-matching heuristic (not a real geocoding
lookup) — fine for a demo location field, not a real compliance mechanism.
"""

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

CA_PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador", "NS": "Nova Scotia",
    "NT": "Northwest Territories", "NU": "Nunavut", "ON": "Ontario",
    "PE": "Prince Edward Island", "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon",
}

# Real legal constraint, not a business rollout decision — kept separate from
# the admin-toggleable region table on purpose so it can never accidentally
# be switched back on from the admin UI.
LEGALLY_BLOCKED_STATES = {"CA"}


def detect_region(location_text: str):
    """Given free text like 'Fort Worth, TX' or 'Toronto, Ontario, Canada',
    returns (country, code, name) for the first US state or Canadian
    province/territory found, checking each comma-separated segment for an
    exact match against a code or full name. Returns None if nothing matches
    — callers should treat 'unknown' as 'allow', not 'block'.
    """
    parts = [p.strip().lower() for p in location_text.split(",") if p.strip()]
    for part in parts:
        for code, name in US_STATES.items():
            if part == code.lower() or part == name.lower():
                return ("US", code, name)
        for code, name in CA_PROVINCES.items():
            if part == code.lower() or part == name.lower():
                return ("CA", code, name)
    return None


def all_regions():
    """Returns a flat list of (country, code, name) for every region,
    used to seed the database on first boot."""
    regions = [("US", code, name) for code, name in US_STATES.items()]
    regions += [("CA", code, name) for code, name in CA_PROVINCES.items()]
    return regions


def seed_region_table(db):
    """Populates region_availability on first boot, defaulting every region
    to enabled (open for testing across all of the US and Canada). Run once
    — never overwrites existing rows, so toggles made from the admin UI
    survive restarts and redeploys.
    """
    from . import models  # local import to avoid a circular import at module load time

    if db.query(models.RegionAvailability).first():
        return  # already seeded

    for country, code, name in all_regions():
        db.add(models.RegionAvailability(country=country, code=code, name=name, is_enabled=True))
    db.commit()
