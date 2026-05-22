"""
Zillow URL Match Verifier

A comprehensive URL-based verifier for Zillow.com property search navigation.
Validates AI agent navigation by parsing the searchQueryState URL parameter.

Author: NaviBench Team
Version: 1.0.0
"""

import json
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

from beartype import beartype
from loguru import logger
from pydantic import BaseModel

from navi_bench.base import BaseMetric, BaseTaskConfig, UserMetadata, get_import_path


class ZillowVerifierResult(BaseModel):
    """Result of Zillow URL verification."""

    score: float  # 0.0 to 1.0 (partial coverage supported)
    match: bool  # True only if ALL required GT groups are covered
    agent_url: str  # Last agent URL (legacy compat)
    ground_truth_url: str  # First GT URL (legacy compat)
    details: dict  # Detailed comparison results
    coverage: str = ""  # e.g. "2/3" for partial scoring


class ZillowUrlMatch(BaseMetric):
    """
    Zillow URL Match Verifier.

    Verifies that an AI agent has correctly navigated to the expected
    Zillow search page by comparing URL parameters.

    Zillow encodes all search state in a single URL parameter called
    `searchQueryState` which contains URL-encoded JSON.

    Example URL:
        https://www.zillow.com/homes/for_sale/?searchQueryState=%7B%22filterState%22%3A%7B%22price%22%3A%7B%22min%22%3A500000%7D%7D%7D

    Decoded searchQueryState:
        {
            "filterState": {
                "price": {"min": 500000}
            }
        }
    """

    # Parameters to ignore during comparison (UI state, not search filters)
    IGNORED_PARAMS = {
        "pagination",
        "mapBounds",
        "isMapVisible",
        "isListVisible",
        "mapZoom",
        "customRegionId",
        "sort",  # Auto-set default sort, not user-intent
        "fr",  # for-rent flag (context only)
    }

    # Mapping of abbreviated property type keys → canonical key.
    # Zillow uses BOTH forms depending on context:
    #   Ground truths often use: isHouse, isCondo, isTownhouse, etc.
    #   Live browser URLs use:   tow:false, mf:false, etc.
    ABBREV_TO_CANONICAL = {
        "sf": "ishouse",
        "tow": "istownhouse",
        "mf": "ismultifamily",
        "con": "iscondo",
        "land": "islotland",
        "apa": "isapartment",
        "apco": "isapartment",  # Apartment Community alias
        "manu": "ismanufactured",
    }

    # All 7 canonical property types
    ALL_PROPERTY_TYPES = {
        "ishouse",
        "istownhouse",
        "ismultifamily",
        "iscondo",
        "islotland",
        "isapartment",
        "ismanufactured",
    }

    # Primary listing status types (for-sale context).
    # Zillow uses negative encoding: selecting e.g. "New Construction"
    # disables all OTHER primary statuses (fsba:F, fsbo:F, fore:F, auc:F).
    # The 5 primary types that participate in negative encoding:
    ALL_LISTING_TYPES = {"fsba", "fsbo", "nc", "fore", "auc"}

    # Valid Zillow domains
    VALID_DOMAINS = {"zillow.com", "www.zillow.com"}

    # URL path patterns that indicate non-search / error pages
    INVALID_PATH_PATTERNS = {
        "/error",
        "/captcha",
        "/404",
        "/login",
        "/register",
        "/user/",
        "/myzillow",
        "/profile",
    }

    # Search type patterns in URL path
    SEARCH_TYPES = {
        "for_sale": ["/homes/for_sale/", "for_sale", "_rb/"],
        "for_rent": ["/homes/for_rent/", "for_rent", "/rentals/", "/apartments-for-rent/"],
        "recently_sold": ["/homes/recently_sold/", "recently_sold", "/sold/"],
    }

    def __init__(
        self,
        gt_urls=None,
        *,
        ground_truth_url: str | None = None,
        strict_location: bool = True,
        ignore_map_bounds: bool = True,
        ignore_pagination: bool = True,
    ):
        """
        Initialize the Zillow URL verifier.

        Supports two input formats:

        1. **New AND/OR format** (``gt_urls``):
           ``gt_urls: list[list[str]]`` — outer list = AND (all groups
           must be covered), inner list = OR (any alternative suffices).

        2. **Legacy single-URL format** (``ground_truth_url``):
           ``ground_truth_url: str`` — auto-converted to ``[[url]]``.

        Backward-compatible: passing a single ``str`` or flat ``list[str]``
        as ``gt_urls`` is also accepted and auto-normalized.

        Args:
            gt_urls: Ground-truth URLs in AND/OR structure, or legacy
                formats (str, list[str]) which are auto-normalized.
            ground_truth_url: Legacy single GT URL (keyword-only).
            strict_location: If True, requires exact location match.
            ignore_map_bounds: If True, ignores mapBounds differences.
            ignore_pagination: If True, ignores pagination differences.
        """
        # ------------------------------------------------------------------
        # Normalize gt_urls to canonical list[list[str]] form
        # ------------------------------------------------------------------
        if gt_urls is not None and ground_truth_url is not None:
            raise ValueError("Specify either 'gt_urls' or 'ground_truth_url', not both.")

        if ground_truth_url is not None:
            # Legacy single-URL kwarg → wrap
            self.gt_urls: list[list[str]] = [[ground_truth_url]]
        elif gt_urls is not None:
            if isinstance(gt_urls, str):
                # Single URL string passed positionally (backward compat)
                self.gt_urls = [[gt_urls]]
            elif isinstance(gt_urls, list) and gt_urls and isinstance(gt_urls[0], str):
                # Flat list of alternatives: ["url1", "url2"] → [["url1", "url2"]]
                self.gt_urls = [gt_urls]
            elif isinstance(gt_urls, list):
                # Full AND/OR format: [["url1", "url2"], ["url3"]]
                self.gt_urls = gt_urls
            else:
                raise ValueError(f"Invalid gt_urls type: {type(gt_urls)}")
        else:
            raise ValueError("Must specify either 'gt_urls' or 'ground_truth_url'.")

        # Legacy compat: expose the first GT URL as a simple property
        self.ground_truth_url: str = self.gt_urls[0][0]

        self.strict_location = strict_location
        self.ignore_map_bounds = ignore_map_bounds
        self.ignore_pagination = ignore_pagination

        self._agent_urls: list[str] = []
        self._parsed_gt_groups = [
            [self._parse_zillow_url(url) for url in group]
            for group in self.gt_urls
        ]

    async def reset(self) -> None:
        """Reset the verifier state."""
        self._agent_urls = []

    @staticmethod
    def _is_valid_zillow_url(url: str) -> bool:
        """Check if a URL is a valid Zillow search page.

        Rejects:
        - Non-Zillow domains (e.g. fake-zillow.com)
        - Error/non-search pages (e.g. /error404, /captcha, /login)
        """
        if not url:
            return False
        parsed = urlparse(url.strip())
        domain = parsed.hostname or ""
        # Must be from zillow.com
        if domain not in ZillowUrlMatch.VALID_DOMAINS:
            return False
        # Reject known non-search paths
        path_lower = parsed.path.lower()
        if any(p in path_lower for p in ZillowUrlMatch.INVALID_PATH_PATTERNS):
            return False
        return True

    @beartype
    async def update(self, *, url: Optional[str] = None, **kwargs) -> None:
        """
        Update the verifier with the agent's current URL.

        All valid Zillow URLs are accumulated so that AND-level groups
        can each be matched against a different page the agent visited.

        Args:
            url: The current URL from the agent's browser.
        """
        if url:
            if not self._is_valid_zillow_url(url):
                logger.debug(f"Ignoring non-Zillow URL: {url}")
                return
            if url not in self._agent_urls:
                self._agent_urls.append(url)
                logger.debug(f"Tracked agent URL ({len(self._agent_urls)} total): {url}")

    @beartype
    async def compute(self) -> ZillowVerifierResult:
        """
        Compute the verification result using AND/OR matching logic.

        AND level: Every GT group must be covered by at least one agent URL.
        OR  level: Within each group, any alternative URL matching suffices.

        Returns:
            ZillowVerifierResult with partial coverage score.
        """
        n_required = len(self.gt_urls)

        if not self._agent_urls:
            logger.warning("No agent URLs provided")
            return ZillowVerifierResult(
                score=0.0,
                match=False,
                agent_url="",
                ground_truth_url=self.ground_truth_url,
                details={"error": "No agent URL provided"},
                coverage=f"0/{n_required}",
            )

        n_covered = 0
        group_details = []

        # AND level: iterate over all required GT groups
        for i, gt_group in enumerate(self.gt_urls):
            group_covered = False
            best_details = None

            # OR level: any alternative URL in this group suffices
            for j, gt_url in enumerate(gt_group):
                # Check against all tracked agent URLs
                for agent_url in self._agent_urls:
                    match, details = self._urls_match(agent_url, gt_url)
                    if match:
                        group_covered = True
                        best_details = {
                            "group_index": i,
                            "matched_alternative": j,
                            "agent_url": agent_url,
                            "gt_url": gt_url,
                            "match": True,
                            "details": details,
                        }
                        logger.info(
                            f"Group {i} covered: agent URL matched alternative {j}\n"
                            f"    agent_url: {agent_url}\n"
                            f"    gt_url: {gt_url}"
                        )
                        break  # Found a match for this alternative
                if group_covered:
                    break  # This group is satisfied

            if group_covered:
                n_covered += 1
            else:
                # Store the last comparison details for debugging
                if gt_group and self._agent_urls:
                    _, last_details = self._urls_match(self._agent_urls[-1], gt_group[0])
                    best_details = {
                        "group_index": i,
                        "matched_alternative": None,
                        "agent_url": self._agent_urls[-1],
                        "gt_url": gt_group[0],
                        "match": False,
                        "details": last_details,
                    }

            if best_details:
                group_details.append(best_details)

        score = n_covered / max(n_required, 1)
        coverage_str = f"{n_covered}/{n_required}"

        logger.info(f"Coverage: {coverage_str} (score={score:.2f})")

        return ZillowVerifierResult(
            score=score,
            match=n_covered == n_required,
            agent_url=self._agent_urls[-1] if self._agent_urls else "",
            ground_truth_url=self.ground_truth_url,
            details={
                "coverage": coverage_str,
                "n_covered": n_covered,
                "n_required": n_required,
                "agent_urls_count": len(self._agent_urls),
                "groups": group_details,
            },
            coverage=coverage_str,
        )

    def _parse_zillow_url(self, url: str) -> dict:
        """
        Parse a Zillow URL into normalized components.

        Args:
            url: The Zillow URL to parse.

        Returns:
            Dictionary with parsed components:
            - search_type: "for_sale", "for_rent", or "recently_sold"
            - location: The search location (city, zip, etc.)
            - region_id: Zillow region ID if present
            - region_type: Zillow region type if present
            - filters: Normalized filter state dictionary
        """
        result = {"search_type": "for_sale", "location": "", "region_id": None, "region_type": None, "filters": {}}

        if not url:
            return result

        # Normalize URL
        url = url.strip()

        # Parse URL
        parsed = urlparse(url)

        # Validate domain
        domain = parsed.hostname or ""
        if domain and domain not in self.VALID_DOMAINS:
            logger.warning(f"Invalid Zillow domain: {domain}")
            return result

        path = parsed.path.lower()

        # Detect search type from path
        for search_type, patterns in self.SEARCH_TYPES.items():
            if any(p in path for p in patterns):
                result["search_type"] = search_type
                break

        # Extract location from path
        # Pattern: /homes/for_sale/Los-Angeles-CA_rb/ or /los-angeles-ca/
        location_match = re.search(
            r"/(?:homes/(?:for_sale|for_rent|recently_sold)/)?([^/]+?)(?:_rb)?/?(?:\?|$)", path, re.IGNORECASE
        )
        if location_match:
            location = location_match.group(1)
            # Clean up location string
            location = location.replace("-", " ").replace("_", " ")
            location = unquote(location)
            result["location"] = location.lower().strip()

        # Parse searchQueryState parameter
        query_params = parse_qs(parsed.query)

        if "searchQueryState" in query_params:
            try:
                state_json = unquote(query_params["searchQueryState"][0])
                state = json.loads(state_json)

                # Extract region info
                if "regionSelection" in state and state["regionSelection"]:
                    region = state["regionSelection"][0]
                    result["region_id"] = region.get("regionId")
                    result["region_type"] = region.get("regionType")

                # Extract location from usersSearchTerm if present
                if "usersSearchTerm" in state and state["usersSearchTerm"]:
                    result["location"] = state["usersSearchTerm"].lower().strip()

                # Extract and normalize filter state
                if "filterState" in state:
                    result["filters"] = self._normalize_filter_state(state["filterState"])

                # Check for sort selection
                if "sortSelection" in state:
                    sort_value = state["sortSelection"].get("value")
                    if sort_value:
                        result["filters"]["_sort"] = sort_value

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse searchQueryState: {e}")

        return result

    def _normalize_filter_state(self, filter_state: dict) -> dict:
        """
        Normalize the filterState dictionary for comparison.

        Handles various Zillow filter formats and normalizes them
        to a consistent structure.  Also resolves Zillow's two
        property-type encodings:

        1. **Positive (ground truth style)**:
              ``isHouse: {value: true}``   →   ``ishouse: True``

        2. **Negative (live browser style)**:
              ``tow: false, mf: false, land: false, con: false,
               apa: false, apco: false, manu: false``
              (all non-House types disabled → infer ``ishouse: True``)

        Args:
            filter_state: Raw filterState from searchQueryState.

        Returns:
            Normalized filter dictionary with canonical property type keys.
        """
        normalized = {}

        # Track which abbreviated property types are explicitly false
        false_abbrevs: set[str] = set()
        # Track which canonical property types are explicitly true
        true_types: set[str] = set()

        # Track listing status types for negative encoding inference
        false_listing_types: set[str] = set()
        true_listing_types: set[str] = set()

        for key, value in filter_state.items():
            # Skip ignored parameters
            if key in self.IGNORED_PARAMS:
                continue

            # Normalize the key (lowercase)
            norm_key = key.lower()

            # Check if this is a property type abbreviation
            is_abbrev = norm_key in self.ABBREV_TO_CANONICAL
            is_canonical = norm_key in self.ALL_PROPERTY_TYPES
            # Check if this is a listing status type
            is_listing_type = norm_key in self.ALL_LISTING_TYPES

            # Handle different value formats
            if isinstance(value, dict):
                # Handle {value: X} format (boolean, string, or number)
                if "value" in value:
                    val = value["value"]
                    if val is True:
                        # Map abbreviated keys to canonical form
                        if is_abbrev:
                            canonical = self.ABBREV_TO_CANONICAL[norm_key]
                            normalized[canonical] = True
                            true_types.add(canonical)
                        else:
                            normalized[norm_key] = True
                            if is_canonical:
                                true_types.add(norm_key)
                            if is_listing_type:
                                true_listing_types.add(norm_key)
                    elif val is False or val is None:
                        # Track false property types for inference
                        if is_abbrev:
                            false_abbrevs.add(norm_key)
                        # Track false listing types for inference
                        if is_listing_type:
                            false_listing_types.add(norm_key)
                        # Skip false/null values (default state)
                    else:
                        # String or number values
                        normalized[norm_key] = self._normalize_value(val)
                    continue

                # Handle range filters {min: X, max: Y}
                if "min" in value or "max" in value:
                    if "min" in value and value["min"] is not None:
                        normalized[f"{norm_key}_min"] = self._normalize_value(value["min"])
                    if "max" in value and value["max"] is not None:
                        normalized[f"{norm_key}_max"] = self._normalize_value(value["max"])
                    continue

                # Handle exact value
                if "exact" in value:
                    normalized[f"{norm_key}_exact"] = self._normalize_value(value["exact"])
                    continue

                # Recursively process nested dicts (like homeType)
                for sub_key, sub_value in value.items():
                    sub_norm_key = f"{norm_key}_{sub_key}".lower()
                    if isinstance(sub_value, dict) and "value" in sub_value:
                        if sub_value["value"] is True:
                            normalized[sub_norm_key] = True
                    elif isinstance(sub_value, bool) and sub_value:
                        normalized[sub_norm_key] = True
                    elif sub_value not in (None, False, ""):
                        normalized[sub_norm_key] = self._normalize_value(sub_value)

            elif isinstance(value, bool):
                if value:  # Only track True values
                    if is_abbrev:
                        canonical = self.ABBREV_TO_CANONICAL[norm_key]
                        normalized[canonical] = True
                        true_types.add(canonical)
                    else:
                        normalized[norm_key] = True
                        if is_canonical:
                            true_types.add(norm_key)

            elif value is not None and value != "":
                normalized[norm_key] = self._normalize_value(value)

        # ---------------------------------------------------------------
        # Infer positive property types from negative-encoding pattern.
        #
        # Zillow's live browser encodes property type selection by
        # setting all NON-selected types to false.  Examples:
        #
        #   Houses only:
        #     tow:false, mf:false, land:false, con:false,
        #     apa:false, apco:false, manu:false
        #     → infer ishouse:true
        #
        #   Only Condos:
        #     sf:false, tow:false, mf:false, land:false,
        #     apa:false, apco:false, manu:false
        #     → infer iscondo:true
        #
        # Logic: convert false abbrevs to the canonical types they
        # disable, then the selected types = ALL - disabled.
        # ---------------------------------------------------------------
        if false_abbrevs and not true_types:
            disabled_types: set[str] = set()
            for abbrev in false_abbrevs:
                canonical = self.ABBREV_TO_CANONICAL.get(abbrev)
                if canonical:
                    disabled_types.add(canonical)

            selected_types = self.ALL_PROPERTY_TYPES - disabled_types
            if selected_types and len(selected_types) < len(self.ALL_PROPERTY_TYPES):
                for ptype in selected_types:
                    normalized[ptype] = True

        # ---------------------------------------------------------------
        # Infer listing status types from negative-encoding pattern.
        #
        # Same principle as property types.  Zillow's browser encodes
        # listing status selection by disabling all NON-selected types:
        #
        #   New Construction only:
        #     fsba:false, fsbo:false, fore:false, auc:false
        #     → infer nc:true
        #
        #   Foreclosure only:
        #     fsba:false, fsbo:false, nc:false, auc:false
        #     → infer fore:true
        #
        #   FSBO only:
        #     fsba:false, nc:false, fore:false, auc:false
        #     → infer fsbo:true
        #
        # If ALL 5 primary types are false (rental context), the
        # inferred set is empty → no listing types added. ✅
        # ---------------------------------------------------------------
        if false_listing_types and not true_listing_types:
            selected_listings = self.ALL_LISTING_TYPES - false_listing_types
            if selected_listings and len(selected_listings) < len(self.ALL_LISTING_TYPES):
                for lt in selected_listings:
                    normalized[lt] = True

        return normalized

    def _normalize_value(self, value: Any) -> Any:
        """
        Normalize a single filter value.

        Args:
            value: The value to normalize.

        Returns:
            Normalized value (typically string or number).
        """
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            # Convert to int if it's a whole number
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return value

        if isinstance(value, str):
            value = value.strip().lower()

            # Try to convert to number
            try:
                num = float(value)
                if num.is_integer():
                    return int(num)
                return num
            except ValueError:
                pass

            return value

        return value

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """
        Compare two Zillow URLs for equivalence.

        Args:
            agent_url: The URL from the agent's browser.
            gt_url: The ground truth URL.

        Returns:
            Tuple of (match: bool, details: dict)
        """
        agent_parts = self._parse_zillow_url(agent_url)
        gt_parts = self._parse_zillow_url(gt_url)

        details = {"agent_parsed": agent_parts, "gt_parsed": gt_parts, "mismatches": []}

        # 1. Check search type
        if agent_parts["search_type"] != gt_parts["search_type"]:
            details["mismatches"].append(
                {"field": "search_type", "agent": agent_parts["search_type"], "expected": gt_parts["search_type"]}
            )
            logger.debug(f"Search type mismatch: {agent_parts['search_type']} vs {gt_parts['search_type']}")
            return False, details

        # 2. Check location (if strict)
        if self.strict_location and gt_parts["location"]:
            agent_loc = agent_parts["location"].lower().replace(",", "").replace("-", " ")
            gt_loc = gt_parts["location"].lower().replace(",", "").replace("-", " ")

            # Allow partial match (city name matches)
            if gt_loc and gt_loc not in agent_loc and agent_loc not in gt_loc:
                details["mismatches"].append(
                    {"field": "location", "agent": agent_parts["location"], "expected": gt_parts["location"]}
                )
                logger.debug(f"Location mismatch: {agent_parts['location']} vs {gt_parts['location']}")
                return False, details

        # 3. Compare filters
        agent_filters = agent_parts["filters"]
        gt_filters = gt_parts["filters"]

        # Find missing, extra, and wrong filters
        missing = set(gt_filters.keys()) - set(agent_filters.keys())
        extra = set(agent_filters.keys()) - set(gt_filters.keys())
        wrong = {k for k in agent_filters if k in gt_filters and agent_filters[k] != gt_filters[k]}

        if missing or wrong:
            # Missing required filters or wrong values = fail
            if missing:
                details["mismatches"].append({"field": "filters", "type": "missing", "filters": list(missing)})
                logger.debug(f"Missing filters: {missing}")

            if wrong:
                for k in wrong:
                    details["mismatches"].append(
                        {
                            "field": "filters",
                            "type": "wrong_value",
                            "filter": k,
                            "agent": agent_filters[k],
                            "expected": gt_filters[k],
                        }
                    )
                logger.debug(f"Wrong filter values: {wrong}")

            return False, details

        # Extra filters are logged but don't cause failure
        # (agent may have applied additional valid filters)
        if extra:
            details["extra_filters"] = list(extra)
            logger.debug(f"Extra filters (allowed): {extra}")

        logger.info("URLs match!")
        return True, details


# ============================================================================
# COMPREHENSIVE EDGE CASE TESTS
# ============================================================================


def _run_parse_tests(verifier, test_category, tests, test_results):
    """Helper: run parse tests and print results."""
    for test in tests:
        parsed = verifier._parse_zillow_url(test["url"])
        passed = all(parsed["filters"].get(k) == v for k, v in test["expected_filters"].items())
        status = "PASS" if passed else "FAIL"
        if not passed:
            print(f"  [{status}] {test['name']}")
            for k, v in test["expected_filters"].items():
                actual = parsed["filters"].get(k, "<MISSING>")
                if actual != v:
                    print(f"         expected {k}={v!r}, got {actual!r}")
        else:
            print(f"  [{status}] {test['name']}")
        test_results.append(passed)


def run_tests():
    """Run comprehensive URL parsing and matching tests covering all 92 filters."""

    print("=" * 70)
    print("ZILLOW URL VERIFIER - COMPREHENSIVE TESTS (92 FILTERS)")
    print("=" * 70)

    test_results = []
    verifier = ZillowUrlMatch("https://www.zillow.com/homes/for_sale/")

    # =========================================================================
    # Category 1: Search Mode & Location (Section 1 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 1] Search Mode & Location")
    print("-" * 50)

    type_tests = [
        {
            "name": "For sale URL",
            "url": "https://www.zillow.com/homes/for_sale/?searchQueryState=%7B%7D",
            "expected_type": "for_sale",
        },
        {"name": "For rent URL", "url": "https://www.zillow.com/homes/for_rent/", "expected_type": "for_rent"},
        {
            "name": "Recently sold URL",
            "url": "https://www.zillow.com/homes/recently_sold/",
            "expected_type": "recently_sold",
        },
    ]

    for test in type_tests:
        parsed = verifier._parse_zillow_url(test["url"])
        passed = parsed["search_type"] == test["expected_type"]
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test['name']}")
        test_results.append(passed)

    # Location + Region
    loc_url = (
        'https://www.zillow.com/homes/for_sale/?searchQueryState='
        '{"usersSearchTerm":"Los Angeles CA","regionSelection":[{"regionId":12447,"regionType":6}]}'
    )
    parsed = verifier._parse_zillow_url(loc_url)
    passed = parsed["location"] == "los angeles ca" and parsed["region_id"] == 12447 and parsed["region_type"] == 6
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] Location + Region parsing")
    test_results.append(passed)

    # =========================================================================
    # Category 2: Price (Section 2 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 2] Price Filters")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Price",
        [
            {
                "name": "Min price only",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}',
                "expected_filters": {"price_min": 500000},
            },
            {
                "name": "Max price only",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"max":1000000}}}',
                "expected_filters": {"price_max": 1000000},
            },
            {
                "name": "Price range",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":300000,"max":750000}}}',
                "expected_filters": {"price_min": 300000, "price_max": 750000},
            },
            {
                "name": "Monthly payment range",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"monthlyPayment":{"min":2000,"max":4000}}}',
                "expected_filters": {"monthlypayment_min": 2000, "monthlypayment_max": 4000},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 3: Beds & Baths (Section 3 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 3] Beds & Baths")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Beds & Baths",
        [
            {
                "name": "3+ bedrooms",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"beds":{"min":3}}}',
                "expected_filters": {"beds_min": 3},
            },
            {
                "name": "2+ bathrooms",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"baths":{"min":2}}}',
                "expected_filters": {"baths_min": 2},
            },
            {
                "name": "Exact 4 bedrooms",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"beds":{"min":4,"max":4}}}',
                "expected_filters": {"beds_min": 4, "beds_max": 4},
            },
            {
                "name": "Beds + Baths combo",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"beds":{"min":4},"baths":{"min":3}}}',
                "expected_filters": {"beds_min": 4, "baths_min": 3},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 4: Home/Property Type (Section 4 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 4] Property Types (Full + Abbreviated Keys)")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Property Types",
        [
            # Full key format
            {
                "name": "isHouse",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isHouse":{"value":true}}}',
                "expected_filters": {"ishouse": True},
            },
            {
                "name": "isCondo",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isCondo":{"value":true}}}',
                "expected_filters": {"iscondo": True},
            },
            {
                "name": "isTownhouse",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isTownhouse":{"value":true}}}',
                "expected_filters": {"istownhouse": True},
            },
            {
                "name": "isMultiFamily",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isMultiFamily":{"value":true}}}',
                "expected_filters": {"ismultifamily": True},
            },
            {
                "name": "isLotLand",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isLotLand":{"value":true}}}',
                "expected_filters": {"islotland": True},
            },
            {
                "name": "isApartment",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isApartment":{"value":true}}}',
                "expected_filters": {"isapartment": True},
            },
            {
                "name": "isManufactured",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isManufactured":{"value":true}}}',
                "expected_filters": {"ismanufactured": True},
            },
            # Abbreviated key format (normalized to canonical)
            {
                "name": "sf (Houses)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"sf":{"value":true}}}',
                "expected_filters": {"ishouse": True},
            },
            {
                "name": "con (Condos)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"con":{"value":true}}}',
                "expected_filters": {"iscondo": True},
            },
            {
                "name": "tow (Townhomes)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"tow":{"value":true}}}',
                "expected_filters": {"istownhouse": True},
            },
            {
                "name": "mf (Multi-family)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"mf":{"value":true}}}',
                "expected_filters": {"ismultifamily": True},
            },
            {
                "name": "apa (Apartments)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"apa":{"value":true}}}',
                "expected_filters": {"isapartment": True},
            },
            {
                "name": "land (Lots/Land)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"land":{"value":true}}}',
                "expected_filters": {"islotland": True},
            },
            {
                "name": "manu (Manufactured)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"manu":{"value":true}}}',
                "expected_filters": {"ismanufactured": True},
            },
            # Negative encoding (live browser style)
            {
                "name": "Houses only (neg enc)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"tow":{"value":false},"mf":{"value":false},"land":{"value":false},"con":{"value":false},"apa":{"value":false},"apco":{"value":false},"manu":{"value":false}}}',
                "expected_filters": {"ishouse": True},
            },
            {
                "name": "Houses+Townhomes (neg enc)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"mf":{"value":false},"land":{"value":false},"con":{"value":false},"apa":{"value":false},"apco":{"value":false},"manu":{"value":false}}}',
                "expected_filters": {"ishouse": True, "istownhouse": True},
            },
            {
                "name": "Condos only (neg enc)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"sf":{"value":false},"tow":{"value":false},"mf":{"value":false},"land":{"value":false},"apa":{"value":false},"apco":{"value":false},"manu":{"value":false}}}',
                "expected_filters": {"iscondo": True},
            },
            # Multiple types
            {
                "name": "House + Townhouse",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isHouse":{"value":true},"isTownhouse":{"value":true}}}',
                "expected_filters": {"ishouse": True, "istownhouse": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 5: Listing Type & Status (Section 5 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 5] Listing Type & Status")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Listing Status",
        [
            {
                "name": "By Agent",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isForSaleByAgent":{"value":true}}}',
                "expected_filters": {"isforsalebyagent": True},
            },
            {
                "name": "By Owner (FSBO)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isForSaleByOwner":{"value":true}}}',
                "expected_filters": {"isforsalebyowner": True},
            },
            {
                "name": "New Construction",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isNewConstruction":{"value":true}}}',
                "expected_filters": {"isnewconstruction": True},
            },
            {
                "name": "Foreclosures",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isForeclosure":{"value":true}}}',
                "expected_filters": {"isforeclosure": True},
            },
            {
                "name": "Pre-Foreclosures",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isPreForeclosure":{"value":true}}}',
                "expected_filters": {"ispreforeclosure": True},
            },
            {
                "name": "Auctions",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isAuction":{"value":true}}}',
                "expected_filters": {"isauction": True},
            },
            {
                "name": "Coming Soon",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isComingSoon":{"value":true}}}',
                "expected_filters": {"iscomingsoon": True},
            },
            {
                "name": "Pending Listings",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isPendingListings":{"value":true}}}',
                "expected_filters": {"ispendinglistings": True},
            },
            {
                "name": "Accepting Backup Offers",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isAcceptingBackupOffers":{"value":true}}}',
                "expected_filters": {"isacceptingbackupoffers": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 6: Size & Dimensions (Section 6 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 6] Size & Dimensions")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Size",
        [
            {
                "name": "Min sqft",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"sqft":{"min":1500}}}',
                "expected_filters": {"sqft_min": 1500},
            },
            {
                "name": "Max sqft",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"sqft":{"max":3000}}}',
                "expected_filters": {"sqft_max": 3000},
            },
            {
                "name": "Sqft range",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"sqft":{"min":1500,"max":3000}}}',
                "expected_filters": {"sqft_min": 1500, "sqft_max": 3000},
            },
            {
                "name": "Lot size range",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"lotSize":{"min":5000,"max":20000}}}',
                "expected_filters": {"lotsize_min": 5000, "lotsize_max": 20000},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 7: Year Built (Section 7 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 7] Year Built")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Year Built",
        [
            {
                "name": "Built after 2000",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"built":{"min":2000}}}',
                "expected_filters": {"built_min": 2000},
            },
            {
                "name": "Built before 1980",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"built":{"max":1980}}}',
                "expected_filters": {"built_max": 1980},
            },
            {
                "name": "Built between 1990-2010",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"built":{"min":1990,"max":2010}}}',
                "expected_filters": {"built_min": 1990, "built_max": 2010},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 8: Parking (Section 8 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 8] Parking")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Parking",
        [
            {
                "name": "2+ parking spots",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"parking":{"min":2}}}',
                "expected_filters": {"parking_min": 2},
            },
            {
                "name": "Must have garage",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasGarage":{"value":true}}}',
                "expected_filters": {"hasgarage": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 9: Building Features (Section 9 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 9] Building Features")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Building",
        [
            {
                "name": "Single story",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"singleStory":{"value":true}}}',
                "expected_filters": {"singlestory": True},
            },
            {
                "name": "Has basement",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasBasement":{"value":true}}}',
                "expected_filters": {"hasbasement": True},
            },
            {
                "name": "Must have A/C",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasCooling":{"value":true}}}',
                "expected_filters": {"hascooling": True},
            },
            {
                "name": "Hardwood floors",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasHardwoodFloors":{"value":true}}}',
                "expected_filters": {"hashardwoodfloors": True},
            },
            {
                "name": "Fireplace",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasFireplace":{"value":true}}}',
                "expected_filters": {"hasfireplace": True},
            },
            {
                "name": "Accessible",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isAccessible":{"value":true}}}',
                "expected_filters": {"isaccessible": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 10: Exterior Features & Views (Section 10 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 10] Exterior Features & Views")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Exterior",
        [
            {
                "name": "Has pool (full key)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasPool":{"value":true}}}',
                "expected_filters": {"haspool": True},
            },
            {
                "name": "Has pool (abbreviated)",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"pool":{"value":true}}}',
                "expected_filters": {"pool": True},
            },
            {
                "name": "Waterfront",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isWaterfront":{"value":true}}}',
                "expected_filters": {"iswaterfront": True},
            },
            {
                "name": "City view",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasCityView":{"value":true}}}',
                "expected_filters": {"hascityview": True},
            },
            {
                "name": "Mountain view",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasMountainView":{"value":true}}}',
                "expected_filters": {"hasmountainview": True},
            },
            {
                "name": "Water view",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasWaterView":{"value":true}}}',
                "expected_filters": {"haswaterview": True},
            },
            {
                "name": "Park view",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hasParkView":{"value":true}}}',
                "expected_filters": {"hasparkview": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 11: HOA & Financials (Section 11 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 11] HOA & Financials")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "HOA",
        [
            {
                "name": "Max HOA $500",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"hoa":{"max":500}}}',
                "expected_filters": {"hoa_max": 500},
            },
            {
                "name": "No HOA",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"noHoa":{"value":true}}}',
                "expected_filters": {"nohoa": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 12: 55+ Communities (Section 12 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 12] 55+ Communities")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "55+",
        [
            {
                "name": "Include 55+",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"seniorHousing":{"value":"include"}}}',
                "expected_filters": {"seniorhousing": "include"},
            },
            {
                "name": "Exclude 55+",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"seniorHousing":{"value":"exclude"}}}',
                "expected_filters": {"seniorhousing": "exclude"},
            },
            {
                "name": "Only 55+",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"seniorHousing":{"value":"only"}}}',
                "expected_filters": {"seniorhousing": "only"},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 13: Tours & Media (Section 13 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 13] Tours & Media")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Tours",
        [
            {
                "name": "Open House",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isOpenHouse":{"value":true}}}',
                "expected_filters": {"isopenhouse": True},
            },
            {
                "name": "3D Tour",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"has3DTour":{"value":true}}}',
                "expected_filters": {"has3dtour": True},
            },
            {
                "name": "Showcase",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"isShowcase":{"value":true}}}',
                "expected_filters": {"isshowcase": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 14: Days on Zillow (Section 14 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 14] Days on Zillow")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "DOZ",
        [
            {
                "name": "7 days",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"doz":{"value":"7"}}}',
                "expected_filters": {"doz": 7},
            },
            {
                "name": "30 days",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"doz":{"value":"30"}}}',
                "expected_filters": {"doz": 30},
            },
            {
                "name": "6 months",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"doz":{"value":"6m"}}}',
                "expected_filters": {"doz": "6m"},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 15: Keywords (Section 15 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 15] Keywords")
    print("-" * 50)

    _run_parse_tests(
        verifier,
        "Keywords",
        [
            {
                "name": "Keyword search",
                "url": (
                    'https://www.zillow.com/homes/for_sale/'
                    '?searchQueryState={"filterState":{"keywords":"granite counters"}}'
                ),
                "expected_filters": {"keywords": "granite counters"},
            },
            {
                "name": "Pool keyword",
                "url": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"keywords":"pool"}}',
                "expected_filters": {"keywords": "pool"},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 16: Rental-Specific Filters (Section 16 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 16] Rental-Specific Filters")
    print("-" * 50)

    rent_verifier = ZillowUrlMatch("https://www.zillow.com/homes/for_rent/")
    _run_parse_tests(
        rent_verifier,
        "Rental",
        [
            # Pet policies
            {
                "name": "Large dogs allowed",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"largeDogsAllowed":{"value":true}}}',
                "expected_filters": {"largedogsallowed": True},
            },
            {
                "name": "Small dogs allowed",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"smallDogsAllowed":{"value":true}}}',
                "expected_filters": {"smalldogsallowed": True},
            },
            {
                "name": "Cats allowed",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"catsAllowed":{"value":true}}}',
                "expected_filters": {"catsallowed": True},
            },
            {
                "name": "Dogs allowed (any)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"dogsAllowed":{"value":true}}}',
                "expected_filters": {"dogsallowed": True},
            },
            {
                "name": "No pets",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"noPets":{"value":true}}}',
                "expected_filters": {"nopets": True},
            },
            # Laundry
            {
                "name": "In-unit laundry",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"laundryInUnit":{"value":true}}}',
                "expected_filters": {"laundryinunit": True},
            },
            {
                "name": "Laundry in building",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"laundryInBuilding":{"value":true}}}',
                "expected_filters": {"laundryinbuilding": True},
            },
            {
                "name": "Washer/dryer hookups",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"laundryHookup":{"value":true}}}',
                "expected_filters": {"laundryhookup": True},
            },
            # Amenities
            {
                "name": "Furnished",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"isFurnished":{"value":true}}}',
                "expected_filters": {"isfurnished": True},
            },
            {
                "name": "Income restricted",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"isIncomeRestricted":{"value":true}}}',
                "expected_filters": {"isincomerestricted": True},
            },
            {
                "name": "Utilities included",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"utilitiesIncluded":{"value":true}}}',
                "expected_filters": {"utilitiesincluded": True},
            },
            {
                "name": "Short term lease",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"shortTermLease":{"value":true}}}',
                "expected_filters": {"shorttermlease": True},
            },
            # Abbreviated rental keys (discovered from live Zillow exploration)
            {
                "name": "Accepts Zillow Applications (app)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"app":{"value":true}}}',
                "expected_filters": {"app": True},
            },
            {
                "name": "Outdoor Space (os)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"os":{"value":true}}}',
                "expected_filters": {"os": True},
            },
            {
                "name": "Controlled Access (ca)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"ca":{"value":true}}}',
                "expected_filters": {"ca": True},
            },
            {
                "name": "High-Speed Internet (hsia)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"hsia":{"value":true}}}',
                "expected_filters": {"hsia": True},
            },
            {
                "name": "Elevator (eaa)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"eaa":{"value":true}}}',
                "expected_filters": {"eaa": True},
            },
            {
                "name": "Apartment Community (fmfb)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"fmfb":{"value":true}}}',
                "expected_filters": {"fmfb": True},
            },
            {
                "name": "Move-in Date (rad)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"rad":{"value":"2026-03-01"}}}',
                "expected_filters": {"rad": "2026-03-01"},
            },
            {
                "name": "Instant Tour Available (ita)",
                "url": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"ita":{"value":true}}}',
                "expected_filters": {"ita": True},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 17: Sold Properties (Section 17 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 17] Sold Properties")
    print("-" * 50)

    sold_verifier = ZillowUrlMatch("https://www.zillow.com/homes/recently_sold/")
    _run_parse_tests(
        sold_verifier,
        "Sold",
        [
            {
                "name": "Sold in last 30 days",
                "url": 'https://www.zillow.com/homes/recently_sold/?searchQueryState={"filterState":{"soldInLast":{"value":"30d"}}}',
                "expected_filters": {"soldinlast": "30d"},
            },
            {
                "name": "Sold in last 90 days",
                "url": 'https://www.zillow.com/homes/recently_sold/?searchQueryState={"filterState":{"soldInLast":{"value":"90d"}}}',
                "expected_filters": {"soldinlast": "90d"},
            },
        ],
        test_results,
    )

    # =========================================================================
    # Category 18: Sort Options (Section 18 of COVERAGE.md)
    # =========================================================================
    print("\n[Category 18] Sort Options")
    print("-" * 50)

    sort_tests = [
        {"name": "Sort by newest", "value": "days"},
        {"name": "Sort by price low-high", "value": "pricea"},
        {"name": "Sort by price high-low", "value": "priced"},
        {"name": "Sort by bedrooms", "value": "beds"},
        {"name": "Sort by sqft", "value": "size"},
    ]

    for test in sort_tests:
        url = (
            f'https://www.zillow.com/homes/for_sale/?searchQueryState={{"sortSelection":{{"value":"{test["value"]}"}}}}'
        )
        parsed = verifier._parse_zillow_url(url)
        passed = parsed["filters"].get("_sort") == test["value"]
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test['name']}")
        test_results.append(passed)

    # =========================================================================
    # Category 19: URL Matching Logic
    # =========================================================================
    print("\n[Category 19] URL Matching Logic")
    print("-" * 50)

    match_tests = [
        {
            "name": "Exact match",
            "agent": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}',
            "gt": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}',
            "should_match": True,
        },
        {
            "name": "Different prices = no match",
            "agent": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":600000}}}',
            "gt": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}',
            "should_match": False,
        },
        {
            "name": "Extra filters = still match",
            "agent": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000},"beds":{"min":3}}}',
            "gt": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}',
            "should_match": True,
        },
        {
            "name": "Missing required filter = no match",
            "agent": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}',
            "gt": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000},"beds":{"min":3}}}',
            "should_match": False,
        },
        {
            "name": "Search type mismatch = no match",
            "agent": 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"price":{"min":500000}}}',
            "gt": 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}',
            "should_match": False,
        },
    ]

    for test in match_tests:
        v = ZillowUrlMatch(test["gt"])
        match, details = v._urls_match(test["agent"], test["gt"])
        passed = match == test["should_match"]
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test['name']}")
        test_results.append(passed)

    # =========================================================================
    # Category 20: Complex Multi-Filter Matching
    # =========================================================================
    print("\n[Category 20] Complex Multi-Filter Scenarios")
    print("-" * 50)

    # Complex scenario: multiple filters combined
    complex_gt = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000,"max":1000000},"beds":{"min":3},"baths":{"min":2},"isHouse":{"value":true},"hasPool":{"value":true},"built":{"min":2000}}}'
    complex_agent_match = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000,"max":1000000},"beds":{"min":3},"baths":{"min":2},"isHouse":{"value":true},"hasPool":{"value":true},"built":{"min":2000},"hasCooling":{"value":true}}}'
    complex_agent_wrong = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000,"max":1000000},"beds":{"min":3},"baths":{"min":2},"isHouse":{"value":true}}}'

    v = ZillowUrlMatch(complex_gt)
    match1, _ = v._urls_match(complex_agent_match, complex_gt)
    passed1 = match1 is True
    status = "PASS" if passed1 else "FAIL"
    print(f"  [{status}] 6-filter match with extra filter (should pass)")
    test_results.append(passed1)

    match2, details2 = v._urls_match(complex_agent_wrong, complex_gt)
    passed2 = match2 is False
    status = "PASS" if passed2 else "FAIL"
    print(f"  [{status}] 6-filter with 2 missing (should fail)")
    test_results.append(passed2)

    # Rental multi-filter
    rental_gt = 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"price":{"max":3000},"beds":{"min":2},"dogsAllowed":{"value":true},"laundryInUnit":{"value":true},"isFurnished":{"value":true}}}'
    rental_agent = 'https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"price":{"max":3000},"beds":{"min":2},"dogsAllowed":{"value":true},"laundryInUnit":{"value":true},"isFurnished":{"value":true}}}'

    v = ZillowUrlMatch(rental_gt)
    match3, _ = v._urls_match(rental_agent, rental_gt)
    passed3 = match3 is True
    status = "PASS" if passed3 else "FAIL"
    print(f"  [{status}] Rental 5-filter exact match")
    test_results.append(passed3)

    # String value matching (seniorHousing, doz)
    string_gt = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"seniorHousing":{"value":"only"},"doz":{"value":"30"}}}'
    string_agent_match = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"seniorHousing":{"value":"only"},"doz":{"value":"30"}}}'
    string_agent_wrong = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"seniorHousing":{"value":"exclude"},"doz":{"value":"30"}}}'

    v = ZillowUrlMatch(string_gt)
    match4, _ = v._urls_match(string_agent_match, string_gt)
    passed4 = match4 is True
    status = "PASS" if passed4 else "FAIL"
    print(f"  [{status}] String value filters match (55+, DOZ)")
    test_results.append(passed4)

    match5, _ = v._urls_match(string_agent_wrong, string_gt)
    passed5 = match5 is False
    status = "PASS" if passed5 else "FAIL"
    print(f"  [{status}] String value mismatch (only vs exclude)")
    test_results.append(passed5)

    # =========================================================================
    # Category 21: AND/OR Multi-URL Matching (New)
    # =========================================================================
    print("\n[Category 21] AND/OR Multi-URL Matching")
    print("-" * 50)

    import asyncio

    # 21a: Backward compat — single URL string as positional arg
    v_compat = ZillowUrlMatch("https://www.zillow.com/homes/for_sale/")
    passed = v_compat.gt_urls == [["https://www.zillow.com/homes/for_sale/"]]
    print(f"  [{'PASS' if passed else 'FAIL'}] Backward compat: str positional -> [[str]]")
    test_results.append(passed)

    # 21b: Backward compat — ground_truth_url keyword arg
    v_compat2 = ZillowUrlMatch(ground_truth_url="https://www.zillow.com/homes/for_sale/")
    passed = v_compat2.gt_urls == [["https://www.zillow.com/homes/for_sale/"]]
    print(f"  [{'PASS' if passed else 'FAIL'}] Backward compat: ground_truth_url kwarg")
    test_results.append(passed)

    # 21c: gt_urls list[list[str]] (AND/OR) format accepted
    v_multi = ZillowUrlMatch(gt_urls=[
        ['https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}'],
        ['https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"beds":{"min":3}}}'],
    ])
    passed = len(v_multi.gt_urls) == 2
    print(f"  [{'PASS' if passed else 'FAIL'}] gt_urls: 2 AND groups parsed")
    test_results.append(passed)

    # 21d: Flat list backward compat: list[str] → [[str, str]]
    v_flat = ZillowUrlMatch(gt_urls=[
        "https://www.zillow.com/homes/for_sale/?url1",
        "https://www.zillow.com/homes/for_sale/?url2",
    ])
    passed = len(v_flat.gt_urls) == 1 and len(v_flat.gt_urls[0]) == 2
    print(f"  [{'PASS' if passed else 'FAIL'}] Flat list compat: [str,str] -> [[str,str]]")
    test_results.append(passed)

    # 21e: Full AND match (2/2 groups covered) → score 1.0
    async def test_and_full_match():
        gt_a = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}'
        gt_b = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"beds":{"min":3}}}'
        v = ZillowUrlMatch(gt_urls=[[gt_a], [gt_b]])
        await v.update(url=gt_a)
        await v.update(url=gt_b)
        r = await v.compute()
        return r.score == 1.0 and r.match is True and r.coverage == "2/2"

    passed = asyncio.run(test_and_full_match())
    print(f"  [{'PASS' if passed else 'FAIL'}] AND logic: 2/2 groups covered -> score 1.0")
    test_results.append(passed)

    # 21f: Partial coverage (1/2 groups covered) → score 0.5
    async def test_partial_coverage():
        gt_a = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}'
        gt_b = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"beds":{"min":3}}}'
        v = ZillowUrlMatch(gt_urls=[[gt_a], [gt_b]])
        await v.update(url=gt_a)  # Only visit one URL
        r = await v.compute()
        return r.score == 0.5 and r.match is False and r.coverage == "1/2"

    passed = asyncio.run(test_partial_coverage())
    print(f"  [{'PASS' if passed else 'FAIL'}] Partial coverage: 1/2 -> score 0.5")
    test_results.append(passed)

    # 21g: OR alternatives — second alternative in group matches
    async def test_or_alternatives():
        gt_alt1 = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}'
        gt_alt2 = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"beds":{"min":3}}}'
        v = ZillowUrlMatch(gt_urls=[[gt_alt1, gt_alt2]])  # One group, two OR alternatives
        await v.update(url=gt_alt2)  # Visit the second alternative only
        r = await v.compute()
        return r.score == 1.0 and r.match is True and r.coverage == "1/1"

    passed = asyncio.run(test_or_alternatives())
    print(f"  [{'PASS' if passed else 'FAIL'}] OR logic: second alternative matches")
    test_results.append(passed)

    # 21h: No agent URLs → score 0.0
    async def test_no_agent_urls():
        gt = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}'
        v = ZillowUrlMatch(gt_urls=[[gt]])
        r = await v.compute()
        return r.score == 0.0 and r.match is False and r.coverage == "0/1"

    passed = asyncio.run(test_no_agent_urls())
    print(f"  [{'PASS' if passed else 'FAIL'}] No agent URLs -> score 0.0")
    test_results.append(passed)

    # 21i: Reset clears all tracked URLs
    async def test_reset():
        gt = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}'
        v = ZillowUrlMatch(gt_urls=[[gt]])
        await v.update(url=gt)
        r1 = await v.compute()
        await v.reset()
        r2 = await v.compute()
        return r1.score == 1.0 and r2.score == 0.0

    passed = asyncio.run(test_reset())
    print(f"  [{'PASS' if passed else 'FAIL'}] Reset clears tracked URLs")
    test_results.append(passed)

    # 21j: Legacy single-URL compute still works (end-to-end)
    async def test_legacy_compute():
        gt = 'https://www.zillow.com/homes/for_sale/?searchQueryState={"filterState":{"price":{"min":500000}}}'
        v = ZillowUrlMatch(ground_truth_url=gt)
        await v.update(url=gt)
        r = await v.compute()
        return r.score == 1.0 and r.match is True and r.coverage == "1/1"

    passed = asyncio.run(test_legacy_compute())
    print(f"  [{'PASS' if passed else 'FAIL'}] Legacy single-URL end-to-end")
    test_results.append(passed)

    # 21k: generate_task_config backward compat
    tc = generate_task_config(
        url="https://www.zillow.com",
        task="test",
        location="Test, US",
        timezone="America/Los_Angeles",
        ground_truth_url="https://www.zillow.com/test/",
    )
    passed = tc.eval_config["ground_truth_url"] == "https://www.zillow.com/test/"
    print(f"  [{'PASS' if passed else 'FAIL'}] generate_task_config: legacy ground_truth_url")
    test_results.append(passed)

    # 21l: generate_task_config with gt_urls
    tc2 = generate_task_config(
        url="https://www.zillow.com",
        task="test",
        location="Test, US",
        timezone="America/Los_Angeles",
        gt_urls=[["https://www.zillow.com/a/"], ["https://www.zillow.com/b/"]],
    )
    passed = tc2.eval_config["gt_urls"] == [["https://www.zillow.com/a/"], ["https://www.zillow.com/b/"]]
    print(f"  [{'PASS' if passed else 'FAIL'}] generate_task_config: gt_urls format")
    test_results.append(passed)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    passed = sum(test_results)
    total = len(test_results)
    pct = 100 * passed / total if total > 0 else 0
    print(f"TEST SUMMARY: {passed}/{total} tests passed ({pct:.1f}%)")
    print("=" * 70)

    return passed == total


def generate_task_config(
    url: str,
    task: str,
    location: str,
    timezone: str,
    gt_urls: list[list[str]] | None = None,
    ground_truth_url: str | None = None,
) -> BaseTaskConfig:
    """Generate a BaseTaskConfig for a Zillow URL match task.

    Supports both new ``gt_urls`` (AND/OR) and legacy ``ground_truth_url``
    formats.  Follows the same pattern as craigslist_url_match.
    """
    tz_info = ZoneInfo(timezone)
    timestamp = int(datetime.now(tz_info).timestamp())
    user_metadata = UserMetadata(location=location, timezone=timezone, timestamp=timestamp)

    eval_target = get_import_path(ZillowUrlMatch)

    if gt_urls is not None:
        eval_config = {"_target_": eval_target, "gt_urls": gt_urls}
    elif ground_truth_url is not None:
        eval_config = {"_target_": eval_target, "ground_truth_url": ground_truth_url}
    else:
        raise ValueError("Must specify either 'gt_urls' or 'ground_truth_url'.")

    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)


if __name__ == "__main__":
    run_tests()
