"""Hotels.com URL Match verifier for hotel search navigation.

This module provides functionality to verify AI agent navigation on Hotels.com
by comparing the agent's final URL against expected ground truth URLs.

Hotels.com is part of the Expedia Group and uses the SAME URL structure as
Expedia for hotel searches. This is a URL-BASED verifier — all search state
is encoded in the URL query parameters, not in the DOM.

The verifier handles all Hotels.com URL variations including:
- Search results path: /Hotel-Search?destination=...&startDate=...&endDate=...
- Destination: destination=New%20York (URL-encoded city name)
- Region ID: regionId=2621 (numeric internal area identifier)
- Check-in / Check-out: startDate=YYYY-MM-DD, endDate=YYYY-MM-DD
  Alternative params: d1, d2, checkIn, checkOut (all normalized)
- Adults: adults=2 (single room) or adults=2,1,1 (multi-room, comma-separated)
- Rooms: rooms=1 (number of rooms)
- Children: children=1_5,1_10 (RoomIndex_Age format, comma-separated)
  Alternative: childrenAges=5,10 (legacy format)
- Sort: sort=RECOMMENDED|PRICE_LOW_TO_HIGH|PRICE_HIGH_TO_LOW|DISTANCE|REVIEW
         |GUEST_RATING|STAR_RATING_HIGHEST_FIRST
- Star rating filter: f-star-rating=4,5 (comma-separated star levels)
- Price filter: f-price-min=50, f-price-max=200 (in dollars, NOT cents)
- Amenities filter: f-amenities=WIFI,POOL,FREE_BREAKFAST (comma-separated codes)
- Guest rating filter: f-guest-rating=8 (minimum rating threshold)
- Payment type: paymentType=FREE_CANCELLATION|PAY_LATER

Browser-Verified CLICKABLE Filters (Jun 2026 on hotels.com):
  Search bar (top):
    destination, startDate, endDate, adults, rooms, children
  Filter pills / sidebar:
    sort, f-star-rating, f-price, f-amenities, f-guest-rating, paymentType

Note: Hotels.com is an Expedia Group property. Its URL structure is nearly
identical to expedia.com/Hotel-Search. Prices are in DOLLARS (not cents).
"""

import re
from datetime import datetime
from itertools import product
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


class HotelsComVerifierResult(BaseModel):
    """Detailed verification result for Hotels.com URL matching."""

    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid Hotels.com domain patterns
VALID_BASE_DOMAINS = {
    "hotels.com",
    "www.hotels.com",
}

# Regional / localized domains (Hotels.com serves many country variants)
REGIONAL_DOMAINS = {
    "in.hotels.com",      # India
    "uk.hotels.com",      # United Kingdom
    "de.hotels.com",      # Germany
    "fr.hotels.com",      # France
    "es.hotels.com",      # Spain
    "it.hotels.com",      # Italy
    "jp.hotels.com",      # Japan
    "kr.hotels.com",      # South Korea
    "au.hotels.com",      # Australia
    "ca.hotels.com",      # Canada
    "mx.hotels.com",      # Mexico
    "br.hotels.com",      # Brazil
    "ar.hotels.com",      # Argentina
    "sg.hotels.com",      # Singapore
    "hk.hotels.com",      # Hong Kong
    "tw.hotels.com",      # Taiwan
    "nz.hotels.com",      # New Zealand
    "se.hotels.com",      # Sweden
    "no.hotels.com",      # Norway
    "dk.hotels.com",      # Denmark
    "fi.hotels.com",      # Finland
    "ie.hotels.com",      # Ireland
    "at.hotels.com",      # Austria
    "ch.hotels.com",      # Switzerland
    "nl.hotels.com",      # Netherlands
    "za.hotels.com",      # South Africa
    "my.hotels.com",      # Malaysia
    "ph.hotels.com",      # Philippines
    "th.hotels.com",      # Thailand
    "id.hotels.com",      # Indonesia
}

# Sort normalization mapping (browser-verified Jun 2026)
SORT_MAP = {
    # Canonical uppercase values (pass through)
    "RECOMMENDED": "RECOMMENDED",
    "PRICE_LOW_TO_HIGH": "PRICE_LOW_TO_HIGH",
    "PRICE_HIGH_TO_LOW": "PRICE_HIGH_TO_LOW",
    "DISTANCE": "DISTANCE",
    "DISTANCE_FROM_LANDMARK": "DISTANCE_FROM_LANDMARK",
    "REVIEW": "REVIEW",
    "GUEST_RATING": "GUEST_RATING",
    "STAR_RATING_HIGHEST_FIRST": "STAR_RATING_HIGHEST_FIRST",
    # Lowercase aliases
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
    # Common aliases an agent might use
    "lowest_price": "PRICE_LOW_TO_HIGH",
    "cheapest": "PRICE_LOW_TO_HIGH",
    "highest_price": "PRICE_HIGH_TO_LOW",
    "most_expensive": "PRICE_HIGH_TO_LOW",
    "closest": "DISTANCE",
    "best_reviewed": "REVIEW",
    "top_rated": "GUEST_RATING",
    "stars": "STAR_RATING_HIGHEST_FIRST",
}

# Query parameters to IGNORE during comparison (tracking, session, UI state)
IGNORED_PARAMS = {
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
    "pos",
    "referrerUrl",
}


# =============================================================================
# PARSING HELPERS
# =============================================================================


def _get_param(query: dict, *keys: str) -> str:
    """Get the first non-empty value from query dict for any of the keys.

    Handles both exact keys and case-insensitive fallback.
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

    Handles multiple Hotels.com date formats:
      - YYYY-MM-DD (standard — most common)
      - YYYY-M-D   (e.g., 2026-7-1 — from d1/d2 params)
      - M/D/YYYY   (e.g., 7/1/2026 — legacy format)
    """
    if not date_str:
        return ""

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


def _normalize_sort(raw: str) -> str:
    """Normalize sort order to canonical uppercase value."""
    if not raw:
        return ""
    raw_clean = raw.strip()
    # Try direct lookup
    if raw_clean in SORT_MAP:
        return SORT_MAP[raw_clean]
    # Try lowercase
    raw_lower = raw_clean.lower().replace(" ", "_")
    return SORT_MAP.get(raw_lower, raw_clean.upper())


def _normalize_destination(raw: str) -> str:
    """Normalize a destination string for comparison.

    - URL-decode
    - Lowercase
    - Take only the city part (before first comma)
    - Strip whitespace
    """
    if not raw:
        return ""
    decoded = unquote(raw).strip().lower()
    # Take only the city part (e.g., "New York, New York, United States" → "new york")
    return decoded.split(",")[0].strip()


def _parse_star_rating(raw: str) -> list[str]:
    """Parse star rating filter into sorted list of values.

    Input: "4,5" or "3,4,5" (comma-separated)
    Output: ["4", "5"] or ["3", "4", "5"]
    """
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return sorted(parts)


def _parse_amenities(raw: str) -> list[str]:
    """Parse amenities filter into sorted list of values.

    Input: "WIFI,POOL,FREE_BREAKFAST" (comma-separated)
    Output: ["FREE_BREAKFAST", "POOL", "WIFI"]
    """
    if not raw:
        return []
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    return sorted(parts)


# =============================================================================
# URL PARSER
# =============================================================================


def parse_hotels_com_url(url: str) -> dict[str, Any]:
    """Parse a Hotels.com Hotel-Search URL into normalized components.

    Browser-verified Hotel URL anatomy (Jun 2026):
      /Hotel-Search?destination=New%20York%2C%20New%20York%2C%20United%20States
        &regionId=2621
        &startDate=2026-07-01&endDate=2026-07-05
        &adults=2
        &rooms=1
        &sort=RECOMMENDED
        [&children=1_5,1_10]  (RoomIndex_Age format)
        [&f-star-rating=4,5]
        [&paymentType=FREE_CANCELLATION]

    Returns dict with keys:
      destination, region_id, start_date, end_date,
      adults, rooms, children, children_ages, sort,
      star_rating, price_min, price_max, amenities,
      guest_rating, payment_type
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)

    # --- Children parsing ---
    # Format A (browser-verified): children=1_5,1_10 (RoomIndex_Age)
    # Format B (legacy): childrenAges=5,10 (comma-separated)
    children_raw = _get_param(query, "children")
    children_ages_raw = _get_param(
        query, "childrenAges", "children_ages", "childrenAge"
    )

    children_count = ""
    children_ages: list[str] = []

    if children_raw and "_" in children_raw:
        # Browser-verified RoomIndex_Age format: children=1_5,1_10
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
        # Legacy format: childrenAges=5,10
        children_ages = sorted(
            [a.strip() for a in children_ages_raw.split(",") if a.strip()]
        )
        children_count = _get_param(query, "children") or str(len(children_ages))
    elif children_raw:
        # Plain count without ages (e.g., children=2)
        children_count = children_raw

    # --- Adults (multi-room support) ---
    # adults=2 (single room) or adults=2,1,1 (multi-room: 2+1+1=4 total, 3 rooms)
    adults_raw = _get_param(query, "adults")
    if adults_raw and "," in adults_raw:
        adult_parts = [a.strip() for a in adults_raw.split(",") if a.strip()]
        adults_total = str(sum(int(a) for a in adult_parts if a.isdigit()))
        rooms_from_adults = str(len(adult_parts))
    else:
        adults_total = adults_raw
        rooms_from_adults = ""

    rooms_raw = _get_param(query, "rooms")
    rooms = (
        rooms_from_adults
        if rooms_from_adults and int(rooms_from_adults) > 1
        else rooms_raw
    )

    # --- Dates ---
    start_date = _normalize_date(
        _get_param(query, "startDate", "start_date", "checkIn", "checkin", "d1")
    )
    end_date = _normalize_date(
        _get_param(query, "endDate", "end_date", "checkOut", "checkout", "d2")
    )

    # --- Filters ---
    # Star rating: f-star-rating=4,5
    star_raw = _get_param(query, "f-star-rating", "star")
    star_rating = _parse_star_rating(star_raw)

    # Price range (in dollars)
    price_min_raw = _get_param(query, "f-price-min", "price_min")
    price_max_raw = _get_param(query, "f-price-max", "price_max")
    price_min = int(price_min_raw) if price_min_raw and price_min_raw.isdigit() else None
    price_max = int(price_max_raw) if price_max_raw and price_max_raw.isdigit() else None

    # Amenities: f-amenities=WIFI,POOL
    amenities_raw = _get_param(query, "f-amenities", "amenities")
    amenities = _parse_amenities(amenities_raw)

    # Guest rating: f-guest-rating=8
    guest_rating = _get_param(query, "f-guest-rating", "guest_rating")

    # Payment type: paymentType=FREE_CANCELLATION
    payment_type = _get_param(
        query, "paymentType", "payment_type", "f-payment-type"
    ).upper() if _get_param(query, "paymentType", "payment_type", "f-payment-type") else ""

    return {
        "destination": _normalize_destination(
            _get_param(query, "destination")
        ),
        "region_id": _get_param(query, "regionId", "region_id"),
        "start_date": start_date,
        "end_date": end_date,
        "adults": adults_total,
        "rooms": rooms,
        "children": children_count,
        "children_ages": children_ages,
        "sort": _normalize_sort(_get_param(query, "sort")),
        "star_rating": star_rating,
        "price_min": price_min,
        "price_max": price_max,
        "amenities": amenities,
        "guest_rating": guest_rating,
        "payment_type": payment_type,
    }


# =============================================================================
# VERIFIER CLASS
# =============================================================================


@beartype
class HotelsComUrlMatch(BaseMetric):
    """URL-based Hotels.com verifier for hotel search tasks.

    This is a URL-BASED verifier. Hotels.com encodes ALL search state in URL
    query parameters. No DOM parsing is needed — the URL alone contains the
    complete search specification.

    Browser-Verified (Jun 2026 on hotels.com):
    - Search path: /Hotel-Search
    - Core params: destination, startDate, endDate, adults, rooms
    - Sort: sort=RECOMMENDED|PRICE_LOW_TO_HIGH|PRICE_HIGH_TO_LOW|DISTANCE|REVIEW
    - Filters: f-star-rating, f-price-min, f-price-max, f-amenities, f-guest-rating
    - Payment: paymentType=FREE_CANCELLATION|PAY_LATER
    - Children: children=RoomIdx_Age (e.g., 1_5,1_10)
    - Domain: hotels.com, www.hotels.com, *.hotels.com (regional)

    Matching Rules:
    - If GT specifies a field and agent omits it → FAIL
    - If GT omits a field → agent value is ignored (pass)
    - Destination: case-insensitive, city-part only (before first comma)
    - Dates: normalized to YYYY-MM-DD, exact match
    - Sort: alias-normalized exact match
    - Star rating: sorted-set equality (order-independent)
    - Amenities: sorted-set equality
    - Price: exact integer match (in dollars)
    - Children ages: sorted-list equality
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

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(gt_urls={self.gt_urls})"

    async def reset(self) -> None:
        """Reset the match state for new evaluation."""
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details = {}

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
        if domain and not self._is_valid_hotels_com_domain(domain):
            logger.debug(f"Ignoring non-Hotels.com URL: {url}")
            return

        # Must be a Hotel-Search URL
        path = (parsed.path or "").lower()
        if "hotel-search" not in path:
            logger.debug(f"Ignoring non-search URL: {url}")
            return

        # Don't overwrite after match
        if self._found_match:
            return

        self._agent_url = url

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

    async def compute_detailed(self) -> HotelsComVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return HotelsComVerifierResult(
            score=score,
            match=self._found_match,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

    # ========================================================================
    # DOMAIN VALIDATION
    # ========================================================================

    @staticmethod
    def _is_valid_hotels_com_domain(domain: str) -> bool:
        """Check if domain is a valid Hotels.com domain.

        Accepts:
        - Exact matches: hotels.com, www.hotels.com
        - Regional subdomains: in.hotels.com, uk.hotels.com, etc.
        - Any subdomain of hotels.com
        """
        domain = domain.lower().rstrip(".")

        # Direct match on known domains
        for base in VALID_BASE_DOMAINS:
            if domain == base:
                return True

        # Known regional domains
        for regional in REGIONAL_DOMAINS:
            if domain == regional:
                return True

        # Any subdomain of hotels.com
        if domain.endswith(".hotels.com"):
            return True

        return False

    # ========================================================================
    # URL MATCHING
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Compare two Hotels.com URLs.

        Performs sequential field comparison. Returns (match, details).
        If any required field mismatches, returns False immediately with
        mismatch details.
        """
        details: dict[str, Any] = {"mismatches": []}

        try:
            agent = parse_hotels_com_url(agent_url)
            gt = parse_hotels_com_url(gt_url)

            # 1. Destination (case-insensitive, city-part only)
            if gt["destination"]:
                if not agent["destination"]:
                    details["mismatches"].append(
                        f"Destination missing (expected '{gt['destination']}')"
                    )
                    return False, details
                if agent["destination"] != gt["destination"]:
                    details["mismatches"].append(
                        f"Destination: '{agent['destination']}' "
                        f"vs '{gt['destination']}'"
                    )
                    return False, details

            # 2. Check-in date
            if gt["start_date"]:
                if not agent["start_date"]:
                    details["mismatches"].append(
                        f"Check-in date missing (expected '{gt['start_date']}')"
                    )
                    return False, details
                if agent["start_date"] != gt["start_date"]:
                    details["mismatches"].append(
                        f"Check-in: '{agent['start_date']}' "
                        f"vs '{gt['start_date']}'"
                    )
                    return False, details

            # 3. Check-out date
            if gt["end_date"]:
                if not agent["end_date"]:
                    details["mismatches"].append(
                        f"Check-out date missing (expected '{gt['end_date']}')"
                    )
                    return False, details
                if agent["end_date"] != gt["end_date"]:
                    details["mismatches"].append(
                        f"Check-out: '{agent['end_date']}' "
                        f"vs '{gt['end_date']}'"
                    )
                    return False, details

            # 4. Adults
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

            # 5. Rooms
            if gt["rooms"]:
                if not agent["rooms"]:
                    details["mismatches"].append(
                        f"Rooms missing (expected '{gt['rooms']}')"
                    )
                    return False, details
                if agent["rooms"] != gt["rooms"]:
                    details["mismatches"].append(
                        f"Rooms: '{agent['rooms']}' vs '{gt['rooms']}'"
                    )
                    return False, details

            # 6. Children count
            if gt["children"]:
                if not agent["children"]:
                    details["mismatches"].append(
                        f"Children missing (expected '{gt['children']}')"
                    )
                    return False, details
                if agent["children"] != gt["children"]:
                    details["mismatches"].append(
                        f"Children: '{agent['children']}' vs '{gt['children']}'"
                    )
                    return False, details

            # 7. Children ages (sorted list comparison)
            if gt["children_ages"]:
                if not agent["children_ages"]:
                    details["mismatches"].append(
                        f"Children ages missing (expected {gt['children_ages']})"
                    )
                    return False, details
                if agent["children_ages"] != gt["children_ages"]:
                    details["mismatches"].append(
                        f"Children ages: {agent['children_ages']} "
                        f"vs {gt['children_ages']}"
                    )
                    return False, details

            # 8. Sort order
            if gt["sort"]:
                if not agent["sort"]:
                    details["mismatches"].append(
                        f"Sort order missing (expected '{gt['sort']}')"
                    )
                    return False, details
                if agent["sort"] != gt["sort"]:
                    details["mismatches"].append(
                        f"Sort: '{agent['sort']}' vs '{gt['sort']}'"
                    )
                    return False, details

            # 9. Star rating (sorted set comparison)
            if gt["star_rating"]:
                if not agent["star_rating"]:
                    details["mismatches"].append(
                        f"Star rating missing (expected {gt['star_rating']})"
                    )
                    return False, details
                if agent["star_rating"] != gt["star_rating"]:
                    details["mismatches"].append(
                        f"Star rating: {agent['star_rating']} "
                        f"vs {gt['star_rating']}"
                    )
                    return False, details

            # 10. Price min
            if gt["price_min"] is not None:
                if agent["price_min"] is None:
                    details["mismatches"].append(
                        f"Price min missing (expected {gt['price_min']})"
                    )
                    return False, details
                if agent["price_min"] != gt["price_min"]:
                    details["mismatches"].append(
                        f"Price min: {agent['price_min']} vs {gt['price_min']}"
                    )
                    return False, details

            # 11. Price max
            if gt["price_max"] is not None:
                if agent["price_max"] is None:
                    details["mismatches"].append(
                        f"Price max missing (expected {gt['price_max']})"
                    )
                    return False, details
                if agent["price_max"] != gt["price_max"]:
                    details["mismatches"].append(
                        f"Price max: {agent['price_max']} vs {gt['price_max']}"
                    )
                    return False, details

            # 12. Amenities (sorted set comparison)
            if gt["amenities"]:
                if not agent["amenities"]:
                    details["mismatches"].append(
                        f"Amenities missing (expected {gt['amenities']})"
                    )
                    return False, details
                if agent["amenities"] != gt["amenities"]:
                    details["mismatches"].append(
                        f"Amenities: {agent['amenities']} "
                        f"vs {gt['amenities']}"
                    )
                    return False, details

            # 13. Guest rating
            if gt["guest_rating"]:
                if not agent["guest_rating"]:
                    details["mismatches"].append(
                        f"Guest rating missing (expected '{gt['guest_rating']}')"
                    )
                    return False, details
                if agent["guest_rating"] != gt["guest_rating"]:
                    details["mismatches"].append(
                        f"Guest rating: '{agent['guest_rating']}' "
                        f"vs '{gt['guest_rating']}'"
                    )
                    return False, details

            # 14. Payment type
            if gt["payment_type"]:
                if not agent["payment_type"]:
                    details["mismatches"].append(
                        f"Payment type missing (expected '{gt['payment_type']}')"
                    )
                    return False, details
                if agent["payment_type"] != gt["payment_type"]:
                    details["mismatches"].append(
                        f"Payment type: '{agent['payment_type']}' "
                        f"vs '{gt['payment_type']}'"
                    )
                    return False, details

            return True, details

        except Exception as e:
            logger.error(f"Error comparing URLs: {e}")
            details["mismatches"].append(f"Parse error: {str(e)}")
            return False, details


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
    url: str = "https://www.hotels.com/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Hotels.com URL matching.

    Accepts either ``gt_url`` (list of strings) or ``ground_truth_url``
    (single string) for backward compat. Supports multi-date placeholder
    expansion for dynamic date tasks.

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
        raise ValueError(
            "Either 'gt_url' or 'ground_truth_url' must be provided."
        )

    values = values or {}
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    resolved_placeholders, _ = initialize_placeholder_map(
        user_metadata, values
    )

    # Render {placeholder} tokens in task text
    rendered_task = render_task_statement(task, resolved_placeholders)

    # ----------------------------
    # Generate all GT URL combinations
    # ----------------------------
    all_gt_urls: list[str] = []

    for template in gt_url:
        placeholders_in_template = {
            k: dates
            for k, (_, dates) in resolved_placeholders.items()
            if any(
                token in template
                for token in [
                    f"{{{k}}}",
                    f"{{{k}Day}}",
                    f"{{{k}Month}}",
                    f"{{{k}Year}}",
                ]
            )
        }

        if not placeholders_in_template:
            all_gt_urls.append(template)
            continue

        keys = list(placeholders_in_template.keys())
        date_lists = list(placeholders_in_template.values())

        for combination in product(*date_lists):
            rendered_u = template

            for k, v in zip(keys, combination):
                rendered_u = rendered_u.replace(f"{{{k}}}", v)

                try:
                    dt = datetime.strptime(v, "%Y-%m-%d")
                    replacements = {
                        f"{{{k}Day}}": str(dt.day),
                        f"{{{k}Month}}": str(dt.month),
                        f"{{{k}Year}}": str(dt.year),
                    }
                    for token, value in replacements.items():
                        if token in rendered_u:
                            rendered_u = rendered_u.replace(token, value)
                except Exception:
                    pass

            all_gt_urls.append(rendered_u)

    all_gt_urls = list(set(all_gt_urls))

    eval_target = get_import_path(HotelsComUrlMatch)
    eval_config = {"_target_": eval_target, "gt_url": all_gt_urls}

    return BaseTaskConfig(
        url=url,
        task=rendered_task,
        user_metadata=user_metadata,
        eval_config=eval_config,
    )


# =============================================================================
# STANDALONE DEMO
# =============================================================================


if __name__ == "__main__":
    import json

    from navi_bench.base import DatasetItem, instantiate

    dataset_row = {
        "task_id": "navi_bench/hotels_com/hotel_search/0",
        "task_generation_config_json": json.dumps(
            {
                "_target_": "navi_bench.hotels_com.hotels_com_url_match.generate_task_config",
                "url": "https://www.hotels.com/",
                "task": (
                    "Search for hotels in New York for 2 adults, checking in on "
                    "July 1st 2026 and checking out on July 5th 2026. "
                    "Sort by lowest price and filter for 4-star and 5-star hotels."
                ),
                "location": "San Francisco, CA, United States",
                "timezone": "America/Los_Angeles",
                "gt_url": [
                    "https://www.hotels.com/Hotel-Search?destination=New%20York"
                    "&startDate=2026-07-01&endDate=2026-07-05"
                    "&adults=2&rooms=1"
                    "&sort=PRICE_LOW_TO_HIGH"
                    "&f-star-rating=4,5"
                ],
            }
        ),
        "env": "real",
        "domain": "hotels_com",
        "l1_category": "travel",
        "l2_category": "hotel_search",
        "suggested_split": "train",
        "suggested_difficulty": "hard",
    }

    dataset_item = DatasetItem.model_validate(dataset_row)
    task_config = dataset_item.generate_task_config()
    evaluator = instantiate(task_config.eval_config)

    print("Loaded dataset item")
    print("-------------------")
    print(dataset_item)
    print()

    print("Generated task config")
    print("---------------------")
    print(task_config)
    print()

    print("Instantiated evaluator")
    print("----------------------")
    print(evaluator)
