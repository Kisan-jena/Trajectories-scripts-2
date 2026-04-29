"""Expedia URL Match verifier for flight and hotel search navigation.

This module provides functionality to verify AI agent navigation on Expedia
by comparing the agent's final URL against expected ground truth URLs.

The verifier handles all Expedia URL variations including:
- Flight search paths: /Flights-Search?trip={oneway|roundtrip}&leg1=from:IATA,to:IATA,departure:M/D/YYYYTANYT...
- Hotel search paths: /Hotel-Search?destination=...&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
- Flight query params: trip, leg1, leg2, options (cabinclass), passengers (adults, children, childrenAge)
- Hotel query params: destination, startDate, endDate, adults, rooms, children, childrenAges, sort, regionId
- Domain variations: expedia.com, www.expedia.com
- Filter order independence, case-insensitive comparison

Browser-Verified Patterns (Apr 2026 on expedia.com):
  Flight path: /Flights-Search
  Flight params: trip=oneway|roundtrip, leg1=from:JFK,to:LAX,departure:4/16/2026TANYT,fromType:AIRPORT,toType:AIRPORT
  Flight options: options=cabinclass:economy|business|first|premium_economy
  Flight passengers: passengers=adults:1,infantinlap:N  (or adults:2,children:1,childrenAge:5)
  Flight dates also: fromDate=M/D/YYYY, d1=YYYY-M-D, toDate=M/D/YYYY, d2=YYYY-M-D
  Hotel path: /Hotel-Search
  Hotel params: destination=New%20York, startDate=2026-04-15, endDate=2026-04-20
  Hotel guests: adults=2, rooms=1, children=1, childrenAges=5
  Hotel sort: sort=RECOMMENDED|PRICE_LOW_TO_HIGH|PRICE_HIGH_TO_LOW|DISTANCE|REVIEW
  Hotel regionId: regionId=2621 (numeric area ID)
"""

import re
from typing import Any, TypedDict
from urllib.parse import parse_qs, unquote, urlparse

from beartype import beartype
from loguru import logger
from pydantic import BaseModel

from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import (
    initialize_placeholder_map,
    initialize_user_metadata,
    render_task_statement,
)


# =============================================================================
# TypedDicts
# =============================================================================


class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class ExpediaVerifierResult(BaseModel):
    """Detailed verification result for Expedia URL matching."""

    score: float
    match: bool
    page_type: str = ""
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid Expedia domain patterns
VALID_BASE_DOMAINS = {
    "expedia.com",
}

# Regional / sister-brand domains
REGIONAL_DOMAINS = {
    "expedia.co.uk",
    "expedia.de",
    "expedia.fr",
    "expedia.es",
    "expedia.it",
    "expedia.co.jp",
    "expedia.com.au",
    "expedia.ca",
    "expedia.co.in",
    "expedia.com.br",
    "expedia.com.mx",
    "expedia.co.kr",
    "expedia.com.sg",
    "expedia.com.hk",
    "expedia.com.tw",
    "expedia.co.nz",
    "expedia.se",
    "expedia.no",
    "expedia.dk",
    "expedia.fi",
    "expedia.ie",
    "expedia.at",
    "expedia.ch",
    "expedia.com.my",
    "expedia.com.ph",
}

# Query parameters to IGNORE during flight comparison
IGNORED_FLIGHT_PARAMS = {
    "flight-type",
    "mode",
    "fromType",
    "toType",
    "fromDate",
    "toDate",
    "d1",
    "d2",
    "infantinlap",
    "locale",
    "currency",
    "siteid",
    "rfrr",
    "tpid",
    "eapid",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "ref",
    "semcid",
    "semdtl",
    "gclid",
    "msclkid",
    "selectedOfferToken",
    "newFlightSearch",
    "previousDateful",
    "filters",
}

# Query parameters to IGNORE during hotel comparison
IGNORED_HOTEL_PARAMS = {
    "locale",
    "currency",
    "siteid",
    "rfrr",
    "tpid",
    "eapid",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "ref",
    "latLong",
    "theme",
    "userIntent",
    "selected",
    "searchId",
    "propertyId",
    "gclid",
    "msclkid",
    "semdtl",
    "semcid",
    "pwaDialogNested",
    "mapBounds",
    "neighborhood",
    "flexibility",
}

# Cabin class normalization mapping
CABIN_CLASS_MAP = {
    "economy": "economy",
    "coach": "economy",
    "premium_economy": "premium_economy",
    "premiumeconomy": "premium_economy",
    "premium economy": "premium_economy",
    "premium": "premium_economy",
    "business": "business",
    "first": "first",
}

# Hotel sort normalization mapping
HOTEL_SORT_MAP = {
    "recommended": "RECOMMENDED",
    "price_low_to_high": "PRICE_LOW_TO_HIGH",
    "price": "PRICE_LOW_TO_HIGH",
    "price_high_to_low": "PRICE_HIGH_TO_LOW",
    "distance": "DISTANCE",
    "distance_from_landmark": "DISTANCE_FROM_LANDMARK",
    "review": "REVIEW",
    "review_score": "REVIEW",
    "guest_rating": "GUEST_RATING",
    "star_rating_highest_first": "STAR_RATING_HIGHEST_FIRST",
    "star_rating": "STAR_RATING_HIGHEST_FIRST",
}


# =============================================================================
# PAGE TYPE DETECTION
# =============================================================================


def detect_page_type(url: str) -> str:
    """Detect the Expedia page type from a URL.

    Returns one of: 'flights', 'hotels', 'packages', 'cars', 'cruises', 'activities', 'other'.
    """
    parsed = urlparse(url.strip())
    path = parsed.path.lower()

    if "/flights-search" in path or "flights-search" in path:
        return "flights"
    if "/hotel-search" in path or "hotel-search" in path:
        return "hotels"
    if "/carsearch" in path or "/car-search" in path or path.rstrip("/") == "/cars":
        return "cars"
    if "/cruises" in path:
        return "cruises"
    if "/packages" in path:
        return "packages"
    if "/things-to-do" in path or "/activities" in path:
        return "activities"
    if "/flights" in path:
        return "flights"
    if "/hotels" in path:
        return "hotels"
    return "other"


# =============================================================================
# PARSING HELPERS
# =============================================================================


def _get_param(query: dict, *keys: str) -> str:
    """Get the first non-empty value from query dict for any of the keys.

    Handles both exact keys and case-insensitive fallback.
    Note: parse_qs() already URL-decodes values, so no unquote() is needed.
    """
    for key in keys:
        if key in query and query[key]:
            return query[key][0]
        key_lower = key.lower()
        if key_lower in query and query[key_lower]:
            return query[key_lower][0]
    return ""


def _normalize_date(date_str: str) -> str:
    """Normalize a date string to YYYY-MM-DD format.

    Handles multiple Expedia date formats:
      - M/D/YYYY  (e.g., 4/16/2026 — from leg params)
      - YYYY-M-D  (e.g., 2026-4-16 — from d1/d2 params)
      - YYYY-MM-DD (e.g., 2026-04-16 — from hotel params)
      - M/D/YYYYTANYT (e.g., 4/16/2026TANYT — departure in leg, strip TANYT suffix)
    """
    if not date_str:
        return ""

    # Strip TANYT suffix (time-any-time marker in leg departure)
    date_str = re.sub(r"TANYT$", "", date_str, flags=re.IGNORECASE)
    date_str = date_str.strip()

    # M/D/YYYY format
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    # YYYY-M-D or YYYY-MM-DD format
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", date_str)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    return date_str


def _extract_iata_code(location_str: str) -> str:
    """Extract IATA airport code from an Expedia location string.

    Handles multiple formats:
      - 'JFK'                  → 'jfk'
      - 'New York, NY (JFK)'   → 'jfk'
      - 'New York, NY, United States of America (JFK-John F. Kennedy Intl.)' → 'jfk'
      - 'Los Angeles, CA (LAX-Los Angeles Intl.)' → 'lax'

    Returns lowercase IATA code, or the original string lowercased if no code found.
    """
    if not location_str:
        return ""

    location_str = unquote(location_str).strip()

    # Pattern: look for (XXX or (XXX-... where XXX is 3-letter IATA
    iata_match = re.search(r"\(([A-Z]{3})(?:-[^)]+)?\)", location_str, re.IGNORECASE)
    if iata_match:
        return iata_match.group(1).lower()

    # If the string itself looks like a bare IATA code (2-4 uppercase letters)
    if re.match(r"^[A-Za-z]{2,4}$", location_str):
        return location_str.lower()

    # Fallback: return lowercased string for fuzzy matching
    return location_str.lower()


def _parse_leg_param(leg_str: str) -> dict[str, str]:
    """Parse an Expedia leg parameter into components.

    leg format: from:ORIGIN,to:DEST,departure:M/D/YYYYTANYT,fromType:AIRPORT,toType:AIRPORT

    Returns dict with keys: from, to, departure, fromType, toType
    """
    result = {}
    if not leg_str:
        return result

    # Split on commas, but need to handle commas inside city names
    # Strategy: find key:value pairs separated by comma-key:
    # Keys we expect: from, to, departure, fromType, toType
    known_keys = ["from", "to", "departure", "fromType", "toType"]

    # Build regex to split on known keys
    # Pattern: key:value where value extends until the next known key: or end
    pattern = r"(?:^|,)(" + "|".join(known_keys) + r"):(.*?)(?=,(?:" + "|".join(known_keys) + r"):|$)"
    matches = re.findall(pattern, leg_str)
    for key, value in matches:
        result[key] = value.strip()

    return result


def _normalize_cabin_class(raw: str) -> str:
    """Normalize cabin class to canonical value."""
    if not raw:
        return ""
    raw_lower = raw.lower().strip()
    return CABIN_CLASS_MAP.get(raw_lower, raw_lower)


def _normalize_hotel_sort(raw: str) -> str:
    """Normalize hotel sort to canonical value."""
    if not raw:
        return ""
    raw_upper = raw.strip().upper()
    raw_lower = raw.strip().lower().replace(" ", "_")
    # Try direct uppercase match first
    if raw_upper in {
        "RECOMMENDED", "PRICE_LOW_TO_HIGH", "PRICE_HIGH_TO_LOW",
        "DISTANCE", "DISTANCE_FROM_LANDMARK",
        "REVIEW", "GUEST_RATING",
        "STAR_RATING_HIGHEST_FIRST",
    }:
        return raw_upper
    # Try lowercase mapping
    return HOTEL_SORT_MAP.get(raw_lower, raw_upper)


def _parse_passengers(passengers_str: str) -> dict[str, Any]:
    """Parse Expedia passengers parameter.

    Browser-verified formats (Apr 2026):
      Format A (bracket-semicolon, LIVE):
        passengers=adults:2,children:2[10;5],infantinlap:N
        → children count = 2, ages = [10, 5]

      Format B (legacy/alternative):
        passengers=adults:2,children:2,childrenAge:5,8,infantinlap:N
        → children count = 2, ages = [5, 8]

    Returns dict with: adults, children, children_ages
    """
    result: dict[str, Any] = {
        "adults": "",
        "children": "",
        "children_ages": [],
        "infantinlap": "",
    }

    if not passengers_str:
        return result

    parts = passengers_str.split(",")
    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if ":" in part:
            key, value = part.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "adults":
                result["adults"] = value
            elif key == "children":
                # Browser-verified format: children:2[10;5]
                # The count may have bracket-enclosed ages attached
                bracket_match = re.match(r"^(\d+)\[([^\]]+)\]$", value)
                if bracket_match:
                    result["children"] = bracket_match.group(1)
                    # Ages are semicolon-separated inside brackets
                    ages_str = bracket_match.group(2)
                    ages = [a.strip() for a in ages_str.split(";") if a.strip()]
                    result["children_ages"] = sorted(ages)
                else:
                    result["children"] = value
            elif key in ("childrenage", "childrenages", "childage"):
                # Legacy format: childrenAge:5,8
                # Ages might span across multiple comma-separated parts
                ages = [value] if value else []
                # Look ahead for bare numbers that are continuation of ages
                while i + 1 < len(parts) and ":" not in parts[i + 1]:
                    i += 1
                    ages.append(parts[i].strip())
                result["children_ages"] = sorted([a for a in ages if a])
            elif key == "infantinlap":
                result["infantinlap"] = value.upper()
        i += 1

    return result


# =============================================================================
# FLIGHT URL PARSER
# =============================================================================


def parse_flight_url(url: str) -> dict[str, Any]:
    """Parse an Expedia flight search URL into normalized components.

    Flight URL anatomy:
      /Flights-Search?trip=oneway
        &leg1=from:JFK,to:LAX,departure:4/16/2026TANYT,fromType:AIRPORT,toType:AIRPORT
        [&leg2=from:LAX,to:JFK,departure:4/20/2026TANYT,fromType:AIRPORT,toType:AIRPORT]
        &options=cabinclass:economy
        &passengers=adults:1,infantinlap:N

    Returns dict with keys:
      origin, destination, depart_date, return_date,
      trip_type, cabin_class, adults, children, children_ages
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)

    result: dict[str, Any] = {
        "origin": "",
        "destination": "",
        "depart_date": "",
        "return_date": "",
        "trip_type": "",
        "cabin_class": "",
        "adults": "",
        "children": "",
        "children_ages": [],
        "infantinlap": "",
    }

    # Trip type
    trip = _get_param(query, "trip")
    if trip:
        result["trip_type"] = trip.lower()

    # Parse leg1 (outbound)
    leg1_raw = _get_param(query, "leg1")
    if leg1_raw:
        leg1 = _parse_leg_param(leg1_raw)
        result["origin"] = _extract_iata_code(leg1.get("from", ""))
        result["destination"] = _extract_iata_code(leg1.get("to", ""))
        result["depart_date"] = _normalize_date(leg1.get("departure", ""))

    # Parse leg2 (return — for roundtrip)
    leg2_raw = _get_param(query, "leg2")
    if leg2_raw:
        leg2 = _parse_leg_param(leg2_raw)
        result["return_date"] = _normalize_date(leg2.get("departure", ""))

    # Cabin class from options param
    options_raw = _get_param(query, "options")
    if options_raw:
        # Format: cabinclass:economy or cabinclass:business
        cc_match = re.search(r"cabinclass:(\w+)", options_raw, re.IGNORECASE)
        if cc_match:
            result["cabin_class"] = _normalize_cabin_class(cc_match.group(1))

    # Passengers
    passengers_raw = _get_param(query, "passengers")
    if passengers_raw:
        pax = _parse_passengers(passengers_raw)
        result["adults"] = pax["adults"]
        result["children"] = pax["children"]
        result["children_ages"] = pax["children_ages"]
        result["infantinlap"] = pax.get("infantinlap", "")

    return result


# =============================================================================
# HOTEL URL PARSER
# =============================================================================


def parse_hotel_url(url: str) -> dict[str, Any]:
    """Parse an Expedia hotel search URL into normalized components.

    Browser-verified Hotel URL anatomy (Apr 2026):
      /Hotel-Search?destination=New%20York%2C%20New%20York%2C%20United%20States%20of%20America
        &regionId=2621
        &latLong=40.712843%2C-74.005966
        &flexibility=0_DAY
        &d1=2026-04-16&startDate=2026-04-16
        &d2=2026-04-19&endDate=2026-04-19
        &adults=2          (or adults=2,1,1 for multi-room)
        &rooms=1
        &sort=RECOMMENDED
        [&children=1_10,1_5]  (RoomIndex_Age format)

    Returns dict with keys:
      destination, region_id, start_date, end_date,
      adults, rooms, children, children_ages, sort
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)

    # Children ages: support BOTH formats
    # Format A (browser-verified): children=1_10,1_5 (RoomIndex_Age)
    # Format B (legacy): childrenAges=10,5 (comma-separated)
    children_raw = _get_param(query, "children")
    children_ages_raw = _get_param(query, "childrenAges", "children_ages", "childrenAge")

    children_count = ""
    children_ages: list[str] = []

    if children_raw and "_" in children_raw:
        # Browser-verified RoomIndex_Age format: children=1_10,1_5
        # Each entry is RoomIndex_Age, extract just the ages
        entries = [e.strip() for e in children_raw.split(",") if e.strip()]
        for entry in entries:
            parts = entry.split("_", 1)
            if len(parts) == 2:
                children_ages.append(parts[1])
            else:
                children_ages.append(entry)
        children_count = str(len(entries))
        children_ages = sorted(children_ages)
    elif children_ages_raw:
        # Legacy format: childrenAges=10,5
        children_ages = sorted([a.strip() for a in children_ages_raw.split(",") if a.strip()])
        children_count = _get_param(query, "children") or str(len(children_ages))
    elif children_raw:
        # Plain count without ages (e.g., children=2)
        children_count = children_raw

    # Adults: may be comma-separated for multi-room (e.g., adults=2,1,1)
    # Sum them for total adults count
    adults_raw = _get_param(query, "adults")
    if adults_raw and "," in adults_raw:
        # Multi-room: adults=2,1,1 → total = 4, rooms = 3
        adult_parts = [a.strip() for a in adults_raw.split(",") if a.strip()]
        adults_total = str(sum(int(a) for a in adult_parts if a.isdigit()))
        rooms_from_adults = str(len(adult_parts))
    else:
        adults_total = adults_raw
        rooms_from_adults = ""

    rooms_raw = _get_param(query, "rooms")
    # Use rooms from adults list if rooms param doesn't match
    rooms = rooms_from_adults if rooms_from_adults and int(rooms_from_adults) > 1 else rooms_raw

    # Dates: support d1/d2 as alternatives to startDate/endDate
    start_date = _normalize_date(
        _get_param(query, "startDate", "start_date", "checkIn", "checkin", "d1")
    )
    end_date = _normalize_date(
        _get_param(query, "endDate", "end_date", "checkOut", "checkout", "d2")
    )

    return {
        "destination": _get_param(query, "destination").lower().strip(),
        "region_id": _get_param(query, "regionId", "region_id"),
        "start_date": start_date,
        "end_date": end_date,
        "adults": adults_total,
        "rooms": rooms,
        "children": children_count,
        "children_ages": children_ages,
        "sort": _normalize_hotel_sort(_get_param(query, "sort")),
    }


# =============================================================================
# VERIFIER CLASS
# =============================================================================


@beartype
class ExpediaUrlMatch(BaseMetric):
    """Comprehensive Expedia URL verifier for flights and hotels.

    Browser-Verified (Apr 2026 on expedia.com):
    - Flight path: /Flights-Search
    - Flight params: trip, leg1 (from/to/departure), leg2, options (cabinclass), passengers
    - Hotel path: /Hotel-Search
    - Hotel params: destination, startDate, endDate, adults, rooms, sort, regionId
    - Domain variations: .com, regional (.co.uk, .de, etc.)
    - Origin/dest support both IATA codes and full city+airport strings
    - Dates normalized across M/D/YYYY, YYYY-M-D, YYYY-MM-DD formats
    """

    def __init__(self, gt_url: str | list[str]) -> None:
        """
        Args:
            gt_url: Ground truth URL(s). If a list is provided, matching ANY
                    URL in the list counts as a match (OR semantics).
        """
        super().__init__()
        if isinstance(gt_url, str):
            self.gt_urls = [gt_url]
        else:
            self.gt_urls = gt_url
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details: dict = {}
        self._page_type = ""

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(gt_urls={self.gt_urls})"

    async def reset(self) -> None:
        """Reset the match state for new evaluation."""
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details = {}
        self._page_type = ""

    async def update(self, **kwargs) -> None:
        """Update with new URL to check against ground truth."""
        inputs: InputDict = kwargs
        url = inputs.get("url", "")

        if not url:
            logger.debug("Empty URL provided")
            return

        # Validate domain
        parsed = urlparse(url.strip())
        domain = (parsed.hostname or "").lower()
        if domain and not self._is_valid_expedia_domain(domain):
            logger.debug(f"Ignoring non-Expedia URL: {url}")
            return

        # Don't overwrite after match
        if self._found_match:
            return

        self._agent_url = url
        self._page_type = detect_page_type(url)

        for gt_url in self.gt_urls:
            match, details = self._urls_match(url, gt_url)
            if match:
                self._found_match = True
                self._matched_gt_url = gt_url
                self._match_details = details
                logger.info(f"Match found: {url[:100]}...")
                return

        logger.info(f"No match found: {url[:100]}...")

    async def compute(self) -> FinalResult:
        """Compute final score (1.0 = match, 0.0 = no match)."""
        score = 1.0 if self._found_match else 0.0
        result = FinalResult(score=score)
        logger.info(f"Final score: {score}")
        return result

    async def compute_detailed(self) -> ExpediaVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return ExpediaVerifierResult(
            score=score,
            match=self._found_match,
            page_type=self._page_type,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

    # ========================================================================
    # DOMAIN VALIDATION
    # ========================================================================

    @staticmethod
    def _is_valid_expedia_domain(domain: str) -> bool:
        """Check if domain is a valid Expedia domain.

        Accepts:
        - Exact matches: expedia.com
        - www prefix: www.expedia.com
        - Regional: expedia.co.uk, expedia.de, expedia.co.in, etc.
        - Any subdomain of the above
        """
        domain = domain.lower().rstrip(".")

        # Direct match on known domains
        for base in VALID_BASE_DOMAINS:
            if domain == base or domain.endswith("." + base):
                return True

        # Regional domains
        for regional in REGIONAL_DOMAINS:
            if domain == regional or domain.endswith("." + regional):
                return True

        # Generic pattern: anything.expedia.xxx
        if re.match(r"^([\w-]+\.)*expedia\.\w+(\.\w+)?$", domain):
            return True

        return False

    # ========================================================================
    # URL MATCHING DISPATCH
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Compare two Expedia URLs based on detected page type."""
        details: dict[str, Any] = {"mismatches": [], "extra_params": []}

        try:
            gt_type = detect_page_type(gt_url)
            agent_type = detect_page_type(agent_url)

            # Page types must match
            if gt_type != agent_type:
                details["mismatches"].append(
                    f"Page type mismatch: agent='{agent_type}' vs gt='{gt_type}'"
                )
                return False, details

            if gt_type == "flights":
                return self._match_flight_urls(agent_url, gt_url, details)
            elif gt_type == "hotels":
                return self._match_hotel_urls(agent_url, gt_url, details)
            else:
                details["mismatches"].append(f"Unsupported page type: {gt_type}")
                return False, details

        except Exception as e:
            logger.error(f"Error comparing URLs: {e}")
            details["mismatches"].append(f"Parse error: {str(e)}")
            return False, details

    # ========================================================================
    # FLIGHT MATCHING
    # ========================================================================

    def _match_flight_urls(
        self, agent_url: str, gt_url: str, details: dict
    ) -> tuple[bool, dict]:
        """Compare two flight search URLs."""
        agent = parse_flight_url(agent_url)
        gt = parse_flight_url(gt_url)

        # 1. Origin
        if gt["origin"]:
            if not agent["origin"]:
                details["mismatches"].append(
                    f"Origin missing (expected '{gt['origin']}')"
                )
                return False, details
            if agent["origin"] != gt["origin"]:
                details["mismatches"].append(
                    f"Origin: '{agent['origin']}' vs '{gt['origin']}'"
                )
                return False, details

        # 2. Destination
        if gt["destination"]:
            if not agent["destination"]:
                details["mismatches"].append(
                    f"Destination missing (expected '{gt['destination']}')"
                )
                return False, details
            if agent["destination"] != gt["destination"]:
                details["mismatches"].append(
                    f"Destination: '{agent['destination']}' vs '{gt['destination']}'"
                )
                return False, details

        # 3. Departure date
        if gt["depart_date"]:
            if not agent["depart_date"]:
                details["mismatches"].append(
                    f"Depart date missing (expected '{gt['depart_date']}')"
                )
                return False, details
            if agent["depart_date"] != gt["depart_date"]:
                details["mismatches"].append(
                    f"Depart date: '{agent['depart_date']}' vs '{gt['depart_date']}'"
                )
                return False, details

        # 4. Return date (only for roundtrip)
        if gt["return_date"]:
            if not agent["return_date"]:
                details["mismatches"].append(
                    f"Return date missing (expected '{gt['return_date']}')"
                )
                return False, details
            if agent["return_date"] != gt["return_date"]:
                details["mismatches"].append(
                    f"Return date: '{agent['return_date']}' vs '{gt['return_date']}'"
                )
                return False, details

        # 5. Trip type
        if gt["trip_type"]:
            if not agent["trip_type"]:
                details["mismatches"].append(
                    f"Trip type missing (expected '{gt['trip_type']}')"
                )
                return False, details
            if agent["trip_type"] != gt["trip_type"]:
                details["mismatches"].append(
                    f"Trip type: '{agent['trip_type']}' vs '{gt['trip_type']}'"
                )
                return False, details

        # 6. Cabin class
        if gt["cabin_class"]:
            if not agent["cabin_class"]:
                details["mismatches"].append(
                    f"Cabin class missing (expected '{gt['cabin_class']}')"
                )
                return False, details
            if agent["cabin_class"] != gt["cabin_class"]:
                details["mismatches"].append(
                    f"Cabin class: '{agent['cabin_class']}' vs '{gt['cabin_class']}'"
                )
                return False, details

        # 7. Adults
        if gt["adults"]:
            if not agent["adults"]:
                details["mismatches"].append(
                    f"Adults missing (expected '{gt['adults']}')"
                )
                return False, details
            if agent["adults"] != gt["adults"]:
                details["mismatches"].append(
                    f"Adults: '{agent['adults']}' vs '{gt['adults']}'"
                )
                return False, details

        # 8. Children count
        if gt["children"]:
            if not agent["children"]:
                details["mismatches"].append(
                    f"Children count missing (expected '{gt['children']}')"
                )
                return False, details
            if agent["children"] != gt["children"]:
                details["mismatches"].append(
                    f"Children: '{agent['children']}' vs '{gt['children']}'"
                )
                return False, details

        # 9. Children ages (order-independent)
        if gt["children_ages"]:
            if not agent["children_ages"]:
                details["mismatches"].append(
                    f"Children ages missing (expected {gt['children_ages']})"
                )
                return False, details
            if sorted(agent["children_ages"]) != sorted(gt["children_ages"]):
                details["mismatches"].append(
                    f"Children ages: {agent['children_ages']} vs {gt['children_ages']}"
                )
                return False, details

        # 10. Infant in lap (only validate when GT expects a lap infant)
        gt_infant = gt.get("infantinlap", "")
        agent_infant = agent.get("infantinlap", "")
        if gt_infant == "Y":
            if agent_infant != "Y":
                details["mismatches"].append(
                    f"Infant in lap: expected 'Y' but got '{agent_infant or 'missing'}'"
                )
                return False, details

        return True, details

    # ========================================================================
    # HOTEL MATCHING
    # ========================================================================

    def _match_hotel_urls(
        self, agent_url: str, gt_url: str, details: dict
    ) -> tuple[bool, dict]:
        """Compare two hotel search URLs."""
        agent = parse_hotel_url(agent_url)
        gt = parse_hotel_url(gt_url)

        # 1. Location: prefer regionId, fall back to destination string
        if gt["region_id"]:
            if not agent["region_id"]:
                # Agent might not have regionId — try destination match
                if gt["destination"] and agent["destination"]:
                    if not self._destinations_match(agent["destination"], gt["destination"]):
                        details["mismatches"].append(
                            f"region_id missing and destination mismatch: "
                            f"'{agent['destination']}' vs '{gt['destination']}'"
                        )
                        return False, details
                else:
                    details["mismatches"].append(
                        f"region_id missing (expected '{gt['region_id']}')"
                    )
                    return False, details
            elif agent["region_id"] != gt["region_id"]:
                details["mismatches"].append(
                    f"region_id: '{agent['region_id']}' vs '{gt['region_id']}'"
                )
                return False, details
        elif gt["destination"]:
            if not agent["destination"]:
                details["mismatches"].append(
                    f"Destination missing (expected '{gt['destination']}')"
                )
                return False, details
            if not self._destinations_match(agent["destination"], gt["destination"]):
                details["mismatches"].append(
                    f"Destination: '{agent['destination']}' vs '{gt['destination']}'"
                )
                return False, details

        # 2. Start date
        if gt["start_date"]:
            if not agent["start_date"]:
                details["mismatches"].append(
                    f"start_date missing (expected '{gt['start_date']}')"
                )
                return False, details
            if agent["start_date"] != gt["start_date"]:
                details["mismatches"].append(
                    f"start_date: '{agent['start_date']}' vs '{gt['start_date']}'"
                )
                return False, details

        # 3. End date
        if gt["end_date"]:
            if not agent["end_date"]:
                details["mismatches"].append(
                    f"end_date missing (expected '{gt['end_date']}')"
                )
                return False, details
            if agent["end_date"] != gt["end_date"]:
                details["mismatches"].append(
                    f"end_date: '{agent['end_date']}' vs '{gt['end_date']}'"
                )
                return False, details

        # 4. Adults
        if gt["adults"]:
            if not agent["adults"]:
                details["mismatches"].append(
                    f"adults missing (expected '{gt['adults']}')"
                )
                return False, details
            if agent["adults"] != gt["adults"]:
                details["mismatches"].append(
                    f"adults: '{agent['adults']}' vs '{gt['adults']}'"
                )
                return False, details

        # 5. Rooms
        if gt["rooms"]:
            if not agent["rooms"]:
                details["mismatches"].append(
                    f"rooms missing (expected '{gt['rooms']}')"
                )
                return False, details
            if agent["rooms"] != gt["rooms"]:
                details["mismatches"].append(
                    f"rooms: '{agent['rooms']}' vs '{gt['rooms']}'"
                )
                return False, details

        # 6. Children count
        if gt["children"]:
            if not agent["children"]:
                details["mismatches"].append(
                    f"children count missing (expected '{gt['children']}')"
                )
                return False, details
            if agent["children"] != gt["children"]:
                details["mismatches"].append(
                    f"children: '{agent['children']}' vs '{gt['children']}'"
                )
                return False, details

        # 7. Children ages (order-independent)
        if gt["children_ages"]:
            if not agent["children_ages"]:
                details["mismatches"].append(
                    f"children_ages missing (expected {gt['children_ages']})"
                )
                return False, details
            if sorted(agent["children_ages"]) != sorted(gt["children_ages"]):
                details["mismatches"].append(
                    f"children_ages: {agent['children_ages']} vs {gt['children_ages']}"
                )
                return False, details

        # 8. Sort
        if gt["sort"]:
            if not agent["sort"]:
                details["mismatches"].append(
                    f"sort missing (expected '{gt['sort']}')"
                )
                return False, details
            if agent["sort"] != gt["sort"]:
                details["mismatches"].append(
                    f"sort: '{agent['sort']}' vs '{gt['sort']}'"
                )
                return False, details

        return True, details

    # ========================================================================
    # DESTINATION MATCHING HELPERS
    # ========================================================================

    @staticmethod
    def _destinations_match(agent_dest: str, gt_dest: str) -> bool:
        """Fuzzy match two destination strings.

        Expedia destination strings can vary widely:
          - 'new york' vs 'new york, new york, united states of america'
          - 'paris' vs 'paris, france'

        Strategy: check if the shorter string is contained within the longer string.
        """
        a = agent_dest.lower().strip()
        g = gt_dest.lower().strip()

        if a == g:
            return True

        # Check containment either way
        if a in g or g in a:
            return True

        # Extract first part before comma for comparison
        a_city = a.split(",")[0].strip()
        g_city = g.split(",")[0].strip()

        return a_city == g_city


# =============================================================================
# TASK CONFIG GENERATION
# =============================================================================


def generate_task_config(
    task: str,
    location: str,
    timezone: str,
    gt_url: list[str] | None = None,
    ground_truth_url: str | None = None,
    timestamp: int | None = None,
    url: str = "https://www.expedia.com/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Expedia URL matching.

    Accepts either ``gt_url`` (list of strings) or ``ground_truth_url``
    (single string) for backward compat.

    Args:
        task: Task description. May contain ``{placeholder}`` tokens.
        location: User location string.
        timezone: IANA timezone string.
        gt_url: Ground-truth URL(s).
        ground_truth_url: Single GT URL (alternative to gt_url).
        timestamp: Unix timestamp. ``None`` means "now".
        url: Starting URL.
        values: Placeholder-key → relative-date expression mapping.
    """
    # Resolve gt_url from either parameter
    if gt_url is None and ground_truth_url is not None:
        gt_url = [ground_truth_url]
    elif isinstance(gt_url, str):
        gt_url = [gt_url]
    elif gt_url is None:
        raise ValueError("Either 'gt_url' or 'ground_truth_url' must be provided.")

    values = values or {}
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    resolved_placeholders, _ = initialize_placeholder_map(user_metadata, values)

    # Render {placeholder} tokens in task text
    rendered_task = render_task_statement(task, resolved_placeholders)

    # Substitute resolved dates into gt_url strings
    # Expedia uses multiple date formats — we keep ISO (YYYY-MM-DD) as the canonical form
    # and also generate M/D/YYYY format for leg params
    rendered_gt_urls: list[str] = []
    for u in gt_url:
        rendered_u = u
        for placeholder_key, (_, dates) in resolved_placeholders.items():
            template = "{" + placeholder_key + "}"
            if template in rendered_u and dates:
                rendered_u = rendered_u.replace(template, dates[0])
        rendered_gt_urls.append(rendered_u)

    eval_target = get_import_path(ExpediaUrlMatch)
    eval_config = {"_target_": eval_target, "gt_url": rendered_gt_urls}
    return BaseTaskConfig(
        url=url,
        task=rendered_task,
        user_metadata=user_metadata,
        eval_config=eval_config,
    )