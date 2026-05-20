import functools
import asyncio
from typing import Literal
"""Skyscanner URL Match verifier for flight, hotel, and car hire search navigation.

This module provides functionality to verify AI agent navigation on Skyscanner
by comparing the agent's final URL against expected ground truth URLs.

The verifier handles all Skyscanner URL variations including:
- Flight search paths: /transport/flights/{origin}/{dest}/{YYYY-MM-DD}[/{YYYY-MM-DD}] (ISO) or YYMMDD (legacy)
- Hotel search params: entity_id, checkin, checkout, adults, rooms, sort
- Car hire paths: /carhire/results/{pickup}/{dropoff}/{datetimeISO}/{datetimeISO}[/{age}]
- Flight query params: rtn, adultsv2, childrenv2, cabinclass, stops, airlines, alliances
- Domain variations: skyscanner.net, skyscanner.com, regional subdomains
- Filter order independence, case-insensitive comparison

Browser-Verified Patterns (Mar 2026 on skyscanner.net):
  Flight path: /transport/flights/jfk/lax/260425/ (YYMMDD — ISO format causes 404!)
  Flight params: adultsv2=2, cabinclass=business, rtn=1
  Stops: stops=!oneStop,!twoPlusStops (exclusion-prefix format)
  Alliances: alliances=Star Alliance (with space, URL-encoded %20)
  Airlines: airlines=-32593 (internal numeric IDs)
  Hotel params: entity_id=27544008, checkin=2026-04-20, checkout=2026-04-25
  Hotel sort: sort=price | -price | distance | -hotel_rating
  Car hire path: /carhire/results/95565085/95565085/2026-04-20T10:00/2026-04-25T10:00/30
  Car hire locations: Internal numeric IDs, NOT IATA codes
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
    n_queries: int | None = None
    n_covered: int | None = None
    queries: list | None = None
    is_query_covered: list | None = None

class SkyscannerVerifierResult(BaseModel):
    """Detailed verification result for Skyscanner URL matching."""

    score: float
    match: bool
    page_type: str = ""
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid Skyscanner domain patterns — accept any subdomain of these
VALID_BASE_DOMAINS = {
    "skyscanner.net",
    "skyscanner.com",
}

# Regional domains (.co.in, .co.uk, .de, .fr, .jp, etc.)
REGIONAL_TLDS = {
    "skyscanner.co.in",
    "skyscanner.co.uk",
    "skyscanner.de",
    "skyscanner.fr",
    "skyscanner.es",
    "skyscanner.it",
    "skyscanner.jp",
    "skyscanner.com.au",
    "skyscanner.com.br",
    "skyscanner.ca",
    "skyscanner.se",
    "skyscanner.no",
    "skyscanner.dk",
    "skyscanner.fi",
    "skyscanner.pl",
    "skyscanner.pt",
    "skyscanner.ie",
    "skyscanner.at",
    "skyscanner.ch",
    "skyscanner.com.sg",
    "skyscanner.com.hk",
    "skyscanner.co.kr",
}


# =============================================================================
# PAGE TYPE DETECTION
# =============================================================================


def detect_page_type(url: str) -> str:
    """Detect the Skyscanner page type from a URL.

    Returns one of: 'flights', 'hotels', 'carhire', 'browse', 'multicity', 'other'.
    """
    parsed = urlparse(url.strip())
    path = parsed.path.lower()

    if "/transport/d/" in path:
        return "multicity"
    if "/transport/flights-from/" in path:
        return "browse"
    if "/transport/flights/" in path:
        return "flights"
    if "/hotels/" in path:
        return "hotels"
    if "/carhire/" in path:
        return "carhire"
    return "other"


# =============================================================================
# PARSING HELPERS
# =============================================================================


def _normalize_stops(raw: str) -> set[str]:
    """Normalize the stops parameter into a canonical set.

    Skyscanner uses exclusion-prefix format:
        stops=!oneStop,!twoPlusStops  →  {'!oneStop', '!twoPlusStops'}
        stops=direct                   →  {'direct'}
    """
    parts = [s.strip() for s in raw.split(",") if s.strip()]
    return set(parts)


def _normalize_airlines(raw: str) -> set[str]:
    """Normalize airline IDs into a set.

    Airlines are internal numeric IDs, possibly negative:
        airlines=-32593,-32596  →  {'-32593', '-32596'}
    """
    parts = [a.strip() for a in raw.split(",") if a.strip()]
    return set(parts)


def _normalize_alliances(raw: str) -> set[str]:
    """Normalize alliances into a canonical set.

    Browser-verified: alliance values may contain spaces:
        alliances=Star Alliance  →  {'star alliance'}
        alliances=oneworld       →  {'oneworld'}

    Case-insensitive matching with whitespace normalization.
    """
    parts = [a.strip() for a in raw.split(",") if a.strip()]
    # Normalize: lowercase + collapse whitespace
    return {" ".join(a.lower().split()) for a in parts}


def _normalize_children(raw: str) -> list[str]:
    """Normalize children ages.

    childrenv2=5|8  →  ['5', '8']
    Also handles comma-separated fallback.
    """
    if "|" in raw:
        return sorted([c.strip() for c in raw.split("|") if c.strip()])
    return sorted([c.strip() for c in raw.split(",") if c.strip()])


# =============================================================================
# FLIGHT URL PARSER
# =============================================================================


def parse_flight_url(url: str) -> dict[str, Any]:
    """Parse a Skyscanner flight URL into normalized components.

    Flight URL anatomy:
      /transport/flights/{origin}/{dest}/{YYMMDD}[/{YYMMDD}][/]?params

    Returns dict with keys:
      origin, destination, depart_date, return_date,
      rtn, adults, children_ages, cabin_class,
      stops, airlines, alliances, prefer_directs
    """
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query, keep_blank_values=True)

    result: dict[str, Any] = {
        "origin": "",
        "destination": "",
        "depart_date": "",
        "return_date": "",
        "rtn": "",
        "adults": "",
        "children_ages": [],
        "cabin_class": "",
        "stops": set(),
        "airlines": set(),
        "alliances": set(),
        "prefer_directs": "",
    }

    # Extract path segments: /transport/flights/JFK/LAX/260420[/260425]
    # Accept both YYMMDD (e.g. 260420) and YYYY-MM-DD ISO (e.g. 2026-04-20).
    # dates.py always produces YYYY-MM-DD, so the ISO branch is the primary path.
    _DATE_PAT = r"(\d{4}-\d{2}-\d{2}|\d{6})"
    flight_match = re.search(
        rf"/transport/flights/([a-zA-Z]{{2,5}})/([a-zA-Z]{{2,5}})/{_DATE_PAT}(?:/{_DATE_PAT})?",
        path,
        re.IGNORECASE,
    )
    if flight_match:
        result["origin"] = flight_match.group(1).lower()
        result["destination"] = flight_match.group(2).lower()
        result["depart_date"] = flight_match.group(3)
        if flight_match.group(4):
            result["return_date"] = flight_match.group(4)

    # Query parameters
    result["rtn"] = _get_param(query, "rtn")
    result["adults"] = _get_param(query, "adultsv2")
    result["cabin_class"] = _get_param(query, "cabinclass").lower()
    result["prefer_directs"] = _get_param(query, "preferdirects").lower()

    # Children ages
    children_raw = _get_param(query, "childrenv2")
    if children_raw:
        result["children_ages"] = _normalize_children(children_raw)

    # Stops (exclusion format)
    stops_raw = _get_param(query, "stops")
    if stops_raw:
        result["stops"] = _normalize_stops(stops_raw)

    # Airlines (numeric IDs)
    airlines_raw = _get_param(query, "airlines")
    if airlines_raw:
        result["airlines"] = _normalize_airlines(airlines_raw)

    # Alliances (may have spaces — e.g. "Star Alliance"; normalized to lowercase)
    alliances_raw = _get_param(query, "alliances")
    if alliances_raw:
        result["alliances"] = _normalize_alliances(alliances_raw)

    return result


# =============================================================================
# HOTEL URL PARSER
# =============================================================================


def parse_hotel_url(url: str) -> dict[str, Any]:
    """Parse a Skyscanner hotel search URL into normalized components.

    Hotel URL anatomy:
      /hotels/search?entity_id=27544008&checkin=2026-04-20&checkout=2026-04-25
        &adults=2&rooms=1&children=2&children_ages=6,9&sort=price

    Hotel children encoding (browser-verified, differs from flight encoding):
      - Flight: childrenv2=5|8 (pipe-separated ages, no count)
      - Hotel:  children=2&children_ages=6,9 (count + comma-separated ages separately)

    Returns dict with keys:
      entity_id, checkin, checkout, adults, rooms, children, children_ages, sort
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)

    # Hotel children_ages are comma-separated; normalize to sorted list for comparison
    children_ages_raw = _get_param(query, "children_ages")
    children_ages = sorted([a.strip() for a in children_ages_raw.split(",") if a.strip()])

    return {
        "entity_id": _get_param(query, "entity_id"),
        "checkin": _get_param(query, "checkin"),
        "checkout": _get_param(query, "checkout"),
        "adults": _get_param(query, "adults"),
        "rooms": _get_param(query, "rooms"),
        "children": _get_param(query, "children"),
        "children_ages": children_ages,
        "sort": _get_param(query, "sort").lower(),
    }


# =============================================================================
# CAR HIRE URL PARSER
# =============================================================================


def parse_carhire_url(url: str) -> dict[str, Any]:
    """Parse a Skyscanner car hire URL into normalized components.

    Car hire URL anatomy (browser-verified):
      /carhire/results/{pickup_id}/{dropoff_id}/{YYYY-MM-DDTHH:MM}/{YYYY-MM-DDTHH:MM}[/{age}]

    IMPORTANT: Pickup/Dropoff identifiers are internal numeric IDs, NOT IATA codes.
      e.g., Barcelona = 95565085, LHR = 95565050, LGW = 95565051
    The verifier accepts BOTH numeric IDs and IATA codes for backward compatability.

    Returns dict with keys:
      pickup_location, dropoff_location, pickup_datetime, dropoff_datetime, driver_age
    """
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")

    result: dict[str, Any] = {
        "pickup_location": "",
        "dropoff_location": "",
        "pickup_datetime": "",
        "dropoff_datetime": "",
        "driver_age": "",
    }

    # Extract path segments after /carhire/results/
    # Locations can be:
    #   - Internal numeric IDs (e.g., 95565085)
    #   - IATA codes (e.g., BCN, LHR) — for legacy/manual URLs
    #   - City slugs (e.g., barcelona)
    carhire_match = re.search(
        r"/carhire/results/([^/]+)/([^/]+)/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})(?:/(\d+))?",
        path,
        re.IGNORECASE,
    )
    if carhire_match:
        result["pickup_location"] = carhire_match.group(1).lower()
        result["dropoff_location"] = carhire_match.group(2).lower()
        result["pickup_datetime"] = carhire_match.group(3)
        result["dropoff_datetime"] = carhire_match.group(4)
        if carhire_match.group(5):
            result["driver_age"] = carhire_match.group(5)

    return result


# =============================================================================
# GENERIC HELPERS
# =============================================================================


def _get_param(query: dict, *keys: str) -> str:
    """Get the first non-empty value from query dict for any of the keys.

    Handles both exact keys and case-insensitive fallback.
    """
    for key in keys:
        if key in query and query[key]:
            return unquote(query[key][0])
        key_lower = key.lower()
        if key_lower in query and query[key_lower]:
            return unquote(query[key_lower][0])
    return ""


# =============================================================================
# VERIFIER CLASS
# =============================================================================


@beartype
class SkyscannerUrlMatch(BaseMetric):
    """Comprehensive Skyscanner URL verifier for flights, hotels, and car hire.

    Browser-Verified (Mar 2026 on skyscanner.net):
    - Flight path: /transport/flights/{origin}/{dest}/{YYYY-MM-DD}[/{YYYY-MM-DD}] (ISO primary)
    - Flight params: adultsv2, childrenv2 (pipe-sep), cabinclass, rtn, stops, airlines, alliances
    - Hotel params: entity_id, checkin, checkout, adults, rooms, sort
    - Car hire path: /carhire/results/{numeric_id}/{numeric_id}/{datetimeISO}/{datetimeISO}/{age}
    - Car hire locations use INTERNAL NUMERIC IDs (95565085), not IATA codes
    - Domain variations: .net, .com, regional (.co.in, .co.uk, .de, etc.)
    - Stops use exclusion-prefix: stops=!oneStop,!twoPlusStops
    - Airlines use internal numeric IDs
    - Alliances may have spaces: Star Alliance, oneworld, SkyTeam
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
        if domain and not self._is_valid_skyscanner_domain(domain):
            logger.debug(f"Ignoring non-Skyscanner URL: {url}")
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

    async def compute_detailed(self) -> SkyscannerVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return SkyscannerVerifierResult(
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
    def _is_valid_skyscanner_domain(domain: str) -> bool:
        """Check if domain is a valid Skyscanner domain.

        Accepts:
        - Exact matches: skyscanner.net, skyscanner.com
        - www prefix: www.skyscanner.net
        - Regional: skyscanner.co.in, skyscanner.co.uk, skyscanner.de
        - Any subdomain of the above
        """
        domain = domain.lower().rstrip(".")

        # Direct match on known domains
        for base in VALID_BASE_DOMAINS:
            if domain == base or domain.endswith("." + base):
                return True

        # Regional TLDs
        for regional in REGIONAL_TLDS:
            if domain == regional or domain.endswith("." + regional):
                return True

        # Generic pattern: anything.skyscanner.xxx
        if re.match(r"^([\w-]+\.)*skyscanner\.\w+(\.\w+)?$", domain):
            return True

        return False

    # ========================================================================
    # URL MATCHING DISPATCH
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Compare two Skyscanner URLs based on detected page type."""
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
            elif gt_type == "carhire":
                return self._match_carhire_urls(agent_url, gt_url, details)
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

        # 4. Return date
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

        # 5. Trip type (rtn)
        if gt["rtn"]:
            if agent["rtn"] and agent["rtn"] != gt["rtn"]:
                details["mismatches"].append(
                    f"Trip type (rtn): '{agent['rtn']}' vs '{gt['rtn']}'"
                )
                return False, details

        # 6. Adults
        if gt["adults"]:
            if agent["adults"] and agent["adults"] != gt["adults"]:
                details["mismatches"].append(
                    f"Adults: '{agent['adults']}' vs '{gt['adults']}'"
                )
                return False, details

        # 7. Children ages (order-independent)
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

        # 8. Cabin class
        if gt["cabin_class"]:
            if agent["cabin_class"] and agent["cabin_class"] != gt["cabin_class"]:
                details["mismatches"].append(
                    f"Cabin class: '{agent['cabin_class']}' vs '{gt['cabin_class']}'"
                )
                return False, details

        # 9. Stops (set comparison — exclusion-prefix format)
        if gt["stops"]:
            if not agent["stops"]:
                details["mismatches"].append(
                    f"Stops filter missing (expected {gt['stops']})"
                )
                return False, details
            if agent["stops"] != gt["stops"]:
                details["mismatches"].append(
                    f"Stops: {agent['stops']} vs {gt['stops']}"
                )
                return False, details

        # 10. Airlines (set comparison — numeric IDs)
        if gt["airlines"]:
            if not agent["airlines"]:
                details["mismatches"].append(
                    f"Airlines filter missing (expected {gt['airlines']})"
                )
                return False, details
            if agent["airlines"] != gt["airlines"]:
                details["mismatches"].append(
                    f"Airlines: {agent['airlines']} vs {gt['airlines']}"
                )
                return False, details

        # 11. Alliances (set comparison — case-insensitive)
        if gt["alliances"]:
            if not agent["alliances"]:
                details["mismatches"].append(
                    f"Alliances filter missing (expected {gt['alliances']})"
                )
                return False, details
            if agent["alliances"] != gt["alliances"]:
                details["mismatches"].append(
                    f"Alliances: {agent['alliances']} vs {gt['alliances']}"
                )
                return False, details

        # 12. Prefer directs (fallback param — some URLs use this)
        if gt["prefer_directs"]:
            if agent["prefer_directs"] and agent["prefer_directs"] != gt["prefer_directs"]:
                details["mismatches"].append(
                    f"Prefer directs: '{agent['prefer_directs']}' vs '{gt['prefer_directs']}'"
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

        # 1. Entity ID (location identifier)
        if gt["entity_id"]:
            if not agent["entity_id"]:
                details["mismatches"].append(
                    f"entity_id missing (expected '{gt['entity_id']}')"
                )
                return False, details
            if agent["entity_id"] != gt["entity_id"]:
                details["mismatches"].append(
                    f"entity_id: '{agent['entity_id']}' vs '{gt['entity_id']}'"
                )
                return False, details

        # 2. Check-in date
        if gt["checkin"]:
            if not agent["checkin"]:
                details["mismatches"].append(
                    f"checkin missing (expected '{gt['checkin']}')"
                )
                return False, details
            if agent["checkin"] != gt["checkin"]:
                details["mismatches"].append(
                    f"checkin: '{agent['checkin']}' vs '{gt['checkin']}'"
                )
                return False, details

        # 3. Check-out date
        if gt["checkout"]:
            if not agent["checkout"]:
                details["mismatches"].append(
                    f"checkout missing (expected '{gt['checkout']}')"
                )
                return False, details
            if agent["checkout"] != gt["checkout"]:
                details["mismatches"].append(
                    f"checkout: '{agent['checkout']}' vs '{gt['checkout']}'"
                )
                return False, details

        # 4. Adults
        if gt["adults"]:
            if agent["adults"] and agent["adults"] != gt["adults"]:
                details["mismatches"].append(
                    f"adults: '{agent['adults']}' vs '{gt['adults']}'"
                )
                return False, details

        # 5. Rooms
        if gt["rooms"]:
            if agent["rooms"] and agent["rooms"] != gt["rooms"]:
                details["mismatches"].append(
                    f"rooms: '{agent['rooms']}' vs '{gt['rooms']}'"
                )
                return False, details

        # 6. Children count
        if gt["children"]:
            if agent["children"] and agent["children"] != gt["children"]:
                details["mismatches"].append(
                    f"children count: '{agent['children']}' vs '{gt['children']}'"
                )
                return False, details

        # 7. Children ages (order-independent, comma-separated in hotel URLs)
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
    # CAR HIRE MATCHING
    # ========================================================================

    def _match_carhire_urls(
        self, agent_url: str, gt_url: str, details: dict
    ) -> tuple[bool, dict]:
        """Compare two car hire search URLs."""
        agent = parse_carhire_url(agent_url)
        gt = parse_carhire_url(gt_url)

        # 1. Pickup location
        if gt["pickup_location"]:
            if not agent["pickup_location"]:
                details["mismatches"].append(
                    f"Pickup location missing (expected '{gt['pickup_location']}')"
                )
                return False, details
            if agent["pickup_location"] != gt["pickup_location"]:
                details["mismatches"].append(
                    f"Pickup location: '{agent['pickup_location']}' vs '{gt['pickup_location']}'"
                )
                return False, details

        # 2. Dropoff location
        if gt["dropoff_location"]:
            if not agent["dropoff_location"]:
                details["mismatches"].append(
                    f"Dropoff location missing (expected '{gt['dropoff_location']}')"
                )
                return False, details
            if agent["dropoff_location"] != gt["dropoff_location"]:
                details["mismatches"].append(
                    f"Dropoff location: '{agent['dropoff_location']}' vs '{gt['dropoff_location']}'"
                )
                return False, details

        # 3. Pickup datetime
        if gt["pickup_datetime"]:
            if not agent["pickup_datetime"]:
                details["mismatches"].append(
                    f"Pickup datetime missing (expected '{gt['pickup_datetime']}')"
                )
                return False, details
            if agent["pickup_datetime"] != gt["pickup_datetime"]:
                details["mismatches"].append(
                    f"Pickup datetime: '{agent['pickup_datetime']}' vs '{gt['pickup_datetime']}'"
                )
                return False, details

        # 4. Dropoff datetime
        if gt["dropoff_datetime"]:
            if not agent["dropoff_datetime"]:
                details["mismatches"].append(
                    f"Dropoff datetime missing (expected '{gt['dropoff_datetime']}')"
                )
                return False, details
            if agent["dropoff_datetime"] != gt["dropoff_datetime"]:
                details["mismatches"].append(
                    f"Dropoff datetime: '{agent['dropoff_datetime']}' vs '{gt['dropoff_datetime']}'"
                )
                return False, details

        # 5. Driver age (optional — don't fail if GT doesn't require it)
        if gt["driver_age"]:
            if agent["driver_age"] and agent["driver_age"] != gt["driver_age"]:
                details["mismatches"].append(
                    f"Driver age: '{agent['driver_age']}' vs '{gt['driver_age']}'"
                )
                return False, details

        return True, details


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
    url: str = "https://www.skyscanner.net/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Skyscanner URL matching.

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
    # IMPORTANT: Skyscanner flight paths require YYMMDD (e.g. 260425), NOT ISO (2026-04-25).
    # dates.py always produces ISO, so we convert ALL ISO date segments in a flight path
    # to YYMMDD after substitution.  This covers BOTH the depart and return date segments.
    _ISO_DATE_PAT = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

    def _flight_iso_to_yymmdd(url: str) -> str:
        """Convert all YYYY-MM-DD dates in a flight URL path to YYMMDD (e.g. 260425).

        Only modifies the path component so query-string dates (hotels, carhire)
        are left untouched.
        """
        if "/transport/flights/" not in url:
            return url
        # Split on '?' to isolate the path portion
        path_part, _, query_part = url.partition("?")
        def _iso_to_yymmdd(m: re.Match) -> str:  # type: ignore[type-arg]
            # Strip century: 2026 → 26, then append MM and DD
            return m.group(1)[2:] + m.group(2) + m.group(3)
        path_part = _ISO_DATE_PAT.sub(_iso_to_yymmdd, path_part)
        return path_part + ("?" + query_part if query_part else "")

    rendered_gt_urls: list[str] = []
    for u in gt_url:
        rendered_u = u
        for placeholder_key, (_, dates) in resolved_placeholders.items():
            template = "{" + placeholder_key + "}"
            if template in rendered_u and dates:
                rendered_u = rendered_u.replace(template, dates[0])
        # Convert every ISO date in the flight path to YYMMDD (depart AND return)
        rendered_u = _flight_iso_to_yymmdd(rendered_u)
        rendered_gt_urls.append(rendered_u)

    eval_target = get_import_path(SkyscannerUrlMatch)
    eval_config = {"_target_": eval_target, "gt_url": rendered_gt_urls}
    return BaseTaskConfig(
        url=url,
        task=rendered_task,
        user_metadata=user_metadata,
        eval_config=eval_config,
    )


# =============================================================================
# INFO GATHERING COMPONENTS
# =============================================================================

class MultiCandidateQuery(TypedDict, total=False):
    # Flight fields
    origins: list[str] | None
    destinations: list[str] | None
    depart_dates: list[str] | None
    return_dates: list[str] | None
    airlines: list[str] | None
    require_direct: bool | None
    max_stops: int | None
    cabin_classes: list[str] | None
    
    # Universal / Shared fields
    max_price: float | None
    min_price: float | None
    
    # Hotel fields
    cities: list[str] | None
    check_in_dates: list[str] | None
    check_out_dates: list[str] | None
    min_stars: int | None
    min_score: float | None
    require_freebies: list[str] | None

    # Car fields
    pickup_locations: list[str] | None
    pickup_dates: list[str] | None
    car_types: list[str] | None
    min_passengers: int | None

class InfoDict(TypedDict, total=False):
    url: str
    source: str
    pageType: str
    antiBotStatus: str
    price: float
    
    # Flight
    origin: str
    destination: str
    departDate: str
    departTime: str
    arrivalTime: str
    airline: str
    stops: int
    filterMaxStops: int
    filterAirlines: list[str]

    # Hotel
    city: str
    checkin: str
    checkout: str
    title: str
    score: float | None
    stars: int
    freebies: list[str]
    location: str

    # Car
    pickUpLocation: str
    dropOffLocation: str
    pickUpDate: str
    pickUpTime: str
    supplier: str
    transmission: str
    category: str
    passengers: int | None
    
    filterMaxPrice: float

class SkyscannerInfoGathering(BaseMetric):
    def __init__(self, queries: list[list[MultiCandidateQuery]]) -> None:
        super().__init__()
        self.queries = queries
        self._all_infos: list[list[InfoDict]] = []
        self._is_query_covered: list[bool] = [False] * len(queries)
        self._navigation_stack: list[dict] = [] 
        self._tracked_pages: set = set()

    @functools.cached_property
    def js_script(self) -> str:
        with open(Path(__file__).parent / "skyscanner_url_match.js", "r", encoding="utf-8") as f:
            return f.read()

    async def reset(self) -> None:
        self._all_infos = []
        self._is_query_covered = [False] * len(self.queries)
        self._navigation_stack = []
        self._tracked_pages = set()
    
    def attach_to_context(self, context) -> None:
        async def track_page(page) -> None:
            page_id = id(page)
            if page_id in self._tracked_pages: return
            self._tracked_pages.add(page_id)
            
            async def on_frame_navigated(frame):
                if frame != page.main_frame: return
                
                # Check for skyscanner domain
                if "skyscanner." not in frame.url:
                    return
                
                try:
                    logger.info(f"[NAV] Skyscanner: {frame.url[:80]}...")
                    await self.update(page=page)
                except Exception:
                    pass
            
            page.on("framenavigated", lambda f: asyncio.create_task(on_frame_navigated(f)))
        
        for page in context.pages:
            asyncio.create_task(track_page(page))
        context.on("page", lambda p: asyncio.create_task(track_page(p)))

    async def update(self, **kwargs) -> None:
        page = kwargs["page"]
        content = await page.content()
        
        if "cf-please-wait" in content or "challenge-running" in content or "human" in content.lower():
            logger.error("Agent blocked by Skyscanner Anti-Bot.")

        all_frame_infos: list[InfoDict] = []
        for frame in page.frames:
            try:
                frame_infos = await asyncio.wait_for(frame.evaluate(self.js_script), timeout=3.0)
                if frame_infos and isinstance(frame_infos, list):
                    all_frame_infos.extend(frame_infos)
            except Exception: pass
        
        # Deduplication
        unique_infos = []
        seen = set()
        for info in all_frame_infos:
            ptype = info.get("pageType")
            if ptype == "flights":
                key = f"flight-{info.get('airline')}-{info.get('departTime')}-{info.get('price')}"
            elif ptype in ["hotel_results", "hotels"]:
                key = f"hotel-{info.get('name')}-{info.get('price')}"
            elif ptype in ["carhire_results", "carhire"]:
                key = f"car-{info.get('name')}-{info.get('supplier')}-{info.get('price')}"
            else:
                key = str(info)
                
            if key not in seen:
                seen.add(key)
                unique_infos.append(info)
        
        infos = unique_infos

        if infos:
            print(f"\n[SCRAPED DATA FROM: {page.url[:60]}...]", flush=True)
            
            first_info = infos[0]
            ptype = first_info.get("pageType")
            if first_info.get('filterMaxPrice') or first_info.get('filterAirlines') or first_info.get('filterMaxStops'):
                print("-" * 50)
                print(">> ACTIVE GLOBALS FILTERS DETECTED:")
                if max_p := first_info.get('filterMaxPrice'):
                    print(f"   Max Price Slider: {max_p}")
                if airlines := first_info.get('filterAirlines'):
                    print(f"   Airlines Checked: {', '.join(airlines)}")
                if stops := first_info.get('filterMaxStops'):
                    print(f"   Stops Filter:     {stops}")
                print("-" * 50)

            limit = 10
            printed = 0
            for item in infos:
                if printed >= limit: break
                price = item.get("price", "N/A")
                
                if ptype == "flights":
                    if item.get("source") != "dom_flight_listing": continue
                    airline = item.get("airline", "Unknown").title()
                    stops_val = item.get("stops")
                    stops = "Direct" if stops_val == 0 else f"{stops_val} Stops"
                    depart = item.get("departTime", "XX:XX")
                    arrive = item.get("arrivalTime", "XX:XX")
                    print(f"  {printed+1}. {depart}-{arrive} | {airline} | {stops} | {price}", flush=True)
                    printed += 1
                    
                elif ptype in ["hotel_results", "hotels"]:
                    if item.get("source") != "dom_hotel_listing": continue
                    name = item.get("title", "Unknown")
                    score = item.get("score", "N/A")
                    stars = item.get("stars", 0)
                    print(f"  {printed+1}. {name} | {stars}★ | Rating: {score} | {price}", flush=True)
                    printed += 1
                    
                elif ptype in ["carhire_results", "carhire"]:
                    if item.get("source") != "dom_carhire_listing": continue
                    name = item.get("title", "Unknown")
                    provider = item.get("supplier", "Unknown")
                    print(f"  {printed+1}. {name} | {provider} | {price}", flush=True)
                    printed += 1

        page_type = infos[0].get("pageType", "unknown") if infos else "unknown"
        anti_bot = infos[0].get("antiBotStatus", "unknown") if infos else "unknown"

        self._all_infos.append(infos)
        
        base_url = page.url.split("?")[0]
        page_entry = {"url": page.url, "base_url": base_url, "page_type": page_type, "anti_bot": anti_bot, "infos": infos}
        
        existing_idx = next((i for i, e in enumerate(self._navigation_stack) if e["base_url"] == base_url and e["page_type"] == page_type), None)
        if existing_idx is not None:
            self._navigation_stack[existing_idx] = page_entry
        else:
            self._navigation_stack.append(page_entry)

    async def compute(self) -> FinalResult:
        # Check from newest visited page to oldest
        for page_visit in reversed(self._navigation_stack):
            if page_visit["anti_bot"] != "clear":
                continue
                
            if page_visit["page_type"] in ["flights", "hotel_results", "hotels", "carhire_results", "carhire"]:
                for i, alternative_conditions in enumerate(self.queries):
                    if self._is_query_covered[i]: continue
                    # A query is covered if ANY of the listings on this page fits the condition
                    for info in page_visit["infos"]:
                        if self._check_alternative_conditions(i, alternative_conditions, info):
                            self._is_query_covered[i] = True
                            break
        
        n_queries = len(self.queries)
        n_covered = sum(self._is_query_covered)
        return FinalResult(
            score=n_covered / max(n_queries, 1), 
            n_queries=n_queries, 
            n_covered=n_covered, 
            queries=self.queries, 
            is_query_covered=self._is_query_covered
        )

    def _check_alternative_conditions(self, i: int, alternative_conditions: list[MultiCandidateQuery], info: InfoDict) -> bool:
        for alternative_condition in alternative_conditions:
            if self._check_multi_candidate_query(alternative_condition, info):
                return True
        return False

    @classmethod
    def _check_multi_candidate_query(cls, query: MultiCandidateQuery, info: InfoDict) -> bool:
        # If the item is just a summary (not a specific flight/hotel listing), ignore
        if "summary" in str(info.get("source")): return False
        
        # === Flights ===
        if q_origins := query.get("origins"):
            info_origin = (info.get("origin") or "").lower()
            if not any(o.lower() in info_origin for o in q_origins): return False

        if q_destinations := query.get("destinations"):
            info_dest = (info.get("destination") or "").lower()
            if not any(d.lower() in info_dest for d in q_destinations): return False

        if q_depart_dates := query.get("depart_dates"):
            # depart_dates are navigational — they tell the agent WHEN to search, not what to
            # extract from listings. Individual listing cards don't expose a reliable departDate
            # field. If the info dict has a departDate, do a loose match; otherwise skip.
            dep = (info.get("departDate") or "").replace("-", "")
            if dep and not any(qd.replace("-", "") in dep for qd in q_depart_dates):
                return False

        if q_airlines := query.get("airlines"):
            ticket_airline = (info.get("airline") or "").lower()
            info_airlines = info.get("filterAirlines") or []
            
            ticket_matched = any(a.lower() in ticket_airline for a in q_airlines)
            filter_matched = any(a.lower() in ia.lower() for a in q_airlines for ia in info_airlines)
            
            if not (ticket_matched or filter_matched): 
                return False

        if q_cabin_classes := query.get("cabin_classes"):
            q_cabin_classes = query["cabin_classes"]
            q_cabin_map = {"economy": ["economy", "econ"], "business": ["business", "biz"], "first": ["first"]}
            card_info = (info.get("cabin") or "").lower()
            allowed_terms = [t for cls in q_cabin_classes for t in q_cabin_map.get(cls, [cls])]
            if not any(term in card_info for term in allowed_terms):
                return False

        if query.get("require_direct") is True:
            card_direct = info.get("stops") == 0
            if not card_direct: return False
            
        if "max_stops" in query and query["max_stops"] is not None:
            max_stops = query["max_stops"]
            card_stops = info.get("stops")
            if card_stops is None or card_stops > max_stops: return False
        
        # === Hotels ===
        if q_cities := query.get("cities"):
            # Currently the JS might not extract city easily from the hotel results unless the search box has it
            pass
            
        if "min_stars" in query and query["min_stars"] is not None:
            if info.get("stars", 0) < query["min_stars"]: return False
            
        if "min_score" in query and query["min_score"] is not None:
            score = info.get("reviewScore")
            if score is None or score < query["min_score"]: return False
            
        # === Cars ===
        if q_car_types := query.get("car_types"):
            info_title = (info.get("name") or "").lower()
            info_category = (info.get("category") or "").lower()
            
            type_matched = False
            for car_type in q_car_types:
                ct_lower = car_type.lower()
                if ct_lower in info_title or ct_lower in info_category:
                    type_matched = True
                    break
            if not type_matched: return False
            
        if "min_passengers" in query and query["min_passengers"] is not None:
            passengers = info.get("passengers")
            if passengers is None or passengers < query["min_passengers"]: return False
            
        # === Shared (Price) ===
        if "max_price" in query and query["max_price"] is not None:
            max_price = query["max_price"]
            eval_price = info.get("price")
            # For Skyscanner, flights might be shown in various currencies, but we assume the numbers match logic
            if eval_price is None or eval_price > max_price: return False
        
        if "min_price" in query and query["min_price"] is not None:
            min_price = query["min_price"]
            eval_price = info.get("price")
            if eval_price is None or eval_price < min_price: return False

        return True


def generate_info_gathering_task_config(
    mode: Literal["any", "all"],
    task: str,
    queries: list[list[MultiCandidateQuery]],
    location: str,
    timezone: str,
    timestamp: int | None = None,
    url: str = "https://www.skyscanner.net/", 
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    
    if values:
        placeholder_map, current_date = initialize_placeholder_map(user_metadata, values)
        task = render_task_statement(task, placeholder_map)
        
        # Dates are resolved into the task prompt via render_task_statement above.
        # For info-gathering, dates are navigational (they tell the agent WHEN to
        # search) — they are NOT injected into verifier queries because individual
        # listing cards don't reliably expose extractable date fields.
                        
    eval_config = {
        "_target_": get_import_path(SkyscannerInfoGathering),
        "queries": queries
    }
    
    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)
