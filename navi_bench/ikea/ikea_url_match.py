"""IKEA US URL Match verifier for furniture/home goods navigation.

This module provides functionality to verify AI agent navigation on IKEA US
by comparing the agent's final URL against expected ground truth URLs.

IKEA US uses a **hybrid path + query parameter** URL architecture with:
- Search results:  /us/en/search/?q={keyword}&filters=...&sort=...
- Category pages:  /us/en/cat/{slug}-{id}/?filters=...&sort=...
- Product pages:   /us/en/p/{product-slug}-{article}/

The verifier handles all IKEA URL variations including:
- Search keyword:    ?q=desk
- Color filter:      filters=f-colors:{color_id}
- Price filter:      filters=f-price-buckets:{bucket_code}
- Sort order:        sort=PRICE_LOW_TO_HIGH|NEWEST|...
- Multi-filter:      filters=f-colors:10156,f-price-buckets:PRICE_0_10000

Browser-Verified CLICKABLE Filters (May 2026 on ikea.com/us/en/):
  Sort: Best match | Price: low to high | Price: high to low | Newest |
        Customer rating | Name | Most popular | Width | Height | Depth | Length
  Color: White | Black | Beige | Gray | Brown | Blue | Green | Turquoise |
         Yellow | Red | Pink | Orange | Multicolor
  Price: Category-dependent price buckets (in cents)
  Size:  Width / Height / Depth / Length range buckets
  Other: Type, Material, Features, Shape, Category, Series, Finish
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


class IkeaVerifierResult(BaseModel):
    """Detailed verification result for IKEA URL matching."""

    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid IKEA domain patterns
VALID_BASE_DOMAINS = {
    "ikea.com",
    "www.ikea.com",
}

# Color name → IKEA numeric ID mapping (browser-verified May 2026)
COLOR_MAP: dict[str, str] = {
    # Canonical names (as shown in IKEA UI)
    "white": "10156",
    "black": "10005",
    "beige": "10003",
    "gray": "10008",
    "brown": "10017",
    "blue": "10006",
    "green": "10011",
    "turquoise": "10878",
    "yellow": "10015",
    "red": "10013",
    "pink": "10012",
    "orange": "10010",
    "multicolor": "10009",
    # Common aliases → canonical IDs
    "grey": "10008",
    "cream": "10003",
    "ivory": "10003",
    "off-white": "10003",
    "off white": "10003",
    "tan": "10003",
    "khaki": "10003",
    "teal": "10878",
    "aqua": "10878",
    "cyan": "10878",
    "purple": "10006",
    "violet": "10006",
    "lilac": "10006",
    "navy": "10006",
    "dark blue": "10006",
    "gold": "10015",
    "burgundy": "10013",
    "maroon": "10013",
    "wine": "10013",
    "natural": "10017",
    "wood": "10017",
    "silver": "10008",
    "chrome": "10008",
    "stainless": "10008",
    "multi": "10009",
    "mixed": "10009",
}

# Sort normalization: aliases → canonical IKEA sort value
SORT_MAP: dict[str, str] = {
    # Canonical values (as they appear in IKEA URLs)
    "PRICE_LOW_TO_HIGH": "PRICE_LOW_TO_HIGH",
    "PRICE_HIGH_TO_LOW": "PRICE_HIGH_TO_LOW",
    "NEWEST": "NEWEST",
    "CUSTOMER_RATING": "CUSTOMER_RATING",
    "NAME_ASCENDING": "NAME_ASCENDING",
    "MOST_POPULAR": "MOST_POPULAR",
    "WIDTH": "WIDTH",
    "HEIGHT": "HEIGHT",
    "DEPTH": "DEPTH",
    "LENGTH": "LENGTH",
    # Lowercase canonical
    "price_low_to_high": "PRICE_LOW_TO_HIGH",
    "price_high_to_low": "PRICE_HIGH_TO_LOW",
    "newest": "NEWEST",
    "customer_rating": "CUSTOMER_RATING",
    "name_ascending": "NAME_ASCENDING",
    "most_popular": "MOST_POPULAR",
    "width": "WIDTH",
    "height": "HEIGHT",
    "depth": "DEPTH",
    "length": "LENGTH",
    # Common aliases — Price low
    "cheapest": "PRICE_LOW_TO_HIGH",
    "cheapest first": "PRICE_LOW_TO_HIGH",
    "price_low": "PRICE_LOW_TO_HIGH",
    "price low to high": "PRICE_LOW_TO_HIGH",
    "price: low to high": "PRICE_LOW_TO_HIGH",
    "price_asc": "PRICE_LOW_TO_HIGH",
    "price_ascending": "PRICE_LOW_TO_HIGH",
    "lowest price": "PRICE_LOW_TO_HIGH",
    "lowest_price": "PRICE_LOW_TO_HIGH",
    # Common aliases — Price high
    "most expensive": "PRICE_HIGH_TO_LOW",
    "price_high": "PRICE_HIGH_TO_LOW",
    "price high to low": "PRICE_HIGH_TO_LOW",
    "price: high to low": "PRICE_HIGH_TO_LOW",
    "price_desc": "PRICE_HIGH_TO_LOW",
    "price_descending": "PRICE_HIGH_TO_LOW",
    "highest price": "PRICE_HIGH_TO_LOW",
    "highest_price": "PRICE_HIGH_TO_LOW",
    # Common aliases — Newest
    "newest first": "NEWEST",
    "most recent": "NEWEST",
    "most_recent": "NEWEST",
    "new": "NEWEST",
    "recent": "NEWEST",
    # Common aliases — Rating
    "rating": "CUSTOMER_RATING",
    "top rated": "CUSTOMER_RATING",
    "top_rated": "CUSTOMER_RATING",
    "best rated": "CUSTOMER_RATING",
    "best_rated": "CUSTOMER_RATING",
    "reviews": "CUSTOMER_RATING",
    # Common aliases — Name
    "name": "NAME_ASCENDING",
    "alphabetical": "NAME_ASCENDING",
    "a-z": "NAME_ASCENDING",
    "a to z": "NAME_ASCENDING",
    # Common aliases — Popular
    "popular": "MOST_POPULAR",
    "popularity": "MOST_POPULAR",
    "trending": "MOST_POPULAR",
    "best seller": "MOST_POPULAR",
    "best_seller": "MOST_POPULAR",
    "bestseller": "MOST_POPULAR",
    "best match": "MOST_POPULAR",
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


def _normalize_keyword(keyword: str) -> str:
    """Normalize a search keyword for comparison.

    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse multiple spaces to single
    - URL-decode
    """
    if not keyword:
        return ""
    keyword = unquote(keyword).strip().lower()
    keyword = re.sub(r"\s+", " ", keyword)
    return keyword


def _normalize_sort(raw: str) -> str:
    """Normalize sort order to canonical IKEA value."""
    if not raw:
        return ""
    key = raw.strip()
    # Try exact match first (preserves case for canonical values)
    if key in SORT_MAP:
        return SORT_MAP[key]
    # Try lowercase
    return SORT_MAP.get(key.lower(), key.upper())


def _normalize_color(raw: str) -> str:
    """Normalize color to IKEA numeric ID.

    Accepts either a color name ('white') or numeric ID ('10156').
    """
    if not raw:
        return ""
    raw = raw.strip()
    # Already a numeric ID?
    if raw.isdigit():
        return raw
    # Look up by name
    return COLOR_MAP.get(raw.lower(), raw)


def _parse_filters(filters_str: str) -> dict[str, list[str]]:
    """Parse IKEA filters parameter into a dict.

    Input:  'f-colors:10028|10139,f-price-buckets:PRICE_0_10000'
    Output: {'f-colors': ['10028', '10139'], 'f-price-buckets': ['PRICE_0_10000']}

    Pipe-separated values within a segment (e.g. f-colors:10028|10139) are
    split into individual entries so order-independent comparison works correctly.
    """
    result: dict[str, list[str]] = {}
    if not filters_str:
        return result

    filters_str = unquote(filters_str).strip()
    for part in filters_str.split(","):
        part = part.strip()
        if ":" not in part:
            continue
        key, _, value = part.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            continue
        values = [v.strip() for v in value.split("|") if v.strip()]
        result.setdefault(key, []).extend(values)

    return result


def _extract_category_slug(path: str) -> str:
    """Extract category slug from IKEA category path.

    /us/en/cat/desks-20649/ → 'desks-20649'
    /us/en/cat/sofas-fu003/ → 'sofas-fu003'

    Returns empty string if not a category page.
    """
    if not path:
        return ""
    path = path.strip("/")
    m = re.search(r"us/en/cat/([^/]+)", path, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return ""


def _detect_page_type(path: str) -> str:
    """Detect IKEA page type from URL path.

    Returns: 'search', 'category', 'product', or 'other'
    """
    if not path:
        return "other"
    path_lower = path.lower()
    if "/us/en/search" in path_lower:
        return "search"
    if "/us/en/cat/" in path_lower:
        return "category"
    if "/us/en/p/" in path_lower:
        return "product"
    return "other"


# =============================================================================
# URL PARSER
# =============================================================================


def parse_ikea_url(url: str) -> dict[str, Any]:
    """Parse an IKEA US URL into normalized components.

    Returns dict with keys:
      page_type, keyword, category_slug, filters, sort
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    path = (parsed.path or "").strip("/")

    result: dict[str, Any] = {
        "page_type": "",
        "keyword": "",
        "category_slug": "",
        "filters": {},    # dict[str, list[str]]
        "sort": "",
    }

    # Detect page type
    result["page_type"] = _detect_page_type(parsed.path or "")

    # Extract search keyword
    if result["page_type"] == "search":
        raw_q = _get_param(query, "q", "Q")
        result["keyword"] = _normalize_keyword(raw_q)

    # Extract category slug
    if result["page_type"] == "category":
        result["category_slug"] = _extract_category_slug(parsed.path or "")

    # Parse filters
    raw_filters = _get_param(query, "filters")
    result["filters"] = _parse_filters(raw_filters)

    # Parse sort
    raw_sort = _get_param(query, "sort")
    result["sort"] = _normalize_sort(raw_sort)

    return result


# =============================================================================
# VERIFIER CLASS
# =============================================================================


@beartype
class IkeaUrlMatch(BaseMetric):
    """Comprehensive IKEA US URL verifier for search/category navigation tasks.

    Browser-Verified (May 2026 on ikea.com/us/en/):
    - Search results:  /us/en/search/?q={keyword}&filters=...&sort=...
    - Category pages:  /us/en/cat/{slug}-{id}/?filters=...&sort=...

    Matching Rules (hardened — no auto-pass loopholes):
    - If GT specifies a field and agent omits it → FAIL
    - Search keyword: case-insensitive, whitespace-normalized
    - Category slug: case-insensitive exact match
    - Filters: each f-type:value pair must match
    - Sort: alias-normalized exact match
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
        if domain and not self._is_valid_ikea_domain(domain):
            logger.debug(f"Ignoring non-IKEA URL: {url}")
            return

        # Must be search or category page (not product detail)
        page_type = _detect_page_type(parsed.path or "")
        if page_type == "product":
            logger.debug(f"Ignoring product page URL: {url}")
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

    async def compute_detailed(self) -> IkeaVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return IkeaVerifierResult(
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
    def _is_valid_ikea_domain(domain: str) -> bool:
        """Check if domain is a valid IKEA domain.

        Accepts:
        - Exact matches: ikea.com, www.ikea.com
        - Any subdomain of ikea.com (e.g., m.ikea.com)
        Rejects:
        - Other TLDs: ikea.co.uk, ikea.de
        """
        domain = domain.lower().rstrip(".")

        # Direct match on known domains
        for base in VALID_BASE_DOMAINS:
            if domain == base:
                return True

        # Any subdomain of ikea.com (but not ikea.co.uk etc.)
        if domain.endswith(".ikea.com"):
            return True

        return False

    # ========================================================================
    # URL MATCHING
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Compare two IKEA URLs.

        Performs sequential field comparison. Returns (match, details).
        If any required field mismatches, returns False immediately.
        """
        details: dict[str, Any] = {"mismatches": [], "extra_params": []}

        try:
            agent = parse_ikea_url(agent_url)
            gt = parse_ikea_url(gt_url)

            # 1. Page type: search pages and category pages are NOT equivalent
            if gt["page_type"] in ("search", "category"):
                if agent["page_type"] != gt["page_type"]:
                    details["mismatches"].append(
                        f"Page type: '{agent['page_type']}' vs '{gt['page_type']}'"
                    )
                    return False, details

            # 2. Search keyword (search pages only)
            if gt["page_type"] == "search" and gt["keyword"]:
                if not agent["keyword"]:
                    details["mismatches"].append(
                        f"Search keyword missing (expected '{gt['keyword']}')"
                    )
                    return False, details
                if agent["keyword"] != gt["keyword"]:
                    details["mismatches"].append(
                        f"Search keyword: '{agent['keyword']}' vs '{gt['keyword']}'"
                    )
                    return False, details

            # 3. Category slug (category pages only)
            if gt["page_type"] == "category" and gt["category_slug"]:
                if not agent["category_slug"]:
                    details["mismatches"].append(
                        f"Category slug missing (expected '{gt['category_slug']}')"
                    )
                    return False, details
                if agent["category_slug"] != gt["category_slug"]:
                    details["mismatches"].append(
                        f"Category slug: '{agent['category_slug']}' vs '{gt['category_slug']}'"
                    )
                    return False, details

            # 4. Filters — each GT filter must be present in agent
            gt_filters = gt["filters"]
            agent_filters = agent["filters"]
            for filter_key, gt_values in gt_filters.items():
                agent_values = agent_filters.get(filter_key, [])

                # Normalize filter values for comparison
                if filter_key == "f-colors":
                    gt_values = sorted([_normalize_color(v) for v in gt_values])
                    agent_values = sorted(
                        [_normalize_color(v) for v in agent_values]
                    )
                else:
                    # Case-insensitive comparison for all other filter types
                    gt_values = [v.lower() for v in gt_values]
                    agent_values = [v.lower() for v in agent_values]

                if not agent_values:
                    details["mismatches"].append(
                        f"Filter '{filter_key}' missing (expected {gt_values})"
                    )
                    return False, details

                # Sort both for order-independent comparison
                if sorted(agent_values) != sorted(gt_values):
                    details["mismatches"].append(
                        f"Filter '{filter_key}': {sorted(agent_values)} vs {sorted(gt_values)}"
                    )
                    return False, details

            # 5. Sort order
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
    url: str = "https://www.ikea.com/us/en/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for IKEA URL matching.

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

    eval_target = get_import_path(IkeaUrlMatch)
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
        "task_id": "navi_bench/ikea/search_navigation/0",
        "task_generation_config_json": json.dumps(
            {
                "_target_": "navi_bench.ikea.ikea_url_match.generate_task_config",
                "url": "https://www.ikea.com/us/en/",
                "task": "Search for white desks on IKEA and sort by lowest price.",
                "gt_url": [
                    "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"
                ],
                "location": "United States",
                "timezone": "America/Los_Angeles",
                "timestamp": None,
                "values": {},
            }
        ),
        "env": "real",
        "domain": "ikea",
        "l1_category": "e_commerce",
        "l2_category": "search_navigation",
        "suggested_difficulty": "hard",
        "suggested_hint": "Use the IKEA search bar and sidebar filters.",
        "suggested_max_steps": 50,
        "suggested_split": "validation",
        "metadata_json": "null",
    }

    item = DatasetItem(**dataset_row)
    task_config = item.generate_task_config()
    print(f"URL:  {task_config.url}")
    print(f"Task: {task_config.task}")
    print(f"Eval: {json.dumps(task_config.eval_config, indent=2)}")
