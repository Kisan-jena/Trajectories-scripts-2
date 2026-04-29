"""Trip.com URL Match verifier for hotel search navigation.

This module provides functionality to verify AI agent navigation on Trip.com
by comparing the agent's final URL against expected ground truth URLs.

The verifier handles all Trip.com URL variations including:
- Top-level query parameters (cityId, cityName, checkin, checkout, adult,
  children, ages, crn)
- The compound `listFilters` parameter encoding sidebar filters
- Star rating (category 16)
- Price range (category 15)
- Guest rating / review score (category 6)
- Amenities / facilities (category 3)
- Breakfast / meals (category 5)
- Free cancellation (category 23)
- Property / hotel type (category 75)
- Location / area (category 9)
- Sort options (category 17)
- Filter order independence within listFilters
- Case insensitivity
- Domain variations (us.trip.com, www.trip.com)

Browser-Verified Patterns (Mar 2026 on us.trip.com):
  Top-level params:
    cityId=633, cityName=New%20York
    checkin=2026-04-01, checkout=2026-04-05
    adult=2, children=1, ages=5, crn=1
  listFilters syntax:
    CategoryID~Value*CategoryID*Value
    Multiple entries separated by comma (%2C)
  Category IDs:
    3 = Amenities (605=Pool, 42=Gym, 2=WiFi, 7=Parking, 22=Spa)
    5 = Breakfast (1=Included)
    6 = Guest Rating (7=6+, 8=7+, 9=8+, 10=9+)
    9 = Location/Area (e.g. 99665=Manhattan + geo bounding box)
    15 = Price Range (Range*15*MIN~MAX)
    16 = Star Rating (5, 4, 3, 2)
    17 = Sort (1=Recommended, 3=Lowest Price, 10=Guest Rating)
    23 = Free Cancellation (10=Free Cancellation)
    75 = Property Type (TAG_495=Hotel, TAG_496=Hostel, TAG_497=Apartment)
"""

import re
from typing import Any, TypedDict
from urllib.parse import parse_qs, unquote, urlparse

from beartype import beartype
from loguru import logger
from pydantic import BaseModel

from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import initialize_placeholder_map, initialize_user_metadata, render_task_statement


class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class TripVerifierResult(BaseModel):
    """Detailed verification result for Trip.com URL matching."""
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# ============================================================================
# CONSTANTS
# ============================================================================

# Valid Trip.com domains
VALID_DOMAINS = {
    "trip.com",
    "www.trip.com",
    "us.trip.com",
    "uk.trip.com",
    "sg.trip.com",
    "de.trip.com",
    "jp.trip.com",
    "kr.trip.com",
    "hk.trip.com",
    "au.trip.com",
}

# Query parameters to IGNORE during comparison (session/UI state, not
# user-intentional search filters)
IGNORED_PARAMS = {
    "locale",
    "curr",
    "display",
    "subStamp",
    "isCT",
    "isFlexible",
    "isFirstEnterDetail",
    "isRightClick",
    "flexType",
    "fixedDate",
    "hotelType",           # default type flag, not user filter
    "countryId",           # auto-set from city
    "provinceId",          # auto-set from city
    "destName",            # auto-set display name
    "paymentChannel",
    "sessionId",
    "from",
    "source",
    "selectedHotelId",
    "recmd",
}

# ─────────────────────────────────────────────────────────────
# listFilters category IDs → human-readable names
# ─────────────────────────────────────────────────────────────
CATEGORY_NAMES = {
    "3":  "amenities",
    "5":  "breakfast",
    "6":  "guest_rating",
    "9":  "location_area",
    "15": "price",
    "16": "star_rating",
    "17": "sort",
    "23": "cancellation",
    "75": "property_type",
}

# Known amenity IDs → names (for logging / debugging)
# Browser-verified against us.trip.com listFilters (Mar 2026)
AMENITY_IDS = {
    "102":    "free_wifi",
    "656001": "parking",
    "147":    "restaurant",
    "65":     "spa",
    "42":     "gym",
    "103":    "airport_shuttle",
    "104":    "pet_friendly",
    "605":    "pool",
}

# Known sort IDs
SORT_IDS = {
    "1":  "recommended",
    "3":  "lowest_price",
    "6":  "distance",
    "7":  "star_rating",
    "10": "guest_rating",
}

# Known property type tag IDs
PROPERTY_TYPE_TAGS = {
    "495": "hotel",
    "496": "hostel",
    "497": "apartment",
    "498": "villa",
    "499": "resort",
    "500": "guesthouse",
}


# ============================================================================
# VERIFIER CLASS
# ============================================================================


@beartype
class TripUrlMatch(BaseMetric):
    """
    Comprehensive Trip.com URL verifier with robust handling of all URL patterns.

    Browser-Verified (Mar 2026 on us.trip.com):
    - Top-level query params: cityId, cityName, checkin, checkout, adult,
      children, ages, crn
    - Compound listFilters param for sidebar filters
    - Filter entry format: CategoryID~Value*CategoryID*Value
    - Multiple filters comma-separated inside listFilters
    - Category IDs: 3=Amenities, 5=Breakfast, 6=Rating, 9=Area, 15=Price,
      16=Star, 17=Sort, 23=Cancellation, 75=Type
    - Domain variations (us., www., uk.)
    - Extra auto-computed params (countryId, provinceId, destName) IGNORED
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
        if domain and not self._is_valid_trip_domain(domain):
            logger.debug(f"Ignoring non-Trip.com URL: {url}")
            return

        # Don't overwrite agent_url after a match is found
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

    async def compute_detailed(self) -> TripVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return TripVerifierResult(
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
    def _is_valid_trip_domain(domain: str) -> bool:
        """Check if domain is a valid Trip.com domain.

        Accepts any subdomain of trip.com (e.g. us.trip.com, www.trip.com).
        """
        domain = domain.lower()
        if domain in VALID_DOMAINS:
            return True
        # Accept any subdomain of trip.com
        if domain.endswith(".trip.com"):
            return True
        return False

    # ========================================================================
    # URL MATCHING
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """
        Check if two Trip.com URLs represent the same hotel search.
        Returns (match_bool, details_dict).
        """
        details: dict[str, Any] = {"mismatches": [], "extra_filters": []}
        try:
            agent_parts = self._parse_trip_url(agent_url)
            gt_parts = self._parse_trip_url(gt_url)

            # 1. Compare city (by cityId — the authoritative identifier)
            agent_city = agent_parts["city_id"]
            gt_city = gt_parts["city_id"]
            if gt_city:
                if not agent_city:
                    # GT requires a city but agent didn't specify one
                    details["mismatches"].append(
                        f"City ID missing in agent URL (expected '{gt_city}')"
                    )
                    return False, details
                if agent_city != gt_city:
                    details["mismatches"].append(
                        f"City ID: '{agent_city}' vs '{gt_city}'"
                    )
                    return False, details
            elif agent_city and not gt_city:
                # Agent has city but GT doesn't — fall back to name comparison
                pass

            # If one URL has cityId and the other doesn't, fall back to cityName
            if not agent_city or not gt_city:
                agent_name = agent_parts["city_name"]
                gt_name = gt_parts["city_name"]
                if gt_name and not agent_name:
                    details["mismatches"].append(
                        f"City name missing in agent URL (expected '{gt_name}')"
                    )
                    return False, details
                if agent_name and gt_name and agent_name != gt_name:
                    details["mismatches"].append(
                        f"City name: '{agent_name}' vs '{gt_name}'"
                    )
                    return False, details

            # 2. Compare dates
            for date_key in ("checkin", "checkout"):
                agent_date = agent_parts[date_key]
                gt_date = gt_parts[date_key]
                if gt_date and not agent_date:
                    details["mismatches"].append(
                        f"{date_key} missing in agent URL (expected '{gt_date}')"
                    )
                    return False, details
                if agent_date and gt_date and agent_date != gt_date:
                    details["mismatches"].append(
                        f"{date_key}: '{agent_date}' vs '{gt_date}'"
                    )
                    return False, details

            # 3. Compare guests & rooms
            for guest_key in ("adult", "children", "crn"):
                agent_val = agent_parts[guest_key]
                gt_val = gt_parts[guest_key]
                if gt_val and not agent_val:
                    details["mismatches"].append(
                        f"{guest_key} missing in agent URL (expected '{gt_val}')"
                    )
                    return False, details
                if agent_val and gt_val and agent_val != gt_val:
                    details["mismatches"].append(
                        f"{guest_key}: '{agent_val}' vs '{gt_val}'"
                    )
                    return False, details

            # Children ages comparison (order-independent)
            agent_ages = agent_parts["ages"]
            gt_ages = gt_parts["ages"]
            if gt_ages:
                if not agent_ages:
                    details["mismatches"].append(
                        f"Children ages missing in agent URL (expected {gt_ages})"
                    )
                    return False, details
                if sorted(agent_ages) != sorted(gt_ages):
                    details["mismatches"].append(
                        f"Children ages: {agent_ages} vs {gt_ages}"
                    )
                    return False, details

            # 4. Compare listFilters (sidebar filters)
            agent_filters = agent_parts["filters"]
            gt_filters = gt_parts["filters"]

            # Check all GT filters exist in agent with correct values
            for cat_id, gt_values in gt_filters.items():
                if cat_id not in agent_filters:
                    cat_name = CATEGORY_NAMES.get(cat_id, f"category_{cat_id}")
                    details["mismatches"].append(
                        f"Missing filter category {cat_name} ({cat_id}): "
                        f"expected {gt_values}"
                    )
                    return False, details

                agent_values = agent_filters[cat_id]
                if not self._filter_values_match(cat_id, agent_values, gt_values):
                    cat_name = CATEGORY_NAMES.get(cat_id, f"category_{cat_id}")
                    details["mismatches"].append(
                        f"Filter mismatch in {cat_name} ({cat_id}): "
                        f"agent={agent_values} vs expected={gt_values}"
                    )
                    return False, details

            # Extra filters from agent (noted but don't fail)
            extra_cats = set(agent_filters.keys()) - set(gt_filters.keys())
            if extra_cats:
                details["extra_filters"] = [
                    CATEGORY_NAMES.get(c, f"category_{c}") for c in extra_cats
                ]

            return True, details

        except Exception as e:
            logger.error(f"Error comparing URLs: {e}")
            details["mismatches"].append(f"Parse error: {str(e)}")
            return False, details

    # ========================================================================
    # URL PARSING
    # ========================================================================

    def _parse_trip_url(self, url: str) -> dict:
        """
        Parse a Trip.com URL into normalized components.

        Returns dict with keys:
            city_id: numeric city ID string (e.g. "633")
            city_name: display name (lowercase, e.g. "new york")
            checkin: date string YYYY-MM-DD
            checkout: date string YYYY-MM-DD
            adult: string number of adults
            children: string number of children
            ages: list of age strings
            crn: string number of rooms
            filters: dict mapping category_id → set of parsed filter entries
        """
        url = url.strip()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)

        result = {
            "city_id": "",
            "city_name": "",
            "checkin": "",
            "checkout": "",
            "adult": "",
            "children": "",
            "ages": [],
            "crn": "",
            "filters": {},  # cat_id → set of value tuples
        }

        # ── Top-level parameters ──
        result["city_id"] = self._get_param(query, "cityId", "city")
        result["city_name"] = self._get_param(query, "cityName", "cityname").lower()
        result["checkin"] = self._get_param(query, "checkin", "checkIn")
        result["checkout"] = self._get_param(query, "checkout", "checkOut")
        result["adult"] = self._get_param(query, "adult")
        result["children"] = self._get_param(query, "children")
        result["crn"] = self._get_param(query, "crn")

        # Children ages: comma-separated string → list
        ages_str = self._get_param(query, "ages")
        if ages_str:
            result["ages"] = [a.strip() for a in ages_str.split(",") if a.strip()]

        # ── Parse listFilters ──
        list_filters_raw = self._get_param(query, "listFilters")
        if list_filters_raw:
            result["filters"] = self._parse_list_filters(list_filters_raw)

        return result

    @staticmethod
    def _get_param(query: dict, *keys: str) -> str:
        """Get the first non-empty value from query dict for any of the keys.

        Trip.com sometimes uses camelCase vs lowercase, so we try
        multiple key variants.
        """
        for key in keys:
            if key in query and query[key]:
                return query[key][0]
            # Also try lowercase
            key_lower = key.lower()
            if key_lower in query and query[key_lower]:
                return query[key_lower][0]
        return ""

    def _parse_list_filters(self, raw: str) -> dict[str, set[str]]:
        """Parse the compound listFilters parameter.

        Format: CategoryID~Value*CategoryID*Value[,CategoryID~Value*...]

        Each entry follows the pattern:
            CategoryID~FilterValue*CategoryID*FilterValue

        Multiple entries are separated by commas.

        Returns dict mapping category_id → set of filter value strings.
        """
        filters: dict[str, set[str]] = {}

        # Split on comma (entries delimiter)
        entries = raw.split(",")

        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue

            parsed = self._parse_single_filter_entry(entry)
            if parsed:
                cat_id, value = parsed
                if cat_id not in filters:
                    filters[cat_id] = set()
                filters[cat_id].add(value)

        return filters

    @staticmethod
    def _parse_single_filter_entry(entry: str) -> tuple[str, str] | None:
        """Parse a single listFilters entry.

        Format: CategoryID~Value*CategoryID*Value
        Examples:
            16~5*16*5               → category="16", value="5"
            15~Range*15*0~150       → category="15", value="Range*15*0~150"
            3~605*3*605             → category="3",  value="605"
            75~TAG_495*75*495       → category="75", value="TAG_495*75*495"
            9~99665*9*99665&...     → category="9",  value="99665*9*99665..."

        Strategy: Extract the category from the first segment before ~,
        and the normalized value from the second * segment onward.
        """
        if "~" not in entry:
            return None

        # Split on first ~ to get category ID
        first_tilde = entry.index("~")
        cat_id = entry[:first_tilde].strip()

        # The rest after the tilde is the value portion
        value_portion = entry[first_tilde + 1:]

        if not cat_id or not value_portion:
            return None

        # For comparison we normalize the value
        # The format is: FilterValue*CategoryID*FilterValue
        # We extract the meaningful value from the last * segment
        # But for price (cat 15) the whole pattern is meaningful
        normalized_value = _normalize_filter_value(cat_id, value_portion)

        return cat_id, normalized_value

    # ========================================================================
    # FILTER VALUE COMPARISON
    # ========================================================================

    def _filter_values_match(
        self,
        cat_id: str,
        agent_values: set[str],
        gt_values: set[str],
    ) -> bool:
        """Compare filter values for a given category.

        For most categories, values are simple IDs that must match exactly
        (as sets — order independent).

        Special handling:
        - Price (cat 15): Range comparison with tolerance
        - Location/Area (cat 9): Compare area IDs, ignore geo coordinates
        """
        # Price range: special comparison
        if cat_id == "15":
            return self._price_ranges_match(agent_values, gt_values)

        # Location/Area: compare area IDs only (ignore geo bounding boxes)
        if cat_id == "9":
            return self._area_ids_match(agent_values, gt_values)

        # All other categories: exact set comparison
        return agent_values == gt_values

    @staticmethod
    def _price_ranges_match(agent_values: set[str], gt_values: set[str]) -> bool:
        """Compare price range filter values.

        Price values look like "0~150" or "150~300".
        We extract min/max and compare numerically.
        """
        def parse_price(val: str) -> tuple[float | None, float | None]:
            """Extract (min, max) from a price range value."""
            # Value format after normalization: "MIN~MAX"
            parts = val.split("~")
            if len(parts) != 2:
                return None, None
            try:
                pmin = float(parts[0]) if parts[0] else None
            except ValueError:
                pmin = None
            try:
                pmax = float(parts[1]) if parts[1] else None
            except ValueError:
                pmax = None
            return pmin, pmax

        # Convert to sorted lists of (min, max) tuples
        agent_ranges = sorted(
            [parse_price(v) for v in agent_values],
            key=lambda x: (x[0] or 0, x[1] or float("inf")),
        )
        gt_ranges = sorted(
            [parse_price(v) for v in gt_values],
            key=lambda x: (x[0] or 0, x[1] or float("inf")),
        )

        if len(agent_ranges) != len(gt_ranges):
            return False

        for (a_min, a_max), (g_min, g_max) in zip(agent_ranges, gt_ranges):
            if a_min != g_min or a_max != g_max:
                return False

        return True

    @staticmethod
    def _area_ids_match(agent_values: set[str], gt_values: set[str]) -> bool:
        """Compare area/location filter values.

        Area values contain area IDs plus geo coordinates.
        We only compare the area ID portion, ignoring bounding-box coords.
        """
        def extract_area_id(val: str) -> str:
            """Extract the area ID from a value like '99665*9*99665&lat1&lat2&...'"""
            # The area ID is the first numeric portion
            parts = val.split("*")
            if parts:
                # Take first segment, strip any trailing '&' and coordinates
                area_part = parts[0].split("&")[0].split("%26")[0]
                return area_part.strip()
            return val

        agent_ids = {extract_area_id(v) for v in agent_values}
        gt_ids = {extract_area_id(v) for v in gt_values}
        return agent_ids == gt_ids


# ============================================================================
# MODULE-LEVEL HELPERS
# ============================================================================


def _normalize_filter_value(cat_id: str, value_portion: str) -> str:
    """Normalize a filter value for canonical comparison.

    The raw value_portion has the form: FilterValue*CategoryID*SecondValue
    We extract the meaningful value depending on category.
    """
    # Price (cat 15): format is "Range*15*MIN~MAX"
    if cat_id == "15":
        # Extract just the MIN~MAX part
        # Pattern: Range*15*0~150  →  "0~150"
        match = re.search(r'\*\d+\*(.+)$', value_portion)
        if match:
            return match.group(1)
        return value_portion

    # Property type (cat 75): format is "TAG_495*75*495"
    if cat_id == "75":
        # Extract the numeric ID from the last *-segment
        parts = value_portion.split("*")
        if len(parts) >= 3:
            return parts[-1]
        # Fallback: extract TAG_XXX  → XXX
        tag_match = re.search(r'TAG_(\d+)', value_portion)
        if tag_match:
            return tag_match.group(1)
        return value_portion

    # Location/Area (cat 9): preserve full value for area ID extraction later
    if cat_id == "9":
        return value_portion

    # Generic: format is "VALUE*CATID*VALUE" — extract the last VALUE
    parts = value_portion.split("*")
    if len(parts) >= 3:
        return parts[-1]
    elif len(parts) == 1:
        return parts[0]

    return value_portion


# ============================================================================
# TASK CONFIG GENERATION
# ============================================================================

def generate_task_config(
    task: str,
    location: str,
    timezone: str,
    gt_url: list[str] | None = None,
    ground_truth_url: str | None = None,
    timestamp: int | None = None,
    url: str = "https://us.trip.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Trip.com URL matching.

    Accepts either ``gt_url`` (list of strings) or ``ground_truth_url``
    (single string) so that the function works both when called from
    ``instantiate()`` via benchmark CSV and when called directly.

    Args:
        task: Task description.  May contain ``{placeholder}`` tokens.
        location: User location string.
        timezone: IANA timezone string.
        gt_url: Ground-truth URL(s).
        ground_truth_url: Single GT URL (alternative to gt_url).
        timestamp: Unix timestamp.  ``None`` means "now".
        url: Starting URL.
        values: Placeholder-key → relative-date expression mapping.
                Resolved dates are substituted into *task* text and
                into ``gt_url`` strings (replacing ``{placeholder}`` tokens).
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
    # For Trip: {checkinDate} → first ISO date, {checkoutDate} → last ISO date
    rendered_gt_urls: list[str] = []
    for u in gt_url:
        rendered_u = u
        for placeholder_key, (_, dates) in resolved_placeholders.items():
            template = "{" + placeholder_key + "}"
            if template in rendered_u and dates:
                rendered_u = rendered_u.replace(template, dates[0])
        rendered_gt_urls.append(rendered_u)

    eval_target = get_import_path(TripUrlMatch)
    eval_config = {"_target_": eval_target, "gt_url": rendered_gt_urls}
    return BaseTaskConfig(
        url=url, task=rendered_task, user_metadata=user_metadata, eval_config=eval_config
    )