"""Realtor.com URL Match verifier for property search navigation.

This module provides functionality to verify AI agent navigation on Realtor.com
by comparing the agent's final URL against expected ground truth URLs.

The verifier handles all Realtor.com URL variations including:
- For-sale, rental, sold, and open house search types
- City/state and zip code locations
- Path-based filter segments (beds-3, price-500000-1000000, type-single-family-home)
- Price abbreviations (500k, 2m) and na-bounded ranges
- Property type slug normalization (20+ aliases)
- Multi-type filtering (multiple /type-* segments)
- Show-flag filters (show-open-house, show-new-construction, etc.)
- Square footage, lot size, home age, year-built, stories, garage ranges
- HOA fees, days-on-market, commute radius filters
- Filter order independence
- Case insensitivity
- Sort and pagination ignored

Browser-Verified Patterns (Feb 2026):
Search Types (live paths):
- /realestateandhomes-search/City_ST/  → for sale (WORKS)
- /apartments/City_ST/                 → rentals (WORKS)
- /realestateandhomes-search/City_ST/show-recently-sold → sold (WORKS)
- /realestateandhomes-search/City_ST/show-open-house    → open houses (WORKS)
Legacy paths (404 on live site, but still used in matching):
- /sold-homes/City_ST/   → 404 (equivalent to show-recently-sold)
- /open-houses/City_ST/  → 404 (equivalent to show-open-house)
- /rentals/City_ST/      → 404 (equivalent to /apartments/)
- /houses-for-rent/City_ST/  → 404 (equivalent to /apartments/)
Filters (all as path segments):
- /beds-3, /beds-3-4 (bed range)
- /baths-2 (min baths)
- /price-500000-1000000, /price-na-500000 (price range, na=unbounded)
- /type-single-family-home, /type-condo, /type-townhome, /type-multi-family-home
- /type-land, /type-farm, /type-mobile-home, /type-co-op
- /sqft-2000-3000 (sqft range)
- /lot-sqft-5000-10000 (lot size)
- /age-0-10, /year-built-2000-2024 (home age)
- /stories-1, /garage-2 (structure)
- /hoa-na-500 (HOA fees)
- /show-open-house, /show-recently-sold, /show-new-construction
- /show-price-reduced, /show-foreclosure, /show-pending, /show-contingent
- /sby-2 (sort, IGNORED)
- /pg-2 (pagination, IGNORED)
Filter Panel Categories (10 total):
1. Price (list price, monthly payment, price reduced, builder promotions)
2. Rooms (bedrooms, bathrooms)
3. Home Type (house, condo, townhome, multi-family, mobile, farm, land)
4. Listing Details (for sale/just sold, active/pending, existing/foreclosure/new)
5. Multimedia (open houses, 3D tours, virtual tours)
6. Time on Market (days on realtor.com)
7. Home Specs (sqft, lot size, home age, HOA, garage, stories)
8. Features (pool, waterfront, basement, gated, fireplace, etc.)
9. Views & Community (city/ocean/lake views, amenities)
10. Logistics (commute time, search radius, nearby areas)
"""

import re
from typing import TypedDict
from urllib.parse import urlparse, unquote

from beartype import beartype
from loguru import logger
from pydantic import BaseModel

from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import initialize_user_metadata


class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class RealtorVerifierResult(BaseModel):
    """Detailed verification result for Realtor.com URL matching."""
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# ============================================================================
# CONSTANTS
# ============================================================================

# Valid domains
VALID_DOMAINS = {"realtor.com", "www.realtor.com"}

# Search type base paths → canonical search type
SEARCH_TYPE_PATHS = {
    "realestateandhomes-search": "sale",
    "apartments": "rent",
    "rentals": "rent",
    "apartments-for-rent": "rent",
    "houses-for-rent": "rent",
    "sold-homes": "sold",
    "open-houses": "open_houses",
    "realestateandhomes-detail": "detail",  # Individual listing (reject)
}

# Property type slug aliases → canonical slug
PROPERTY_TYPE_ALIASES = {
    # Canonical slugs (as seen in live URLs)
    "single-family-home": "single-family-home",
    "condo": "condo",
    "townhome": "townhome",
    "multi-family-home": "multi-family-home",
    "land": "land",
    "farm": "farm",
    "mobile-home": "mobile-home",
    "co-op": "co-op",
    # Common aliases
    "house": "single-family-home",
    "houses": "single-family-home",
    "single-family": "single-family-home",
    "sfh": "single-family-home",
    "single_family_home": "single-family-home",
    "condos": "condo",
    "condominium": "condo",
    "condominiums": "condo",
    "townhomes": "townhome",
    "townhouse": "townhome",
    "townhouses": "townhome",
    "multi-family": "multi-family-home",
    "multifamily": "multi-family-home",
    "multi_family": "multi-family-home",
    "multi_family_home": "multi-family-home",
    "lot": "land",
    "lots": "land",
    "lots-land": "land",
    "farms": "farm",
    "ranch": "farm",
    "ranches": "farm",
    "mobile": "mobile-home",
    "mobile_home": "mobile-home",
    "manufactured": "mobile-home",
    "coop": "co-op",
    "co_op": "co-op",
    "cooperative": "co-op",
    # Rental type plurals (browser-verified: /apartments/ URLs auto-pluralize)
    "apartment": "apartments",
    "apartments": "apartments",
}

# Show-flag aliases -> canonical flag
SHOW_FLAG_ALIASES = {
    "show-open-house": "open-house",
    "show-open-houses": "open-house",
    "show-openhouse": "open-house",
    "show-recently-sold": "recently-sold",
    "show-sold": "recently-sold",
    "show-new-construction": "new-construction",
    "show-new-homes": "new-construction",
    "show-price-reduced": "price-reduced",
    "show-price-drop": "price-reduced",
    "show-foreclosure": "foreclosure",
    "show-foreclosures": "foreclosure",
    "show-pending": "pending",
    "show-contingent": "contingent",
    "show-55-plus": "55-plus",
    "show-virtual-tours": "virtual-tours",
    "show-3d-tours": "3d-tours",
    "show-garage": "garage",
    "show-basement": "basement",
    "show-pool": "pool",
    "show-waterfront": "waterfront",
    "show-single-story": "single-story",
}

# Realtor.com abbreviated show-flag segments (browser-verified Feb 2026)
# These do NOT start with "show-" but map to the same canonical flags.
SHOW_ABBREV_ALIASES = {
    "shw-nc": "new-construction",       # shw-nc -> new construction (verified: 104 results)
    "shw-rs": "recently-sold",          # abbreviated recently-sold
    "shw-oh": "open-house",             # abbreviated open-house
    "shw-fc": "foreclosure",            # abbreviated foreclosure
    "shw-pr": "price-reduced",          # abbreviated price-reduced
}

# Soldwithin month aliases -> days (Realtor uses months internally)
SOLDWITHIN_MONTH_TO_DAYS = {
    "1": "30",    # 1 month  = 30 days
    "3": "90",    # 3 months = 90 days
    "6": "180",   # 6 months = 180 days
    "12": "365",  # 12 months = 365 days
    "24": "730",  # 24 months = 730 days
    "36": "1095", # 36 months = 1095 days
}

# Segments to IGNORE during comparison (UI state, not search filters)
IGNORED_SEGMENTS = {"sby", "pg"}

# BUG-2 fix: Removed dead RENTAL_PATH_ALIASES (was never referenced; SEARCH_TYPE_PATHS handles it)

# ============================================================================
# VERIFIER CLASS
# ============================================================================


@beartype
class RealtorUrlMatch(BaseMetric):
    """
    Comprehensive Realtor.com URL verifier with robust handling of all URL patterns.

    Browser-Verified (Feb 2026):
    - Path-based filters: /beds-3/price-500000-1000000/type-single-family-home
    - For-sale base: /realestateandhomes-search/City_ST/
    - Rentals base: /apartments/City_ST/ (only working rental path)
    - Sold: /show-recently-sold flag (legacy /sold-homes/ returns 404)
    - Open houses: /show-open-house flag (legacy /open-houses/ returns 404)
    - Price: /price-MIN-MAX with na for unbounded
    - Property types: /type-slug (slug normalized via 20+ aliases)
    - Show flags: open-house, recently-sold, new-construction, foreclosure, pending, contingent
    - Advanced: sqft, lot, age, year-built, stories, garage, hoa
    - Sort (/sby-*) and pagination (/pg-*) IGNORED

    Equivalence Handling:
    - /sold-homes/City_ST ↔ /realestateandhomes-search/City_ST/show-recently-sold
    - /open-houses/City_ST ↔ /realestateandhomes-search/City_ST/show-open-house
    - /rentals/City_ST ↔ /apartments/City_ST
    - /houses-for-rent/City_ST ↔ /apartments/City_ST
    - /apartments-for-rent/City_ST ↔ /apartments/City_ST
    """

    def __init__(self, gt_urls: list[list[str]]) -> None:
        """
        Args:
            gt_urls: list of list of strings, each string is a URL. The two levels of lists are
                for "AND" -> "OR" checking logic, i.e., all the elements in the first level of the list
                need to be covered, and at least one of the elements in the second level of each list
                need to be covered.
        """
        super().__init__()
        self.gt_urls = gt_urls
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details = {}

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
        if domain and domain not in VALID_DOMAINS:
            logger.debug(f"Ignoring non-Realtor URL: {url}")
            return

        # BUG-1 fix: Don't overwrite agent_url after a match is found
        if self._found_match:
            return

        self._agent_url = url

        for gt_url_group in self.gt_urls:
            for gt_url in gt_url_group:
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

    async def compute_detailed(self) -> RealtorVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return RealtorVerifierResult(
            score=score,
            match=self._found_match,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

    # ========================================================================
    # URL MATCHING
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """
        Check if two Realtor.com URLs represent the same search.
        Returns (match_bool, details_dict).
        """
        details = {"mismatches": [], "extra_filters": []}
        try:
            agent_parts = self._parse_realtor_url(agent_url)
            gt_parts = self._parse_realtor_url(gt_url)

            # 1. Compare search type (sale vs rent vs sold vs open_houses)
            if agent_parts["search_type"] != gt_parts["search_type"]:
                # --- Sold equivalence ---
                # /sold-homes/City <-> /realestateandhomes-search/City/show-recently-sold
                # Also: soldwithin-N filter implies sold search type
                agent_is_sold = (
                    agent_parts["search_type"] == "sale"
                    and (agent_parts["filters"].get("show-recently-sold") == "true"
                         or "sold-within" in agent_parts["filters"])
                )
                gt_is_sold = (
                    gt_parts["search_type"] == "sale"
                    and (gt_parts["filters"].get("show-recently-sold") == "true"
                         or "sold-within" in gt_parts["filters"])
                )
                sold_match = (
                    (agent_parts["search_type"] == "sold" and gt_is_sold)
                    or (gt_parts["search_type"] == "sold" and agent_is_sold)
                    # Both are "sale" type but both have sold indicators
                    or (agent_is_sold and gt_is_sold)
                )

                # --- Open houses equivalence ---
                # /open-houses/City ↔ /realestateandhomes-search/City/show-open-house
                agent_is_open = (
                    agent_parts["search_type"] == "sale"
                    and agent_parts["filters"].get("show-open-house") == "true"
                )
                gt_is_open = (
                    gt_parts["search_type"] == "sale"
                    and gt_parts["filters"].get("show-open-house") == "true"
                )
                open_match = (
                    (agent_parts["search_type"] == "open_houses" and gt_is_open)
                    or (gt_parts["search_type"] == "open_houses" and agent_is_open)
                )

                if not (sold_match or open_match):
                    details["mismatches"].append(
                        f"Search type: '{agent_parts['search_type']}' vs '{gt_parts['search_type']}'"
                    )
                    return False, details

            # 2. Compare location
            if agent_parts["location"] != gt_parts["location"]:
                details["mismatches"].append(
                    f"Location: '{agent_parts['location']}' vs '{gt_parts['location']}'"
                )
                return False, details

            # 3. Compare filters (order-independent)
            agent_filters = agent_parts["filters"]
            gt_filters = gt_parts["filters"]

            # Remove equivalence flags from filter comparison
            # (these are already handled by search_type matching above)
            equiv_flags = set()
            if agent_parts["search_type"] == "sold" or gt_parts["search_type"] == "sold":
                equiv_flags.add("show-recently-sold")
            if agent_parts["search_type"] == "open_houses" or gt_parts["search_type"] == "open_houses":
                equiv_flags.add("show-open-house")

            # Strip redundant type-apartments for rental URLs
            # When path is /apartments/ (search_type=rent), type=apartments is implicit
            agent_f = {k: v for k, v in agent_filters.items() if k not in equiv_flags}
            gt_f = {k: v for k, v in gt_filters.items() if k not in equiv_flags}
            if agent_parts["search_type"] == "rent":
                agent_f = {k: v for k, v in agent_f.items() if not (k == "type" and v == "apartments")}
            if gt_parts["search_type"] == "rent":
                gt_f = {k: v for k, v in gt_f.items() if not (k == "type" and v == "apartments")}

            # Check all GT filters exist in agent with correct values
            for key, gt_val in gt_f.items():
                if key not in agent_f:
                    details["mismatches"].append(f"Missing filter: {key}={gt_val}")
                    return False, details
                agent_val = agent_f[key]
                if not self._filter_values_match(key, agent_val, gt_val):
                    details["mismatches"].append(
                        f"Filter value mismatch: {key}: '{agent_val}' vs '{gt_val}'"
                    )
                    return False, details

            # Check for extra filters in agent (note but don't fail)
            extra = set(agent_f.keys()) - set(gt_f.keys())
            if extra:
                details["extra_filters"] = list(extra)

            return True, details

        except Exception as e:
            logger.error(f"Error comparing URLs: {e}")
            details["mismatches"].append(f"Parse error: {str(e)}")
            return False, details

    # ========================================================================
    # URL PARSING
    # ========================================================================

    def _parse_realtor_url(self, url: str) -> dict:
        """
        Parse a Realtor.com URL into normalized components.

        Returns dict with keys:
            search_type: "sale", "rent", "sold", "open_houses"
            location: normalized location string (lowercase)
            filters: dict of canonical filter key → value
        """
        url = url.strip().lower()
        url = unquote(url)

        # Parse URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        path = parsed.path.strip("/")

        result = {
            "search_type": "sale",
            "location": "",
            "filters": {},
        }

        # Split path into segments
        segments = [s for s in path.split("/") if s]

        if not segments:
            return result

        # 1. Detect search type from first segment
        first_seg = segments[0]
        if first_seg in SEARCH_TYPE_PATHS:
            result["search_type"] = SEARCH_TYPE_PATHS[first_seg]
            segments = segments[1:]
        else:
            result["search_type"] = "sale"

        if not segments:
            return result

        # 2. Extract location (next segment, should be City_ST or zip code)
        location_seg = segments[0]
        # A location segment should NOT look like a filter (beds-3, type-condo, etc.)
        if not self._is_filter_segment(location_seg):
            result["location"] = self._normalize_location(location_seg)
            segments = segments[1:]

        if not segments:
            return result

        # 3. Parse remaining segments as filters
        for seg in segments:
            # BUG-11 fix: pet-friendly expands to both dog-friendly + cat-friendly
            if seg.lower().strip() == "pet-friendly":
                result["filters"]["dog-friendly"] = "true"
                result["filters"]["cat-friendly"] = "true"
                continue

            key, value = self._parse_filter_segment(seg)
            if key:
                # Handle multiple type-* segments (merge into set)
                if key == "type" and "type" in result["filters"]:
                    existing = set(result["filters"]["type"].split(","))
                    new = set(value.split(","))
                    merged = sorted(existing | new)
                    result["filters"]["type"] = ",".join(merged)
                # Handle multiple features-* segments (merge codes)
                elif key == "features" and "features" in result["filters"]:
                    existing = result["filters"]["features"]
                    # Sort concatenated feature codes for order-independent comparison
                    merged_codes = "".join(sorted(set(
                        [existing[i:i+2] for i in range(0, len(existing), 2)] +
                        [value[i:i+2] for i in range(0, len(value), 2)]
                    )))
                    result["filters"]["features"] = merged_codes
                else:
                    result["filters"][key] = value

        return result

    def _is_filter_segment(self, seg: str) -> bool:
        """Check if a path segment looks like a filter (not a location)."""
        filter_prefixes = (
            "beds-", "baths-", "price-", "type-", "sqft-",
            "show-", "shw-", "sby-", "pg-", "lot-", "age-", "year-built-",
            "garage-", "stories-", "hoa-", "radius-",
            "dom-", "days-", "commute-",
            "sold-within-", "soldwithin-",  # both hyphenated and non-hyphenated
            "features-",  # community amenities: features-cs (pool), features-gy (gym)
            "with_",      # unit amenities: with_inunitlaundry
        )
        # Also check for standalone known rental filters
        rental_filters = {
            "dog-friendly", "cat-friendly", "pet-friendly",
            "laundry", "dishwasher", "parking", "furnished",
            "income-restricted", "senior-living", "short-term",
        }
        return any(seg.startswith(p) for p in filter_prefixes) or seg in rental_filters or seg in SHOW_ABBREV_ALIASES

    def _normalize_location(self, location: str) -> str:
        """
        Normalize a location string for comparison.
        Handles: City_ST, zip codes, multi-word cities (New-York_NY).
        """
        location = location.lower().strip()
        # BUG-7 fix: URL-decoded spaces (%20) should become hyphens for matching
        location = location.replace(" ", "-")
        return location

    def _parse_filter_segment(self, seg: str) -> tuple[str, str]:
        """
        Parse a single URL path segment into a (key, value) filter pair.

        Examples:
            "beds-3"                  → ("beds", "3")
            "beds-3-4"                → ("beds", "3-4")
            "price-500000-1000000"    → ("price", "500000-1000000")
            "price-na-500000"         → ("price", "na-500000")
            "type-single-family-home" → ("type", "single-family-home")
            "show-open-house"         → ("show-open-house", "true")
            "sqft-2000-3000"          → ("sqft", "2000-3000")
            "sby-2"                   → (ignored, returns ("", ""))
            "pg-3"                    → (ignored, returns ("", ""))
        """
        seg = seg.lower().strip()

        if not seg:
            return "", ""

        # 1. Ignored segments (sort, pagination)
        for ignored in IGNORED_SEGMENTS:
            if seg.startswith(f"{ignored}-"):
                return "", ""

        # 2a. Abbreviated show-flags: shw-nc -> show-new-construction
        if seg in SHOW_ABBREV_ALIASES:
            canonical = SHOW_ABBREV_ALIASES[seg]
            return f"show-{canonical}", "true"

        # 2b. Show-flag segments: show-open-house -> boolean filter
        if seg.startswith("show-"):
            canonical = SHOW_FLAG_ALIASES.get(seg, seg.replace("show-", ""))
            return f"show-{canonical}", "true"

        # 3. Type segments: type-single-family-home or type-townhome,condo
        if seg.startswith("type-"):
            raw_type = seg[5:]  # Remove "type-" prefix
            # Handle comma-separated types: type-townhome,condo
            if "," in raw_type:
                parts = [self._normalize_property_type(t.strip()) for t in raw_type.split(",")]
                return "type", ",".join(sorted(parts))
            canonical_type = self._normalize_property_type(raw_type)
            return "type", canonical_type

        # 4. Price segments: price-MIN-MAX
        if seg.startswith("price-"):
            raw_price = seg[6:]  # Remove "price-" prefix
            return "price", self._normalize_price_value(raw_price)

        # 5. Beds segments: beds-3 or beds-3-4
        if seg.startswith("beds-"):
            raw_beds = seg[5:]
            return "beds", raw_beds

        # 6. Baths segments: baths-2
        if seg.startswith("baths-"):
            raw_baths = seg[6:]
            return "baths", raw_baths

        # 7. Sqft segments: sqft-2000 or sqft-2000-3000
        if seg.startswith("sqft-"):
            raw_sqft = seg[5:]
            return "sqft", self._normalize_numeric_range(raw_sqft)

        # 8. Lot size segments: lot-sqft-2500-10000 or lot-0.25-1
        if seg.startswith("lot-"):
            raw_lot = seg[4:]
            # BUG-6 fix: strip "sqft-" subprefix (lot-sqft-5000-na → 5000-na)
            if raw_lot.startswith("sqft-"):
                raw_lot = raw_lot[5:]
            return "lot", raw_lot

        # 9. Age segments: age-0-5 or age-5-20
        if seg.startswith("age-"):
            raw_age = seg[4:]
            return "age", raw_age

        # 10. Year-built segments: year-built-1990-2010
        if seg.startswith("year-built-"):
            raw_year = seg[11:]
            return "year-built", raw_year

        # 11. Stories segments: stories-1 or stories-1-2
        if seg.startswith("stories-"):
            raw_stories = seg[8:]
            return "stories", raw_stories

        # 12. Garage segments: garage-1
        if seg.startswith("garage-"):
            raw_garage = seg[7:]
            return "garage", raw_garage

        # 13. HOA segments: hoa-na-500, hoa-0-500, or hoa-500,known (Realtor abbreviation)
        if seg.startswith("hoa-"):
            raw_hoa = seg[4:]
            # Handle hoa-N,known format (Realtor abbreviation for "HOA up to $N")
            # hoa-500,known -> hoa-na-500 (means "HOA max $500, known HOA only")
            if ",known" in raw_hoa:
                amount = raw_hoa.replace(",known", "")
                return "hoa", f"na-{amount}"
            return "hoa", self._normalize_price_value(raw_hoa)

        # 14. Days on market: dom-7 or days-7
        if seg.startswith("dom-") or seg.startswith("days-"):
            prefix_len = 4 if seg.startswith("dom-") else 5
            raw_dom = seg[prefix_len:]
            return "days-on-market", raw_dom

        # 15. Radius/commute segments
        if seg.startswith("radius-") or seg.startswith("commute-"):
            prefix = "radius-" if seg.startswith("radius-") else "commute-"
            raw_val = seg[len(prefix):]
            return prefix.rstrip("-"), raw_val

        # 16a. Sold-within segments: sold-within-7, sold-within-30, etc.
        if seg.startswith("sold-within-"):
            raw_days = seg[12:]  # Remove "sold-within-" prefix
            return "sold-within", raw_days

        # 16b. Soldwithin-N (no hyphen, month-based): soldwithin-1 = 30 days
        if seg.startswith("soldwithin-"):
            raw_months = seg[11:]  # Remove "soldwithin-" prefix
            days = SOLDWITHIN_MONTH_TO_DAYS.get(raw_months, raw_months)
            return "sold-within", days

        # 17. Rental community amenity segments: features-cs, features-gy, etc.
        if seg.startswith("features-"):
            raw_features = seg[9:]  # Remove "features-" prefix
            return "features", raw_features

        # 18. Rental unit amenity segments: with_inunitlaundry, etc.
        if seg.startswith("with_"):
            return seg, "true"

        # 19. Standalone rental pet/amenity filters (no prefix)
        standalone_filters = {
            "dog-friendly", "cat-friendly",
            "laundry", "dishwasher", "parking", "furnished",
            "income-restricted", "senior-living", "short-term",
        }
        # BUG-11 fix: pet-friendly → expand to dog-friendly + cat-friendly
        if seg == "pet-friendly":
            return "dog-friendly", "true"  # First part; cat-friendly added below
        if seg in standalone_filters:
            return seg, "true"

        # Unknown segment — still record it
        logger.debug(f"Unknown filter segment: {seg}")
        return seg, "true"

    # ========================================================================
    # NORMALIZATION
    # ========================================================================

    def _normalize_property_type(self, raw_type: str) -> str:
        """
        Normalize a property type slug to canonical form.
        Handles both canonical slugs and common aliases.
        """
        raw_type = raw_type.lower().strip()
        return PROPERTY_TYPE_ALIASES.get(raw_type, raw_type)

    def _normalize_price_value(self, raw: str) -> str:
        """
        Normalize a price range value.

        Handles:
        - "500000-1000000" → "500000-1000000"
        - "na-500000" → "na-500000"
        - "500000-na" → "500000-na"
        - "500k-1m" → "500000-1000000"
        - "2,000,000" → "2000000"
        """
        raw = raw.strip().lower().replace(",", "").replace("$", "")

        # Split on first hyphen that isn't part of "na"
        # Price format is MIN-MAX, where either can be "na"
        parts = self._split_price_range(raw)

        if len(parts) == 2:
            left = self._expand_price_abbrev(parts[0]) if parts[0] != "na" else "na"
            right = self._expand_price_abbrev(parts[1]) if parts[1] != "na" else "na"
            return f"{left}-{right}"

        # Single value (shouldn't happen for price, but handle gracefully)
        return self._expand_price_abbrev(raw)

    def _split_price_range(self, raw: str) -> list[str]:
        """
        Split a price range string like "500000-1000000" or "na-500000".

        The tricky part is that "na" contains no further hyphens, but
        "500000-1000000" needs to split on the hyphen between numbers.
        """
        # Handle "na-*" prefix
        if raw.startswith("na-"):
            return ["na", raw[3:]]

        # Handle "*-na" suffix
        if raw.endswith("-na"):
            return [raw[:-3], "na"]

        # Split on the hyphen between two numeric values
        # We need to find the hyphen that separates min from max
        # For values like "500000-1000000", simple split works
        # For values like "1.5m-2m", we split carefully
        match = re.match(r'^([0-9]+(?:\.[0-9]+)?[km]?)-([0-9]+(?:\.[0-9]+)?[km]?)$', raw)
        if match:
            return [match.group(1), match.group(2)]

        # If no range detected, return as single value
        return [raw]

    def _expand_price_abbrev(self, val: str) -> str:
        """Expand price abbreviation: 500k → 500000, 2m → 2000000."""
        val = val.strip()
        if not val:
            return val
        if val == "na":
            return "na"
        if val.endswith("m"):
            try:
                return str(int(float(val[:-1]) * 1_000_000))
            except ValueError:
                return val
        if val.endswith("k"):
            try:
                return str(int(float(val[:-1]) * 1_000))
            except ValueError:
                return val
        # Strip any remaining commas and convert
        val = val.replace(",", "")
        try:
            return str(int(float(val)))
        except ValueError:
            return val

    def _normalize_numeric_range(self, raw: str) -> str:
        """Normalize a numeric range value (sqft, lot, etc.)."""
        raw = raw.strip().replace(",", "")
        return raw

    def _normalize_range_value(self, val: str, prefix: str = "", suffix: str = "") -> str:
        """
        Normalize a range value for comparison, handling:
        - Single value ↔ range equivalence
        - suffix='na': '2500' → '2500-na' (sqft/lot: "at least N")
        - prefix='0': '10' → '0-10' (age: "within N years")
        """
        val = val.strip().replace(",", "")
        # If already a range (contains hyphen), return as-is
        if "-" in val:
            return val
        # Single numeric value: expand to range
        try:
            int(val)
            if prefix:
                return f"{prefix}-{val}"
            elif suffix:
                return f"{val}-{suffix}"
            return val
        except ValueError:
            return val

    def _filter_values_match(self, key: str, agent_val: str, gt_val: str) -> bool:
        """
        Compare two filter values, accounting for:
        - Multi-value type comparison (order independent)
        - Price normalization (abbreviations)
        - Boolean equivalence
        - na equivalence
        """
        if agent_val == gt_val:
            return True

        # Multi-value comparison (type: condo,single-family-home vs single-family-home,condo)
        if key == "type":
            agent_set = set(agent_val.split(","))
            gt_set = set(gt_val.split(","))
            return agent_set == gt_set

         # Price comparison: normalize both and compare
        if key == "price":
            # BUG-8 fix: handle single-value price (price-500000 -> price-500000-na)
            a_price = self._normalize_price_value(agent_val)
            g_price = self._normalize_price_value(gt_val)
            if a_price == g_price:
                return True
            # Single value → range: "500000" means "at least 500000" → "500000-na"
            a_range = self._normalize_range_value(a_price, suffix="na")
            g_range = self._normalize_range_value(g_price, suffix="na")
            return a_range == g_range

        # HOA comparison: normalize both and compare
        if key == "hoa":
            return self._normalize_price_value(agent_val) == self._normalize_price_value(gt_val)

        # Range filters: handle single-value ↔ range equivalence
        # sqft/lot: single value N means "at least N" → N-na
        # age: single value N means "built within N years" → 0-N
        # BUG-5 fix: features subset check (agent csgy ⊇ GT cs → match)
        if key == "features":
            agent_codes = {agent_val[i:i+2] for i in range(0, len(agent_val), 2)}
            gt_codes = {gt_val[i:i+2] for i in range(0, len(gt_val), 2)}
            return gt_codes.issubset(agent_codes)

        if key in ("sqft", "lot"):
            a_norm = self._normalize_range_value(agent_val, suffix="na")
            g_norm = self._normalize_range_value(gt_val, suffix="na")
            if a_norm == g_norm:
                return True

        if key == "age":
            a_norm = self._normalize_range_value(agent_val, prefix="0")
            g_norm = self._normalize_range_value(gt_val, prefix="0")
            if a_norm == g_norm:
                return True

        # Boolean equivalence
        bool_true = {"true", "1", "yes", "on"}
        if agent_val in bool_true and gt_val in bool_true:
            return True

        return False


# ============================================================================
# TASK CONFIG GENERATION
# ============================================================================

def generate_task_config(
    task: str,
    gt_urls: list[list[str]],
    location: str,
    timezone: str,
    timestamp: int | None = None,
    url: str = "https://www.realtor.com",
) -> BaseTaskConfig:
    """Generate task configuration for Realtor.com URL matching."""
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    eval_target = get_import_path(RealtorUrlMatch)
    eval_config = {"_target_": eval_target, "gt_urls": gt_urls}
    return BaseTaskConfig(
        url=url, task=task, user_metadata=user_metadata, eval_config=eval_config
    )




