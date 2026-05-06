"""Mercari URL Match verifier for marketplace search navigation.

This module provides functionality to verify AI agent navigation on Mercari
by comparing the agent's final URL against expected ground truth URLs.

The verifier handles all Mercari URL variations including:
- Search results path: /search/?keyword=<search_term>
- Category browse path: /us/category/<name>-<id>/
- Individual listings: /us/item/m<numeric_id>/
- Keyword search: keyword=<search_term>
- Price filters: minPrice, maxPrice (in CENTS — $25 = 2500)
- Sort order: sortBy=1|2|3|4 (best_match|newest|price_asc|price_desc)
- Item condition: itemConditions=1|2|3|4|5 (new|like_new|good|fair|poor)
  Multi-select via hyphen: itemConditions=1-2
- Category filter: categoryIds=<numeric_id>
- Brand filter: brandIds=<numeric_id>
- Free shipping: shippingPayerIds=2
- Item origin: countrySources=1|2 (USA|Japan)
- Deals only: withDealsOnly=true
- Item status: statusIds=1|2 (on_sale|sold_out)
- Color filter: colorIds=<numeric_id>

Browser-Verified CLICKABLE Filters (Apr 2026 on mercari.com):
  Left sidebar (desktop):
    keyword, minPrice, maxPrice, sortBy, itemConditions, categoryIds,
    brandIds, shippingPayerIds, countrySources, withDealsOnly, colorIds
  Mobile filter drawer:
    Same as above + statusIds

  Price presets (sidebar radio buttons):
    Under $25  → maxPrice=2500
    $25–$50    → minPrice=2500&maxPrice=5000
    $50–$100   → minPrice=5000&maxPrice=10000
    $100–$200  → minPrice=10000&maxPrice=20000
    $200 and up → minPrice=20000

Note: Prices are encoded in CENTS. $1 = 100 in the URL.
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


class MercariVerifierResult(BaseModel):
    """Detailed verification result for Mercari URL matching."""

    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid Mercari domain patterns
VALID_BASE_DOMAINS = {
    "mercari.com",
    "www.mercari.com",
}

# Sort order normalization: string aliases → canonical numeric value
SORT_ORDER_MAP = {
    # Canonical numeric values
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    # String aliases (for agent URLs that may use descriptive names)
    "best_match": "1",
    "bestmatch": "1",
    "best match": "1",
    "default": "1",
    "relevance": "1",
    "newest": "2",
    "newest_first": "2",
    "newest first": "2",
    "date_listed": "2",
    "recently_listed": "2",
    "price_asc": "3",
    "price_ascend": "3",
    "price_low": "3",
    "lowest_price": "3",
    "lowest_price_first": "3",
    "lowest price first": "3",
    "price_low_to_high": "3",
    "price: lowest first": "3",
    "price_desc": "4",
    "price_descend": "4",
    "price_high": "4",
    "highest_price": "4",
    "highest_price_first": "4",
    "highest price first": "4",
    "price_high_to_low": "4",
    "price: highest first": "4",
}

# Item condition normalization: string aliases → canonical numeric value
CONDITION_MAP = {
    # Canonical numeric values
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    # String aliases
    "new": "1",
    "like_new": "2",
    "like new": "2",
    "likenew": "2",
    "good": "3",
    "fair": "4",
    "poor": "5",
}

# Item origin normalization
COUNTRY_SOURCE_MAP = {
    "1": "1",
    "2": "2",
    "usa": "1",
    "us": "1",
    "united_states": "1",
    "united states": "1",
    "japan": "2",
    "jp": "2",
}

# Shipping payer normalization
SHIPPING_PAYER_MAP = {
    "2": "2",
    "free": "2",
    "free_shipping": "2",
    "free shipping": "2",
    "seller": "2",
}

# Status normalization
STATUS_MAP = {
    "1": "1",
    "2": "2",
    "on_sale": "1",
    "on sale": "1",
    "active": "1",
    "sold_out": "2",
    "sold out": "2",
    "sold": "2",
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


def _get_int_param(query: dict, *keys: str) -> int | None:
    """Get a parameter as integer, or None if missing/unparseable."""
    raw = _get_param(query, *keys)
    if not raw:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _normalize_query_text(text: str) -> str:
    """Normalize a search query string for comparison.

    - URL-decode
    - Lowercase
    - Collapse whitespace
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""
    text = unquote(text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_sort_order(raw: str) -> str:
    """Normalize sort order to canonical numeric value (1-4)."""
    if not raw:
        return ""
    return SORT_ORDER_MAP.get(raw.lower().strip(), raw.strip())


def _normalize_conditions(raw: str) -> list[str]:
    """Normalize item conditions to sorted list of canonical numeric values.

    Mercari supports multi-select via hyphen separator: itemConditions=1-2
    Also handles comma-separated for robustness: itemConditions=1,2

    Returns sorted list of canonical condition IDs.
    """
    if not raw:
        return []
    raw = raw.strip()

    # Split on hyphen (Mercari's native separator) or comma (fallback)
    if "-" in raw:
        parts = [p.strip() for p in raw.split("-") if p.strip()]
    elif "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        parts = [raw]

    # Normalize each part
    normalized = []
    for part in parts:
        canonical = CONDITION_MAP.get(part.lower().strip(), part.strip())
        if canonical and canonical not in normalized:
            normalized.append(canonical)

    return sorted(normalized)


def _normalize_country_source(raw: str) -> str:
    """Normalize country source / item origin to canonical value."""
    if not raw:
        return ""
    return COUNTRY_SOURCE_MAP.get(raw.lower().strip(), raw.strip())


def _normalize_shipping_payer(raw: str) -> str:
    """Normalize shipping payer ID to canonical value."""
    if not raw:
        return ""
    return SHIPPING_PAYER_MAP.get(raw.lower().strip(), raw.strip())


def _normalize_status(raw: str) -> str:
    """Normalize status ID to canonical value."""
    if not raw:
        return ""
    return STATUS_MAP.get(raw.lower().strip(), raw.strip())


def _extract_category_from_path(path: str) -> str:
    """Extract the category ID from a Mercari category browse path.

    /us/category/electronics-7/ → "7"
    /us/category/women-1/ → "1"

    Returns empty string if no category found.
    """
    if not path:
        return ""

    path = path.strip("/")

    # Pattern: /us/category/{name}-{id}
    m = re.search(r"/category/[a-zA-Z\-_]+-(\d+)$", "/" + path)
    if m:
        return m.group(1)

    # Fallback: just /category/{id}
    m = re.search(r"/category/(\d+)$", "/" + path)
    if m:
        return m.group(1)

    return ""


# =============================================================================
# URL PARSER
# =============================================================================


def parse_mercari_url(url: str) -> dict[str, Any]:
    """Parse a Mercari URL into normalized components.

    Parses ALL clickable filters (browser-verified Apr 2026).

    Returns dict with keys:
      keyword, min_price, max_price, sort_by,
      item_conditions (list), category_ids, brand_ids,
      shipping_payer_ids, country_sources, with_deals_only,
      status_ids, color_ids, category_from_path
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)

    result: dict[str, Any] = {
        # Search query
        "keyword": "",
        # Price (in cents)
        "min_price": None,
        "max_price": None,
        # Sort
        "sort_by": "",
        # Conditions (multi-select → list)
        "item_conditions": [],
        # Category
        "category_ids": "",
        "category_from_path": "",
        # Brand
        "brand_ids": "",
        # Shipping
        "shipping_payer_ids": "",
        # Item origin
        "country_sources": "",
        # Deals
        "with_deals_only": "",
        # Status
        "status_ids": "",
        # Color
        "color_ids": "",
    }

    # Search query
    raw_keyword = _get_param(query, "keyword")
    result["keyword"] = _normalize_query_text(raw_keyword)

    # Price range (in cents)
    result["min_price"] = _get_int_param(query, "minPrice", "minprice")
    result["max_price"] = _get_int_param(query, "maxPrice", "maxprice")

    # Sort order
    raw_sort = _get_param(query, "sortBy", "sortby")
    result["sort_by"] = _normalize_sort_order(raw_sort)

    # Item conditions (multi-select)
    raw_conditions = _get_param(query, "itemConditions", "itemconditions")
    result["item_conditions"] = _normalize_conditions(raw_conditions)

    # Category ID (query param)
    result["category_ids"] = _get_param(query, "categoryIds", "categoryids")

    # Category from path
    result["category_from_path"] = _extract_category_from_path(parsed.path)

    # Brand ID
    result["brand_ids"] = _get_param(query, "brandIds", "brandids")

    # Shipping payer
    raw_shipping = _get_param(query, "shippingPayerIds", "shippingpayerids")
    result["shipping_payer_ids"] = _normalize_shipping_payer(raw_shipping)

    # Country source / Item origin
    raw_country = _get_param(query, "countrySources", "countrysources")
    result["country_sources"] = _normalize_country_source(raw_country)

    # Deals only
    raw_deals = _get_param(query, "withDealsOnly", "withdealsonly")
    result["with_deals_only"] = raw_deals.lower().strip() if raw_deals else ""

    # Status
    raw_status = _get_param(query, "statusIds", "statusids")
    result["status_ids"] = _normalize_status(raw_status)

    # Color
    result["color_ids"] = _get_param(query, "colorIds", "colorids")

    return result


# =============================================================================
# VERIFIER CLASS
# =============================================================================


@beartype
class MercariUrlMatch(BaseMetric):
    """Comprehensive Mercari URL verifier for search/filter tasks.

    Browser-Verified (Apr 2026 on mercari.com):
    - Search path: /search/?keyword=...&filters
    - Category path: /us/category/{name}-{id}/
    - All filters encoded as query parameters
    - Prices in CENTS ($1 = 100)

    Matching Rules (hardened — no auto-pass loopholes):
    - If GT specifies a field and agent omits it → FAIL
    - Search keyword: case-insensitive, whitespace-normalized
    - Price: exact integer match (in cents)
    - Conditions: normalized to sorted numeric list, order-independent
    - Sort/shipping/origin/status: alias-normalized exact match
    - Category: ID match (from query param or path segment)
    - Brand: exact numeric ID match
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
        if domain and not self._is_valid_mercari_domain(domain):
            logger.debug(f"Ignoring non-Mercari URL: {url}")
            return

        # Must be a search or category URL (not item listing)
        path = (parsed.path or "").lower()
        if "/us/item/" in path or "/item/" in path:
            logger.debug(f"Ignoring item listing URL: {url}")
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

    async def compute_detailed(self) -> MercariVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return MercariVerifierResult(
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
    def _is_valid_mercari_domain(domain: str) -> bool:
        """Check if domain is a valid Mercari domain.

        Accepts:
        - Exact matches: mercari.com, www.mercari.com
        - Any subdomain of mercari.com
        """
        domain = domain.lower().rstrip(".")

        # Direct match on known domains
        for base in VALID_BASE_DOMAINS:
            if domain == base:
                return True

        # Any subdomain of mercari.com
        if domain.endswith(".mercari.com"):
            return True

        return False

    # ========================================================================
    # URL MATCHING
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Compare two Mercari URLs.

        Performs sequential field comparison. Returns (match, details).
        If any required field mismatches, returns False immediately with
        mismatch details.
        """
        details: dict[str, Any] = {"mismatches": [], "extra_params": []}

        try:
            agent = parse_mercari_url(agent_url)
            gt = parse_mercari_url(gt_url)

            # 1. Search keyword (case-insensitive, whitespace-normalized)
            if gt["keyword"]:
                if not agent["keyword"]:
                    details["mismatches"].append(
                        f"Keyword missing (expected '{gt['keyword']}')"
                    )
                    return False, details
                if agent["keyword"] != gt["keyword"]:
                    details["mismatches"].append(
                        f"Keyword: '{agent['keyword']}' vs '{gt['keyword']}'"
                    )
                    return False, details

            # 2. Minimum price (in cents)
            if gt["min_price"] is not None:
                if agent["min_price"] is None:
                    details["mismatches"].append(
                        f"Min price missing (expected {gt['min_price']})"
                    )
                    return False, details
                if agent["min_price"] != gt["min_price"]:
                    details["mismatches"].append(
                        f"Min price: {agent['min_price']} vs {gt['min_price']}"
                    )
                    return False, details

            # 3. Maximum price (in cents)
            if gt["max_price"] is not None:
                if agent["max_price"] is None:
                    details["mismatches"].append(
                        f"Max price missing (expected {gt['max_price']})"
                    )
                    return False, details
                if agent["max_price"] != gt["max_price"]:
                    details["mismatches"].append(
                        f"Max price: {agent['max_price']} vs {gt['max_price']}"
                    )
                    return False, details

            # 4. Sort order
            if gt["sort_by"]:
                if not agent["sort_by"]:
                    details["mismatches"].append(
                        f"Sort order missing (expected '{gt['sort_by']}')"
                    )
                    return False, details
                if agent["sort_by"] != gt["sort_by"]:
                    details["mismatches"].append(
                        f"Sort order: '{agent['sort_by']}' vs '{gt['sort_by']}'"
                    )
                    return False, details

            # 5. Item conditions (multi-select — compared as sorted lists)
            if gt["item_conditions"]:
                if not agent["item_conditions"]:
                    details["mismatches"].append(
                        f"Conditions missing (expected {gt['item_conditions']})"
                    )
                    return False, details
                if agent["item_conditions"] != gt["item_conditions"]:
                    details["mismatches"].append(
                        f"Conditions: {agent['item_conditions']} "
                        f"vs {gt['item_conditions']}"
                    )
                    return False, details

            # 6. Category ID (query param)
            gt_cat = gt["category_ids"] or gt["category_from_path"]
            if gt_cat:
                agent_cat = agent["category_ids"] or agent["category_from_path"]
                if not agent_cat:
                    details["mismatches"].append(
                        f"Category ID missing (expected '{gt_cat}')"
                    )
                    return False, details
                if agent_cat != gt_cat:
                    details["mismatches"].append(
                        f"Category ID: '{agent_cat}' vs '{gt_cat}'"
                    )
                    return False, details

            # 7. Brand ID
            if gt["brand_ids"]:
                if not agent["brand_ids"]:
                    details["mismatches"].append(
                        f"Brand ID missing (expected '{gt['brand_ids']}')"
                    )
                    return False, details
                if agent["brand_ids"] != gt["brand_ids"]:
                    details["mismatches"].append(
                        f"Brand ID: '{agent['brand_ids']}' "
                        f"vs '{gt['brand_ids']}'"
                    )
                    return False, details

            # 8. Shipping payer (free shipping)
            if gt["shipping_payer_ids"]:
                if not agent["shipping_payer_ids"]:
                    details["mismatches"].append(
                        f"Shipping payer missing "
                        f"(expected '{gt['shipping_payer_ids']}')"
                    )
                    return False, details
                if agent["shipping_payer_ids"] != gt["shipping_payer_ids"]:
                    details["mismatches"].append(
                        f"Shipping payer: '{agent['shipping_payer_ids']}' "
                        f"vs '{gt['shipping_payer_ids']}'"
                    )
                    return False, details

            # 9. Country source / Item origin
            if gt["country_sources"]:
                if not agent["country_sources"]:
                    details["mismatches"].append(
                        f"Country source missing "
                        f"(expected '{gt['country_sources']}')"
                    )
                    return False, details
                if agent["country_sources"] != gt["country_sources"]:
                    details["mismatches"].append(
                        f"Country source: '{agent['country_sources']}' "
                        f"vs '{gt['country_sources']}'"
                    )
                    return False, details

            # 10. Deals only
            if gt["with_deals_only"]:
                if not agent["with_deals_only"]:
                    details["mismatches"].append(
                        f"Deals filter missing "
                        f"(expected '{gt['with_deals_only']}')"
                    )
                    return False, details
                if agent["with_deals_only"] != gt["with_deals_only"]:
                    details["mismatches"].append(
                        f"Deals: '{agent['with_deals_only']}' "
                        f"vs '{gt['with_deals_only']}'"
                    )
                    return False, details

            # 11. Status
            if gt["status_ids"]:
                if not agent["status_ids"]:
                    details["mismatches"].append(
                        f"Status missing (expected '{gt['status_ids']}')"
                    )
                    return False, details
                if agent["status_ids"] != gt["status_ids"]:
                    details["mismatches"].append(
                        f"Status: '{agent['status_ids']}' "
                        f"vs '{gt['status_ids']}'"
                    )
                    return False, details

            # 12. Color ID
            if gt["color_ids"]:
                if not agent["color_ids"]:
                    details["mismatches"].append(
                        f"Color ID missing (expected '{gt['color_ids']}')"
                    )
                    return False, details
                if agent["color_ids"] != gt["color_ids"]:
                    details["mismatches"].append(
                        f"Color ID: '{agent['color_ids']}' "
                        f"vs '{gt['color_ids']}'"
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
    url: str = "https://www.mercari.com/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Mercari URL matching.

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

    eval_target = get_import_path(MercariUrlMatch)
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
        "task_id": "navi_bench/mercari/general_search/0",
        "task_generation_config_json": json.dumps(
            {
                "_target_": "navi_bench.mercari.mercari_url_match.generate_task_config",
                "url": "https://www.mercari.com/",
                "task": (
                    "Search for Nike shoes priced between $50 and $150 in new condition, "
                    "sorted by lowest price first. How many results are there?"
                ),
                "location": "San Francisco, CA, United States",
                "timezone": "America/Los_Angeles",
                "gt_url": [
                    "https://www.mercari.com/search/?keyword=nike+shoes&minPrice=5000&maxPrice=15000&itemConditions=1&sortBy=3"
                ],
            }
        ),
        "env": "real",
        "domain": "mercari",
        "l1_category": "e_commerce",
        "l2_category": "general_search",
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
