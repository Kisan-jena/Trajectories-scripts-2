"""Swappa URL Match verifier for used tech marketplace navigation.

This module provides functionality to verify AI agent navigation on Swappa
by comparing the agent's final URL against expected ground truth URLs.

Swappa uses a **product-catalog** URL architecture with:
- Product overview: /buy/{brand}-{model}
- Listings page: /listings/{brand}-{model}?filters
- Category browse: /buy/{category}

The verifier handles all Swappa URL variations including:
- Product page path:  /buy/apple-iphone-15
- Listings page path: /listings/apple-iphone-15
- Carrier filter:     ?carrier=unlocked|att|tmobile|verizon|...
- Condition filter:   ?condition=new|mint|good|fair
- Storage filter:     ?storage=128gb|256gb|512gb|1tb
- Color filter:       ?color=black|blue|purple|gold|silver|...
- Sort order:         ?sort=price_low|price_high|listing_created_newest|listing_created_oldest
- Model filter:       ?model=<model_slug>  (for multi-model pages)
- Model number:       ?modeln=<base64_encoded>  (base64-encoded model, e.g. A2848)
- Edition filter:     ?edition=<base64_encoded>  (base64-encoded edition, e.g. mmWave 5G)
- Memory filter:      ?memory=16gb|24gb  (for laptops)
- Processor filter:   ?processor=apple-m2|...  (for laptops)
- Checkboxes:         ?exclude_businesses=on|&accepts_stripe=on|&international=on|&phone_check_certified=on

Browser-Verified CLICKABLE Filters (May 2026 on swappa.com):
  Left sidebar (desktop):
    Conditions: All Conditions | New | Mint | Good | Fair
    Carriers:   All Carriers | Unlocked | AT&T | T-Mobile | Verizon | ...
    Colors:     All Colors | Black | Blue | Purple | Gold | Silver | ...
    Storages:   All Storages | 128 GB | 256 GB | 512 GB | 1 TB
    Models:     All Models | (device-specific sub-models)
    Sort By:    Sort By | Price (Low) | Price (High) | Listing Created (Newest) | Listing Created (Oldest)

  Checkboxes:
    One-Year Warranty | Accepts Credit Cards | Exclude Businesses |
    PhoneCheck Certified | International Shipping

URL Transition Pattern:
  /buy/{slug}  →  product overview (carrier+storage grid)
  /listings/{slug}  →  filterable listings with sidebar filters
  Clicking carrier/storage on /buy/ page → redirects to /listings/{slug}?carrier=...
"""

import re
from typing import Any
from typing_extensions import TypedDict
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


class SwappaVerifierResult(BaseModel):
    """Detailed verification result for Swappa URL matching."""

    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid Swappa domain patterns
VALID_BASE_DOMAINS = {
    "swappa.com",
    "www.swappa.com",
}

# Carrier normalization: aliases → canonical slug
CARRIER_MAP = {
    # Canonical slugs (as they appear in URLs)
    "unlocked": "unlocked",
    "att": "att",
    "tmobile": "tmobile",
    "t-mobile": "tmobile",
    "verizon": "verizon",
    "sprint": "sprint",
    "boost": "boost",
    "cricket": "cricket",
    "mint": "mint",
    "mint-mobile": "mint",
    "mint_mobile": "mint",
    "mintmobile": "mint",
    "us-cellular": "us-cellular",
    "us_cellular": "us-cellular",
    "uscellular": "us-cellular",
    "c-spire": "c-spire",
    "c_spire": "c-spire",
    "cspire": "c-spire",
    "unlocked-non-us": "unlocked-non-us",
    "unlocked_non_us": "unlocked-non-us",
    "xfinity": "xfinity",
    "xfinity-mobile": "xfinity-mobile",
    "spectrum": "spectrum",
    "straight-talk": "straight-talk",
    "straight_talk": "straight-talk",
    "metro": "metro",
    "metro-by-t-mobile": "metro",
    "google-fi": "google-fi",
    "google_fi": "google-fi",
    "googlefi": "google-fi",
    "visible": "visible",
    "total-wireless": "total-wireless",
    "at-t": "att",
    "consumer-cellular": "consumer-cellular",
    "consumer_cellular": "consumer-cellular",
    "consumercellular": "consumer-cellular",
    "red-pocket": "red-pocket",
    "red_pocket": "red-pocket",
    "tracfone": "tracfone",
    "trac-fone": "tracfone",
}

# Condition normalization
CONDITION_MAP = {
    "new": "new",
    "mint": "mint",
    "good": "good",
    "fair": "fair",
    # Common agent aliases
    "like_new": "mint",
    "like new": "mint",
    "excellent": "mint",
    "used": "good",
    "acceptable": "fair",
}

# Sort order normalization
# Canonical values match actual Swappa URL params.
SORT_MAP = {
    # Canonical slugs (as they appear in Swappa URLs)
    "price_low": "price_low",
    "price_high": "price_high",
    "listing_created_newest": "listing_created_newest",
    "listing_created_oldest": "listing_created_oldest",
    # Aliases — Price (Low)
    "price_asc": "price_low",
    "price_ascending": "price_low",
    "price low to high": "price_low",
    "price: low to high": "price_low",
    "lowest_price": "price_low",
    "lowest price": "price_low",
    "cheapest": "price_low",
    "cheapest first": "price_low",
    "price (low)": "price_low",
    "price_min": "price_low",
    # Aliases — Price (High)
    "price_desc": "price_high",
    "price_descending": "price_high",
    "price high to low": "price_high",
    "price: high to low": "price_high",
    "highest_price": "price_high",
    "highest price": "price_high",
    "most expensive": "price_high",
    "price (high)": "price_high",
    "price_max": "price_high",
    # Aliases — Listing Created (Newest)
    "newest": "listing_created_newest",
    "newest_first": "listing_created_newest",
    "newest first": "listing_created_newest",
    "most_recent": "listing_created_newest",
    "most recent": "listing_created_newest",
    "recent": "listing_created_newest",
    "date": "listing_created_newest",
    "listing created (newest)": "listing_created_newest",
    # Aliases — Listing Created (Oldest)
    "oldest": "listing_created_oldest",
    "oldest_first": "listing_created_oldest",
    "oldest first": "listing_created_oldest",
    "least_recent": "listing_created_oldest",
    "listing created (oldest)": "listing_created_oldest",
}

# Color normalization: aliases -> canonical slug
COLOR_MAP = {
    # Standard colors (as they appear in Swappa URLs)
    "black": "black",
    "blue": "blue",
    "green": "green",
    "pink": "pink",
    "yellow": "yellow",
    "white": "white",
    "red": "red",
    "purple": "purple",
    "gold": "gold",
    "silver": "silver",
    "gray": "gray",
    "grey": "gray",
    "natural-titanium": "natural-titanium",
    "natural_titanium": "natural-titanium",
    "blue-titanium": "blue-titanium",
    "blue_titanium": "blue-titanium",
    "black-titanium": "black-titanium",
    "black_titanium": "black-titanium",
    "white-titanium": "white-titanium",
    "white_titanium": "white-titanium",
    "desert-titanium": "desert-titanium",
    "desert_titanium": "desert-titanium",
    "titanium-black": "black-titanium",
    "titanium-blue": "blue-titanium",
    "titanium-natural": "natural-titanium",
    "titanium-white": "white-titanium",
    "titanium-desert": "desert-titanium",
    # Samsung-specific colors
    "phantom-black": "phantom-black",
    "phantom_black": "phantom-black",
    "cream": "cream",
    "lavender": "lavender",
    "graphite": "graphite",
    # Space-prefixed colors
    "space-black": "space-black",
    "space_black": "space-black",
    "space-gray": "space-gray",
    "space_gray": "space-gray",
    # Other common aliases
    "midnight": "midnight",
    "starlight": "starlight",
    "coral": "coral",
    "rose-gold": "rose-gold",
    "rose_gold": "rose-gold",
    "rosegold": "rose-gold",
}

# Storage normalization
STORAGE_MAP = {
    "128gb": "128gb",
    "128 gb": "128gb",
    "128": "128gb",
    "256gb": "256gb",
    "256 gb": "256gb",
    "256": "256gb",
    "512gb": "512gb",
    "512 gb": "512gb",
    "512": "512gb",
    "1tb": "1tb",
    "1 tb": "1tb",
    "1024gb": "1tb",
    "1024 gb": "1tb",
    "2tb": "2tb",
    "2 tb": "2tb",
    "64gb": "64gb",
    "64 gb": "64gb",
    "64": "64gb",
    "32gb": "32gb",
    "32 gb": "32gb",
    "32": "32gb",
    "24gb": "24gb",
    "24 gb": "24gb",
    "24": "24gb",
    "16gb": "16gb",
    "16 gb": "16gb",
    "16": "16gb",
    "8gb": "8gb",
    "8 gb": "8gb",
}


# =============================================================================
# PARSING HELPERS
# =============================================================================


def _get_param(query: dict, *keys: str) -> str:
    """Get the first non-empty value from query dict for any of the keys."""
    for key in keys:
        if key in query and query[key]:
            return query[key][0]
        key_lower = key.lower()
        if key_lower in query and query[key_lower]:
            return query[key_lower][0]
    return ""


def _normalize_slug(slug: str) -> str:
    """Normalize a product slug for comparison.

    - Lowercase
    - Strip leading/trailing slashes and whitespace
    - Collapse multiple hyphens
    """
    if not slug:
        return ""
    slug = unquote(slug).strip().lower().strip("/")
    slug = re.sub(r"-+", "-", slug)
    return slug


def _normalize_carrier(raw: str) -> str:
    """Normalize carrier to canonical slug."""
    if not raw:
        return ""
    return CARRIER_MAP.get(raw.lower().strip(), raw.lower().strip())


def _normalize_condition(raw: str) -> str:
    """Normalize condition to canonical value."""
    if not raw:
        return ""
    return CONDITION_MAP.get(raw.lower().strip(), raw.lower().strip())


def _normalize_sort(raw: str) -> str:
    """Normalize sort order to canonical value."""
    if not raw:
        return ""
    return SORT_MAP.get(raw.lower().strip(), raw.lower().strip())


def _normalize_storage(raw: str) -> str:
    """Normalize storage to canonical value."""
    if not raw:
        return ""
    return STORAGE_MAP.get(raw.lower().strip(), raw.lower().strip())


def _normalize_color(raw: str) -> str:
    """Normalize color to canonical slug via COLOR_MAP, with fallback."""
    if not raw:
        return ""
    key = raw.lower().strip().replace(" ", "-")
    return COLOR_MAP.get(key, key)


def _extract_product_slug(path: str) -> str:
    """Extract the product slug from a Swappa URL path.

    /buy/apple-iphone-15 → "apple-iphone-15"
    /listings/apple-iphone-15 → "apple-iphone-15"
    /buy/samsung-galaxy-s24 → "samsung-galaxy-s24"

    Returns empty string if no product slug found.
    """
    if not path:
        return ""

    path = path.strip("/")

    # Pattern: /buy/{slug} or /listings/{slug}
    m = re.match(r"^(?:buy|listings)/(.+)$", path, re.IGNORECASE)
    if m:
        slug = m.group(1).strip("/")
        # Strip trailing carrier segment from path.
        # e.g., /buy/apple-iphone-15/unlocked → "apple-iphone-15"
        # But keep full slugs like "apple-iphone-15-pro-max"
        parts = slug.split("/")
        if len(parts) > 1 and parts[-1].lower() in CARRIER_MAP:
            slug = "/".join(parts[:-1])
        return _normalize_slug(slug)

    return ""


def _extract_carrier_from_path(path: str) -> str:
    """Extract carrier from URL path if present.

    /buy/apple-iphone-15/unlocked → "unlocked"
    /buy/unlocked/iphones → "unlocked"
    /listings/apple-iphone-15 → "" (no carrier in path)

    Returns empty string if no carrier found in path.
    """
    if not path:
        return ""

    path = path.strip("/").lower()

    # Pattern: /buy/{product}/{carrier}
    m = re.match(r"^buy/[^/]+/([^/]+)$", path)
    if m:
        candidate = m.group(1)
        if candidate in CARRIER_MAP:
            return CARRIER_MAP[candidate]

    # Pattern: /buy/{carrier}/{category}
    m = re.match(r"^buy/([^/]+)/", path)
    if m:
        candidate = m.group(1)
        if candidate in CARRIER_MAP:
            return CARRIER_MAP[candidate]

    return ""


# =============================================================================
# URL PARSER
# =============================================================================


def parse_swappa_url(url: str) -> dict[str, Any]:
    """Parse a Swappa URL into normalized components.

    Returns dict with keys:
      product_slug, carrier, condition, storage, color, sort, model,
      modeln, edition, memory, processor,
      exclude_businesses, accepts_stripe, international, phone_check_certified
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    path = (parsed.path or "").strip("/")

    result: dict[str, Any] = {
        # Product identification
        "product_slug": "",
        # Filters
        "carrier": "",
        "condition": "",
        "storage": "",
        "color": "",
        "sort": "",
        "model": "",
        # Extended filters (new CSV params)
        "modeln": "",       # base64-encoded model number (e.g. A2848)
        "edition": "",      # base64-encoded edition (e.g. mmWave 5G)
        "memory": "",       # RAM for laptops (e.g. 16gb, 24gb)
        "processor": "",    # CPU for laptops (e.g. apple-m2)
        # Checkbox filters
        "exclude_businesses": "",
        "accepts_stripe": "",
        "international": "",
        "phone_check_certified": "",
        # Page type
        "page_type": "",  # "buy" | "listings" | "other"
    }

    # Determine page type
    if path.startswith("buy/") or path == "buy":
        result["page_type"] = "buy"
    elif path.startswith("listings/") or path == "listings":
        result["page_type"] = "listings"
    else:
        result["page_type"] = "other"

    # Extract product slug
    result["product_slug"] = _extract_product_slug(path)

    # Carrier: check query param first, then path
    raw_carrier = _get_param(query, "carrier")
    if raw_carrier:
        result["carrier"] = _normalize_carrier(raw_carrier)
    else:
        result["carrier"] = _extract_carrier_from_path(path)

    # Condition
    raw_condition = _get_param(query, "condition")
    result["condition"] = _normalize_condition(raw_condition)

    # Storage
    raw_storage = _get_param(query, "storage")
    result["storage"] = _normalize_storage(raw_storage)

    # Color
    raw_color = _get_param(query, "color")
    result["color"] = _normalize_color(raw_color)

    # Sort
    raw_sort = _get_param(query, "sort")
    result["sort"] = _normalize_sort(raw_sort)

    # Model (sub-model filter for multi-model pages)
    result["model"] = _get_param(query, "model").lower().strip()

    # Extended filters — base64-encoded params (case-sensitive, exact match)
    result["modeln"] = _get_param(query, "modeln")
    result["edition"] = _get_param(query, "edition")

    # Laptop-specific filters
    result["memory"] = _normalize_storage(_get_param(query, "memory"))
    result["processor"] = _get_param(query, "processor").lower().strip()

    # Checkbox filters (value is always "on" or absent)
    result["exclude_businesses"] = _get_param(query, "exclude_businesses")
    result["accepts_stripe"] = _get_param(query, "accepts_stripe")
    result["international"] = _get_param(query, "international")
    result["phone_check_certified"] = _get_param(query, "phone_check_certified")

    return result


# =============================================================================
# VERIFIER CLASS
# =============================================================================


@beartype
class SwappaUrlMatch(BaseMetric):
    """Comprehensive Swappa URL verifier for product/listing navigation tasks.

    Browser-Verified (May 2026 on swappa.com):
    - Product overview:  /buy/{brand}-{model}
    - Listings page:     /listings/{brand}-{model}?filters
    - Category browse:   /buy/{category}

    Matching Rules (hardened — no auto-pass loopholes):
    - If GT specifies a field and agent omits it → FAIL
    - Product slug: case-insensitive, hyphen-normalized
    - Carrier: alias-normalized exact match
    - Condition: alias-normalized exact match
    - Storage: alias-normalized exact match
    - Color: case-insensitive exact match
    - Sort: alias-normalized exact match
    - /buy/ and /listings/ pages are treated equivalently for product slug
    - modeln/edition: case-sensitive exact match (base64 values)
    - memory/processor: normalized exact match
    - Checkboxes (exclude_businesses, accepts_stripe, international,
      phone_check_certified): exact match on 'on'
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
        if domain and not self._is_valid_swappa_domain(domain):
            logger.debug(f"Ignoring non-Swappa URL: {url}")
            return

        # Must be a buy or listings page (not individual listing view)
        path = (parsed.path or "").lower()
        if "/listing/view/" in path:
            logger.debug(f"Ignoring individual listing URL: {url}")
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

    async def compute_detailed(self) -> SwappaVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return SwappaVerifierResult(
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
    def _is_valid_swappa_domain(domain: str) -> bool:
        """Check if domain is a valid Swappa domain.

        Accepts:
        - Exact matches: swappa.com, www.swappa.com
        - Any subdomain of swappa.com
        """
        domain = domain.lower().rstrip(".")

        # Direct match on known domains
        for base in VALID_BASE_DOMAINS:
            if domain == base:
                return True

        # Any subdomain of swappa.com
        if domain.endswith(".swappa.com"):
            return True

        return False

    # ========================================================================
    # URL MATCHING
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Compare two Swappa URLs.

        Performs sequential field comparison. Returns (match, details).
        If any required field mismatches, returns False immediately with
        mismatch details.
        """
        details: dict[str, Any] = {"mismatches": [], "extra_params": []}

        try:
            agent = parse_swappa_url(agent_url)
            gt = parse_swappa_url(gt_url)

            # 1. Product slug (case-insensitive, hyphen-normalized)
            if gt["product_slug"]:
                if not agent["product_slug"]:
                    details["mismatches"].append(
                        f"Product slug missing (expected '{gt['product_slug']}')"
                    )
                    return False, details
                # Compare slugs: allow /buy/ vs /listings/ equivalence
                # _extract_product_slug already strips the prefix, so compare directly
                gt_slug = re.sub(r"^(buy|listings)/", "", gt["product_slug"])
                agent_slug = re.sub(r"^(buy|listings)/", "", agent["product_slug"])
                if agent_slug != gt_slug:
                    details["mismatches"].append(
                        f"Product slug: '{agent_slug}' vs '{gt_slug}'"
                    )
                    return False, details

            # 2. Carrier
            if gt["carrier"]:
                if not agent["carrier"]:
                    details["mismatches"].append(
                        f"Carrier missing (expected '{gt['carrier']}')"
                    )
                    return False, details
                if agent["carrier"] != gt["carrier"]:
                    details["mismatches"].append(
                        f"Carrier: '{agent['carrier']}' vs '{gt['carrier']}'"
                    )
                    return False, details

            # 3. Condition
            if gt["condition"]:
                if not agent["condition"]:
                    details["mismatches"].append(
                        f"Condition missing (expected '{gt['condition']}')"
                    )
                    return False, details
                if agent["condition"] != gt["condition"]:
                    details["mismatches"].append(
                        f"Condition: '{agent['condition']}' vs '{gt['condition']}'"
                    )
                    return False, details

            # 4. Storage
            if gt["storage"]:
                if not agent["storage"]:
                    details["mismatches"].append(
                        f"Storage missing (expected '{gt['storage']}')"
                    )
                    return False, details
                if agent["storage"] != gt["storage"]:
                    details["mismatches"].append(
                        f"Storage: '{agent['storage']}' vs '{gt['storage']}'"
                    )
                    return False, details

            # 5. Color
            if gt["color"]:
                if not agent["color"]:
                    details["mismatches"].append(
                        f"Color missing (expected '{gt['color']}')"
                    )
                    return False, details
                if agent["color"] != gt["color"]:
                    details["mismatches"].append(
                        f"Color: '{agent['color']}' vs '{gt['color']}'"
                    )
                    return False, details

            # 6. Sort order
            if gt["sort"]:
                if not agent["sort"]:
                    details["mismatches"].append(
                        f"Sort order missing (expected '{gt['sort']}')"
                    )
                    return False, details
                if agent["sort"] != gt["sort"]:
                    details["mismatches"].append(
                        f"Sort order: '{agent['sort']}' vs '{gt['sort']}'"
                    )
                    return False, details

            # 7. Model (sub-model)
            if gt["model"]:
                if not agent["model"]:
                    details["mismatches"].append(
                        f"Model missing (expected '{gt['model']}')"
                    )
                    return False, details
                if agent["model"] != gt["model"]:
                    details["mismatches"].append(
                        f"Model: '{agent['model']}' vs '{gt['model']}'"
                    )
                    return False, details

            # 8. Model number (base64-encoded, case-sensitive)
            if gt["modeln"]:
                if not agent["modeln"]:
                    details["mismatches"].append(
                        f"Model number missing (expected '{gt['modeln']}')"
                    )
                    return False, details
                if agent["modeln"] != gt["modeln"]:
                    details["mismatches"].append(
                        f"Model number: '{agent['modeln']}' vs '{gt['modeln']}'"
                    )
                    return False, details

            # 9. Edition (base64-encoded, case-sensitive)
            if gt["edition"]:
                if not agent["edition"]:
                    details["mismatches"].append(
                        f"Edition missing (expected '{gt['edition']}')"
                    )
                    return False, details
                if agent["edition"] != gt["edition"]:
                    details["mismatches"].append(
                        f"Edition: '{agent['edition']}' vs '{gt['edition']}'"
                    )
                    return False, details

            # 10. Memory (for laptops)
            if gt["memory"]:
                if not agent["memory"]:
                    details["mismatches"].append(
                        f"Memory missing (expected '{gt['memory']}')"
                    )
                    return False, details
                if agent["memory"] != gt["memory"]:
                    details["mismatches"].append(
                        f"Memory: '{agent['memory']}' vs '{gt['memory']}'"
                    )
                    return False, details

            # 11. Processor (for laptops)
            if gt["processor"]:
                if not agent["processor"]:
                    details["mismatches"].append(
                        f"Processor missing (expected '{gt['processor']}')"
                    )
                    return False, details
                if agent["processor"] != gt["processor"]:
                    details["mismatches"].append(
                        f"Processor: '{agent['processor']}' vs '{gt['processor']}'"
                    )
                    return False, details

            # 12-15. Checkbox filters (exact "on" match)
            for checkbox_field in [
                "exclude_businesses",
                "accepts_stripe",
                "international",
                "phone_check_certified",
            ]:
                if gt[checkbox_field]:
                    if not agent[checkbox_field]:
                        details["mismatches"].append(
                            f"{checkbox_field} missing (expected '{gt[checkbox_field]}')"
                        )
                        return False, details
                    if agent[checkbox_field] != gt[checkbox_field]:
                        details["mismatches"].append(
                            f"{checkbox_field}: '{agent[checkbox_field]}' vs '{gt[checkbox_field]}'"
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
    url: str = "https://swappa.com/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Swappa URL matching.

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

    # Substitute resolved dates into gt_url strings
    rendered_gt_urls: list[str] = []
    for u in gt_url:
        rendered_u = u
        for placeholder_key, (_, dates) in resolved_placeholders.items():
            template = "{" + placeholder_key + "}"
            if template in rendered_u and dates:
                rendered_u = rendered_u.replace(template, dates[0])
        rendered_gt_urls.append(rendered_u)

    eval_target = get_import_path(SwappaUrlMatch)
    eval_config = {"_target_": eval_target, "gt_url": rendered_gt_urls}
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
        "task_id": "navi_bench/swappa/product_navigation/0",
        "task_generation_config_json": json.dumps(
            {
                "_target_": "navi_bench.swappa.swappa_url_match.generate_task_config",
                "url": "https://swappa.com/",
                "task": (
                    "Find the Apple iPhone 15 Pro Max on Swappa. Show me the "
                    "unlocked 256GB listings in mint condition, sorted by "
                    "lowest price first."
                ),
                "location": "New York, NY, United States",
                "timezone": "America/New_York",
                "gt_url": [
                    "https://swappa.com/listings/apple-iphone-15-pro-max"
                    "?carrier=unlocked&storage=256gb&condition=mint&sort=price_low"
                ],
            }
        ),
        "env": "real",
        "domain": "swappa",
        "l1_category": "e_commerce",
        "l2_category": "product_navigation",
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
