"""Redfin URL Match verifier for property search navigation.

This module provides functionality to verify AI agent navigation on Redfin
by comparing the agent's final URL against expected ground truth URLs.

The verifier handles all Redfin URL variations including:
- Multiple location types (city, county, zipcode, neighborhood, school, school-district)
- Multi-region searches via mr= parameter
- Rental vs sale listings (/rentals, /apartments-for-rent)
- Price abbreviations (500k, 2m, 2.5M)
- Square footage formats (750-sqft, 1.2k-sqft, 3-acre)
- Multi-value filters (property-type=house+condo)
- URL-encoded parameters
- Parameter order independence
- Parameter name aliases (max-days-on-market ↔ time-on-market)
- Case insensitivity
- Protocol variations (http/https, with/without www)
- Ignored UI parameters (viewport, no-outline, utm_*, etc.)
- Boolean filters (is-fixer, has-view, air-conditioning)
- Keyword search via remarks filter
- Include filters (include=sold-3mo, include=construction)
- School/walk/transit/bike scores
- Financing types (FHA, VA)
- All amenity filters (basement, pool, parking, etc.)

Merged from l2_redfin_url_match.py (comprehensive normalization) and
l3_redfin_url_match.py (multi-region and location type support).
"""

import re
from typing import TypedDict
from urllib.parse import unquote, urlparse

from beartype import beartype
from loguru import logger
from pydantic import BaseModel

from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import initialize_user_metadata


class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float  # 1.0 if match, 0.0 if no match


class RedfinUrlState:
    """
    Parses and normalizes Redfin URLs for comparison.

    Combines:
    - L3's multi-region and location type support
    - L2's comprehensive parameter normalization
    """

    # Parameters to ignore (UI-only, tracking, don't affect search results)
    # Note: sort is NOT ignored - L3 tests expect sort order to be verified
    IGNORED_PARAMS = {
        "viewport",
        "no-outline",
        "redirect",
        "map_zoom",
        "zoomLevel",
        "v",
        "utm_source",
        "utm_medium",
        "utm_content",
        "utm_campaign",
        "android_merchant_id",
        "myapp_param",
        "referrer",
    }

    # Tolerance for viewport coordinate comparison (degrees)
    VIEWPORT_TOLERANCE = 0.05

    def __init__(self, url: str):
        self.original_url = url
        self.url = self._normalize_url(url)
        self.loc_id = None
        self.loc_type = None
        self.loc_name = None  # For city/neighborhood name comparison
        self.state = None
        self.is_rental = False
        self.regions = set()
        self.filters = {}
        self.viewport = None
        self._parse()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(\n"
            f"    original_url={self.original_url},\n"
            f"    url={self.url},\n"
            f"    loc_id={self.loc_id},\n"
            f"    loc_type={self.loc_type},\n"
            f"    loc_name={self.loc_name},\n"
            f"    state={self.state},\n"
            f"    is_rental={self.is_rental},\n"
            f"    regions={self.regions},\n"
            f"    filters={self.filters},\n"
            f"    viewport={self.viewport},\n"
            ")"
        )

    def _normalize_url(self, url: str) -> str:
        """Normalize URL: lowercase, strip, decode, remove protocol/www."""
        url = url.lower().strip()
        url = unquote(url)
        url = url.replace("http://", "").replace("https://", "").replace("www.", "")
        return url

    def _parse(self):
        """Parse URL into components."""
        parsed = urlparse("http://" + self.url)
        path = parsed.path.rstrip("/")

        # Check for rental listings
        if "/rentals" in path or "/apartments-for-rent" in path:
            self.is_rental = True

        # Parse location from path
        self._parse_location(path)

        # Parse filters
        if "/filter/" in path:
            filter_segment = path.split("/filter/")[-1].strip("/")
            # Remove /rentals suffix if present after filter
            filter_segment = filter_segment.replace("/rentals", "")
            self._parse_filters(filter_segment)

        # Post-process filters for consolidation
        self._consolidate_filters()

    def _parse_location(self, path: str):
        """Extract location information from URL path."""
        # Try each location type pattern
        patterns = [
            (r"/city/(\d+)/([^/]+)/([^/]+)", "city"),
            (r"/neighborhood/(\d+)/([^/]+)/([^/]+)/([^/]+)", "neighborhood"),
            (r"/county/(\d+)/([^/]+)/([^/]+)", "county"),
            (r"/zipcode/(\d+)/([^/]+)/([^/]+)", "zipcode"),
            (r"/school/(\d+)/([^/]+)/([^/]+)", "school"),
            (r"/school-district/(\d+)/([^/]+)/([^/]+)", "school-district"),
            (r"/real-estate-agents/([^/]+)", "real-estate-agents"),
            (r"/home/(\d+)", "home"),
        ]

        for pattern, loc_type in patterns:
            match = re.search(pattern, path)
            if match:
                self.loc_type = loc_type

                if loc_type == "neighborhood":
                    self.loc_id = match.group(1)
                    self.state = match.group(2)
                    city = match.group(3)
                    neighborhood = match.group(4)
                    self.loc_name = f"{city}/{neighborhood}"
                elif loc_type in ("city", "county", "zipcode", "school", "school-district"):
                    self.loc_id = match.group(1)
                    self.state = match.group(2)
                    self.loc_name = match.group(3)
                elif loc_type == "real-estate-agents":
                    self.loc_id = match.group(1)
                    self.loc_name = match.group(1)
                elif loc_type == "home":
                    self.loc_id = match.group(1)
                    self.loc_name = match.group(1)

                self.regions.add(self.loc_id)
                break

    def _parse_filters(self, filter_segment: str):
        """Parse filter segment into normalized key-value pairs."""
        # Pre-process: Remove commas from numeric values
        filter_segment = re.sub(r"(\d),(\d)", r"\1\2", filter_segment)

        parts = filter_segment.split(",")

        for part in parts:
            part = unquote(part.strip())
            if not part:
                continue

            # Check if ignored
            if self._is_ignored(part):
                continue

            # Handle viewport specially
            if part.startswith("viewport="):
                self._parse_viewport(part)
                continue

            # Handle multi-region parameter
            if part.startswith("mr="):
                self._parse_multi_region(part)
                continue

            # Parse key=value or boolean flag
            if "=" in part:
                key, value = part.split("=", 1)
                if not value or not value.strip():
                    continue

                # Normalize key
                key = self._normalize_param_name(key.strip())

                # Handle multi-value filters (e.g., property-type=house+condo)
                if "+" in value:
                    value_parts = value.split("+")
                    normalized_parts = [self._normalize_param_value(key, v.strip()) for v in value_parts]
                    # Sort and deduplicate for order-independent comparison
                    self.filters[key] = tuple(sorted(set(normalized_parts)))
                else:
                    self.filters[key] = self._normalize_param_value(key, value)
            else:
                # Boolean flag
                normalized_flag = self._normalize_param_name(part)
                self.filters[normalized_flag] = "true"

    def _is_ignored(self, part: str) -> bool:
        """Check if parameter should be ignored."""
        param_name = part.split("=", 1)[0]
        return param_name in self.IGNORED_PARAMS

    def _parse_viewport(self, part: str):
        """Parse viewport coordinates."""
        try:
            coords_str = part.split("=", 1)[1]
            self.viewport = [float(x) for x in coords_str.split(":")]
        except (ValueError, IndexError):
            pass

    def _parse_multi_region(self, part: str):
        """Parse multi-region parameter (mr=6:29470+1:30062)."""
        try:
            val = part.split("=", 1)[1]
            mr_regions = val.split("+")
            for r in mr_regions:
                if ":" in r:
                    self.regions.add(r.split(":")[1])
        except (ValueError, IndexError):
            pass

    def _normalize_param_name(self, param: str) -> str:
        """Normalize parameter names to canonical form."""
        param = param.strip().lower()

        aliases = {
            # Time on market variations
            "max-days-on-market": "time-on-market",
            "days-on-market": "time-on-market",
            # Stories variations
            "min-stories": "num-stories-min",
            "max-stories": "num-stories-max",
            "num-stories": "num-stories-min",
            # Waterfront aliases
            "has-waterfront": "water-front",
            "waterfront": "water-front",
            "has-water-front": "water-front",
            # View aliases
            "view": "has-view",
            # Pool aliases
            "has-pool": "pool-type",
            "pool": "pool-type",
            # Garage/parking aliases
            "garage": "has-garage",
            "parking": "has-parking",
            # Elevator aliases
            "elevator": "has-elevator",
            # Washer/dryer aliases
            "has-washer-dryer": "washer-dryer",
            "washer-dryer-hookup": "washer-dryer",
            # Fireplace aliases
            "has-fireplace": "fireplace",
            # Basement aliases
            "has-basement": "basement-type",
            "basement": "basement-type",
            # Pet aliases
            "allows-pets": "pets-allowed",
            "pet-friendly": "pets-allowed",
            "allows-dogs": "dogs-allowed",
            "dog-friendly": "dogs-allowed",
            "allows-cats": "cats-allowed",
            "cat-friendly": "cats-allowed",
            # Furnished aliases
            "furnished": "is-furnished",
            # Fixer-upper aliases
            "fixer-upper": "is-fixer",
            "fixer": "is-fixer",
            # Green home aliases
            "green": "is-green",
            "green-home": "is-green",
            # Guest house aliases
            "has-guest-house": "guest-house",
            # Primary bedroom aliases
            "primary-bedroom-on-main": "primary-bed-on-main",
            "master-on-main": "primary-bed-on-main",
            # Dishwasher aliases
            "dishwasher": "has-dishwasher",
            # ATT fiber aliases
            "att-fiber": "has-att-fiber",
            # Deal aliases
            "special-deal": "has-deal",
            "deal": "has-deal",
            # Laundry aliases
            "laundry-facility": "has-laundry-facility",
            "laundry-hookups": "has-laundry-hookups",
            # Virtual tour aliases
            "virtual-tour": "has-virtual-tour",
            # Short term lease aliases
            "short-term-lease": "has-short-term-lease",
            # Accessible aliases
            "accessible": "is-accessible",
            # Senior living aliases
            "senior-living": "is-senior-living",
            # Income restricted aliases
            "income-restricted": "is-income-restricted",
        }
        return aliases.get(param, param)

    def _normalize_param_value(self, param: str, value: str) -> str:
        """Normalize parameter values (prices, sqft, time, etc.)."""
        value = value.strip().lower()
        value = unquote(value)

        # Handle price values
        if "price" in param and "sqft" not in param:
            value = value.replace(",", "")

            if value.endswith("m"):
                try:
                    num = float(value[:-1])
                    return str(int(num * 1000000))
                except ValueError:
                    pass
            elif value.endswith("k"):
                try:
                    num = float(value[:-1])
                    return str(int(num * 1000))
                except ValueError:
                    pass
            return value

        # Handle square footage values
        if "sqft" in param or "lot-size" in param:
            # Remove suffixes
            value = value.replace("-sqft", "").replace("sqft", "")
            value = value.replace("-acre", "").replace("acre", "")

            if value.endswith("k"):
                try:
                    num = float(value[:-1])
                    return str(int(num * 1000))
                except ValueError:
                    pass
            if value.endswith("m"):
                try:
                    num = float(value[:-1])
                    return str(int(num * 1000000))
                except ValueError:
                    pass
            return value

        # Handle price-per-sqft values
        if "price-per-sqft" in param:
            value = value.replace("-sqft", "").replace("sqft", "")
            if value.endswith("k"):
                try:
                    num = float(value[:-1])
                    return str(int(num * 1000))
                except ValueError:
                    pass
            return value

        # Handle time value normalization
        if "time" in param or "market" in param or "days" in param or "reduced" in param:
            time_map = {
                "1wk": "7days",
                "2wk": "14days",
                "3wk": "21days",
                "4wk": "28days",
                "1mo": "30days",
                "2mo": "60days",
                "3mo": "90days",
                "6mo": "180days",
                "1yr": "365days",
            }
            if value in time_map:
                return time_map[value]

        # Handle move-in-date normalization
        if "move-in-date" in param:
            parts = value.split("/")
            if len(parts) == 3:
                try:
                    month, day, year = parts
                    month = str(int(month))
                    day = str(int(day))
                    return f"{month}/{day}/{year}"
                except ValueError:
                    pass
            return value

        return value

    def _consolidate_filters(self):
        """Post-process filters for consolidation (beds, baths, stories)."""
        filters = self.filters

        # Consolidate beds=N to min-beds=N, max-beds=N
        if "beds" in filters:
            beds_val = filters.pop("beds")
            filters["min-beds"] = beds_val
            filters["max-beds"] = beds_val

        # Consolidate baths=N to min-baths=N, max-baths=N
        if "baths" in filters:
            baths_val = filters.pop("baths")
            filters["min-baths"] = baths_val
            filters["max-baths"] = baths_val

        # Consolidate stories when min=max
        min_stories = filters.get("num-stories-min")
        max_stories = filters.get("num-stories-max")

        if min_stories is not None and max_stories is not None:
            if min_stories == max_stories:
                filters.pop("num-stories-min")
                filters.pop("num-stories-max")
                filters["stories"] = min_stories
        elif max_stories is not None and min_stories is None:
            filters.pop("num-stories-max")
            filters["stories"] = max_stories
        elif min_stories is not None and max_stories is None:
            filters.pop("num-stories-min")
            filters["min-stories"] = min_stories

    def matches(self, ground_truth: "RedfinUrlState") -> dict:
        """
        Compare this URL state against ground truth.

        Returns dict with 'match' (bool) and 'evidence' (list of mismatch reasons).
        """
        evidence = []
        is_match = True

        # Compare region sets (strict ID matching as per L3's design)
        # This prevents false positives from redirect confusion
        if self.regions != ground_truth.regions:
            is_match = False
            evidence.append(f"Region mismatch: {self.regions} vs {ground_truth.regions}")

        # Compare location type (for single-region, as safety check)
        if len(self.regions) == 1 and len(ground_truth.regions) == 1:
            if self.loc_type != ground_truth.loc_type:
                is_match = False
                evidence.append(f"Location type mismatch: '{self.loc_type}' vs '{ground_truth.loc_type}'")

        # Compare rental status
        if self.is_rental != ground_truth.is_rental:
            is_match = False
            evidence.append(f"Rental status mismatch: {self.is_rental} vs {ground_truth.is_rental}")

        # Compare viewport if ground truth specifies one
        if ground_truth.viewport:
            if not self.viewport:
                is_match = False
                evidence.append("Viewport missing in agent URL")
            else:
                diffs = [abs(a - b) for a, b in zip(self.viewport, ground_truth.viewport)]
                if any(d > self.VIEWPORT_TOLERANCE for d in diffs):
                    is_match = False
                    evidence.append(
                        f"Viewport too far: max diff {max(diffs):.4f} > tolerance {self.VIEWPORT_TOLERANCE}"
                    )

        # Compare filters
        # Check for missing filters
        for gt_key, gt_value in ground_truth.filters.items():
            agent_value = self.filters.get(gt_key)

            if agent_value is None:
                is_match = False
                evidence.append(f"Missing filter: '{gt_key}'")
            elif agent_value != gt_value:
                is_match = False
                evidence.append(f"Filter value mismatch '{gt_key}': '{agent_value}' vs '{gt_value}'")

        # Check for extra filters
        for agent_key in self.filters:
            if agent_key not in ground_truth.filters:
                is_match = False
                evidence.append(f"Extra filter: '{agent_key}'")

        return {"match": is_match, "evidence": evidence}


@beartype
class RedfinUrlMatch(BaseMetric):
    """
    Comprehensive Redfin URL verifier combining multi-region support,
    location type handling, and robust parameter normalization.

    Supports two input formats for gt_urls:
    1. list[list[str]]: AND -> OR logic
       - First level (outer list) = "AND" conditions (all must be covered)
       - Second level (inner list) = "OR" conditions (at least one must match)
    2. str | list[str]: Legacy format, treated as a single OR group
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

        self._intermediate_url_to_state: dict[str, RedfinUrlState] = {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(gt_urls={self.gt_urls})"

    async def reset(self) -> None:
        """Reset the match state for new evaluation."""
        self._intermediate_url_to_state = {}

    async def update(self, **kwargs) -> None:
        """Update with new URL to check against ground truth."""
        inputs: InputDict = kwargs
        url = inputs.get("url", "")

        if not url:
            logger.info("RedfinUrlMatch.update: Empty URL provided")
            return

        if url not in self._intermediate_url_to_state:
            state = RedfinUrlState(url)
            self._intermediate_url_to_state[url] = state
            logger.info(f"RedfinUrlMatch.update: {url=}, {state=}")

    async def compute(self) -> FinalResult:
        """
        Compute final score based on AND -> OR matching logic.

        Score = (number of AND conditions covered) / (total AND conditions)

        For each AND condition (outer list), at least one OR alternative (inner list)
        must be matched by some intermediate URL.
        """
        n_covered = 0

        # First level of iteration: all elements in self.gt_urls are required to be covered
        for i, candidate_gt_urls in enumerate(self.gt_urls):
            # Second level of iteration: good if any element in candidate_gt_states is covered
            is_covered = False
            for j, gt_url in enumerate(candidate_gt_urls):
                gt_state = RedfinUrlState(gt_url)
                logger.info(f"RedfinUrlMatch.compute: gt_urls[{i}][{j}]={gt_url}, {gt_state=}")

                for intermediate_url, intermediate_state in self._intermediate_url_to_state.items():
                    result = intermediate_state.matches(gt_state)
                    if result["match"]:
                        is_covered = True
                        n_covered += 1
                        logger.info(
                            f"RedfinUrlMatch.compute gt_urls[{i}][{j}] is covered by "
                            f"intermediate_url: {intermediate_url}"
                        )
                        break
                if is_covered:
                    break
                else:
                    logger.info(f"RedfinUrlMatch.compute gt_urls[{i}][{j}] is not covered by any intermediate_url")

        n_required = len(self.gt_urls)
        score = n_covered / max(n_required, 1)
        logger.info(f"RedfinUrlMatch.compute: Covered {n_covered} out of {n_required} required URLs, score={score}")
        return FinalResult(score=score)


def generate_task_config(
    task: str,
    gt_urls: list[list[str]] | list[str],
    location: str,
    timezone: str,
    timestamp: int | None = None,
    url: str = "https://www.redfin.com",
) -> BaseTaskConfig:
    """Generate task configuration for Redfin URL matching.

    Args:
        task: The task description.
        gt_urls: Ground truth URLs. Can be:
            - list[list[str]]: AND -> OR logic (all outer elements required,
              any inner element satisfies each requirement)
            - list[str]: Flat list treated as single OR group (legacy)
        location: User location string.
        timezone: User timezone string.
        timestamp: Optional timestamp override.
        url: Starting URL for the task.
    """
    # Convert legacy flat list[str] to list[list[str]] (single OR group)
    if gt_urls and isinstance(gt_urls[0], str):
        gt_urls = [gt_urls]
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    eval_target = get_import_path(RedfinUrlMatch)
    eval_config = {"_target_": eval_target, "gt_urls": gt_urls}
    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)


# ============================================================================
# COMPREHENSIVE TEST SUITE
# ============================================================================

if __name__ == "__main__":
    import asyncio

    print("=" * 80)
    print("REDFIN URL VERIFIER - MERGED IMPLEMENTATION TEST SUITE")
    print("=" * 80)

    async def run_tests():
        """Run comprehensive tests covering all CSV case patterns."""

        total_tests = 0
        passed_tests = 0

        # Helper function for single URL tests (legacy format)
        async def test_case(name: str, gt_url: str, test_url: str, expected: float):
            nonlocal total_tests, passed_tests
            total_tests += 1
            evaluator = RedfinUrlMatch(gt_urls=gt_url)
            await evaluator.reset()
            await evaluator.update(url=test_url)
            result = await evaluator.compute()
            if result.score == expected:
                print(f"✅ {name}")
                passed_tests += 1
            else:
                print(f"❌ {name} (expected {expected}, got {result.score})")

        # Helper function for AND -> OR tests
        async def test_and_or(name: str, gt_urls: list[list[str]], test_urls: list[str], expected: float):
            nonlocal total_tests, passed_tests
            total_tests += 1
            evaluator = RedfinUrlMatch(gt_urls=gt_urls)
            await evaluator.reset()
            for url in test_urls:
                await evaluator.update(url=url)
            result = await evaluator.compute()
            if abs(result.score - expected) < 0.001:
                print(f"✅ {name}")
                passed_tests += 1
            else:
                print(f"❌ {name} (expected {expected}, got {result.score})")

        # ================================================================
        # CATEGORY 1: Basic Location Types
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 1: LOCATION TYPES")
        print("=" * 60)

        # City
        await test_case(
            "City URL match",
            "https://www.redfin.com/city/29470/IL/Chicago/filter/property-type=condo",
            "https://www.redfin.com/city/29470/IL/Chicago/filter/property-type=condo",
            1.0,
        )

        # City with different ID - L3 expects strict ID matching (should fail)
        # This prevents false positives from redirect confusion
        await test_case(
            "City URL different ID (strict matching)",
            "https://www.redfin.com/city/29470/IL/Chicago/filter/property-type=condo",
            "https://www.redfin.com/city/99999/IL/Chicago/filter/property-type=condo",
            0.0,
        )

        # Neighborhood
        await test_case(
            "Neighborhood URL match",
            "https://www.redfin.com/neighborhood/219258/NY/New-York/Brooklyn/filter/min-price=500k",
            "https://www.redfin.com/neighborhood/219258/NY/New-York/Brooklyn/filter/min-price=500k",
            1.0,
        )

        # County
        await test_case(
            "County URL match",
            "https://www.redfin.com/county/2362/PA/Allegheny-County/filter/property-type=house",
            "https://www.redfin.com/county/2362/PA/Allegheny-County/filter/property-type=house",
            1.0,
        )

        # ================================================================
        # CATEGORY 2: Price Normalization
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 2: PRICE NORMALIZATION")
        print("=" * 60)

        await test_case(
            "Price: 500k = 500000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=500000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=500k",
            1.0,
        )

        await test_case(
            "Price: 1.5M = 1500000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=1500000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=1.5M",
            1.0,
        )

        await test_case(
            "Price: 2m = 2000000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=2000000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=2m",
            1.0,
        )

        # ================================================================
        # CATEGORY 3: Square Footage Normalization
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 3: SQUARE FOOTAGE")
        print("=" * 60)

        await test_case(
            "Sqft: 3k-sqft = 3000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-sqft=3000",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-sqft=3k-sqft",
            1.0,
        )

        await test_case(
            "Sqft: 1.6k-sqft = 1600",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-sqft=1600",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-sqft=1.6k-sqft",
            1.0,
        )

        # ================================================================
        # CATEGORY 4: Time Normalization
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 4: TIME VALUES")
        print("=" * 60)

        await test_case(
            "Time: 1wk = 7days",
            "https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=7days",
            "https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=1wk",
            1.0,
        )

        await test_case(
            "Time: max-days-on-market alias",
            "https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=7days",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-days-on-market=1wk",
            1.0,
        )

        # ================================================================
        # CATEGORY 5: Multi-Value Filters
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 5: MULTI-VALUE FILTERS")
        print("=" * 60)

        await test_case(
            "Multi-value: order independence",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house+condo",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=condo+house",
            1.0,
        )

        await test_case(
            "Multi-value: three values",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house+condo+townhouse",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=townhouse+house+condo",
            1.0,
        )

        await test_case(
            "Multi-value: subset should fail",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house+condo",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house",
            0.0,
        )

        # ================================================================
        # CATEGORY 6: Rentals vs Sales
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 6: RENTALS VS SALES")
        print("=" * 60)

        await test_case(
            "Rental URL match",
            "https://www.redfin.com/city/1/WA/Seattle/rentals/filter/max-price=2k",
            "https://www.redfin.com/city/1/WA/Seattle/rentals/filter/max-price=2k",
            1.0,
        )

        await test_case(
            "Rental vs sale mismatch",
            "https://www.redfin.com/city/1/WA/Seattle/rentals/filter/max-price=2k",
            "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=2k",
            0.0,
        )

        await test_case(
            "apartments-for-rent pattern",
            "https://www.redfin.com/city/1/WA/Seattle/apartments-for-rent/filter/min-beds=2",
            "https://www.redfin.com/city/1/WA/Seattle/rentals/filter/min-beds=2",
            1.0,
        )

        # ================================================================
        # CATEGORY 7: Case Insensitivity
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 7: CASE INSENSITIVITY")
        print("=" * 60)

        await test_case(
            "Uppercase URL",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house",
            "HTTPS://WWW.REDFIN.COM/CITY/1/WA/SEATTLE/FILTER/PROPERTY-TYPE=HOUSE",
            1.0,
        )

        await test_case(
            "Mixed case",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house",
            "https://www.Redfin.com/City/1/Wa/Seattle/Filter/Property-Type=House",
            1.0,
        )

        # ================================================================
        # CATEGORY 8: Parameter Aliases
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 8: PARAMETER ALIASES")
        print("=" * 60)

        await test_case(
            "Waterfront alias",
            "https://www.redfin.com/city/1/WA/Seattle/filter/water-front",
            "https://www.redfin.com/city/1/WA/Seattle/filter/has-waterfront",
            1.0,
        )

        await test_case(
            "Pool alias",
            "https://www.redfin.com/city/1/WA/Seattle/filter/pool-type=private",
            "https://www.redfin.com/city/1/WA/Seattle/filter/has-pool=private",
            1.0,
        )

        await test_case(
            "Basement alias",
            "https://www.redfin.com/city/1/WA/Seattle/filter/basement-type=finished",
            "https://www.redfin.com/city/1/WA/Seattle/filter/has-basement=finished",
            1.0,
        )

        # ================================================================
        # CATEGORY 9: Ignored Parameters
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 9: IGNORED PARAMETERS")
        print("=" * 60)

        await test_case(
            "Viewport ignored",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            "https://www.redfin.com/city/1/WA/Seattle/filter/viewport=47:-122:48:-121,min-beds=3",
            1.0,
        )

        await test_case(
            "Sort is verified (extra sort fails)",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,sort=hi-price",
            0.0,
        )

        await test_case(
            "Sort matches when both have it",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,sort=lo-price",
            "https://www.redfin.com/city/1/WA/Seattle/filter/sort=lo-price,min-beds=3",
            1.0,
        )

        await test_case(
            "no-outline ignored",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,no-outline",
            1.0,
        )

        # ================================================================
        # CATEGORY 10: Filter Order Independence
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 10: FILTER ORDER")
        print("=" * 60)

        await test_case(
            "Reversed filter order",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,max-price=500k,property-type=house",
            "https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house,max-price=500k,min-beds=3",
            1.0,
        )

        # ================================================================
        # CATEGORY 11: CSV Test Cases (Sample)
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 11: CSV SAMPLE CASES")
        print("=" * 60)

        # L1 CSV case
        await test_case(
            "L1: New Orleans price filter",
            "https://www.redfin.com/city/14233/LA/New-Orleans/filter/max-price=225k",
            "https://www.redfin.com/city/14233/LA/New-Orleans/filter/max-price=225000",
            1.0,
        )

        # L2 CSV case
        await test_case(
            "L2: Chicago rental with AT&T fiber",
            "https://www.redfin.com/city/29470/IL/Chicago/rentals/filter/min-price=800,max-price=1.5k,min-beds=2,min-baths=1,air-conditioning,has-att-fiber",
            "https://www.redfin.com/city/29470/IL/Chicago/rentals/filter/min-price=800,max-price=1500,min-beds=2,min-baths=1,air-conditioning,has-att-fiber",
            1.0,
        )

        # L3 CSV case with sold filter
        await test_case(
            "L3: Portland sold listings",
            "https://www.redfin.com/city/30772/OR/Portland/filter/min-baths=2,include=sold-1mo",
            "https://www.redfin.com/city/30772/OR/Portland/filter/include=sold-1mo,min-baths=2",
            1.0,
        )

        # Complex case with school ratings
        await test_case(
            "School rating filter",
            "https://www.redfin.com/city/30794/TX/Dallas/rentals/filter/school-rating=4,school-types=elementary+middle+high",
            "https://www.redfin.com/city/30794/TX/Dallas/rentals/filter/school-types=high+elementary+middle,school-rating=4",
            1.0,
        )

        # ================================================================
        # CATEGORY 12: Negative Cases
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 12: NEGATIVE CASES")
        print("=" * 60)

        await test_case(
            "Wrong city",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            "https://www.redfin.com/city/1/WA/Bellevue/filter/min-beds=3",
            0.0,
        )

        await test_case(
            "Wrong state",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            "https://www.redfin.com/city/1/CA/Seattle/filter/min-beds=3",
            0.0,
        )

        await test_case(
            "Missing filter",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,max-price=500k",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            0.0,
        )

        await test_case(
            "Extra filter",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,max-price=500k",
            0.0,
        )

        await test_case(
            "Wrong filter value",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4",
            0.0,
        )

        # ================================================================
        # CATEGORY 13: AND -> OR Logic
        # ================================================================
        print("\n" + "=" * 60)
        print("CATEGORY 13: AND -> OR LOGIC")
        print("=" * 60)

        # Single AND with single OR (basic case)
        await test_and_or(
            "AND-OR: Single requirement, single option - match",
            gt_urls=[["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"]],
            test_urls=["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
            expected=1.0,
        )

        await test_and_or(
            "AND-OR: Single requirement, single option - no match",
            gt_urls=[["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"]],
            test_urls=["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4"],
            expected=0.0,
        )

        # Single AND with multiple ORs
        await test_and_or(
            "AND-OR: Single requirement, multiple options - first matches",
            gt_urls=[
                [
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4",
                ]
            ],
            test_urls=["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
            expected=1.0,
        )

        await test_and_or(
            "AND-OR: Single requirement, multiple options - second matches",
            gt_urls=[
                [
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4",
                ]
            ],
            test_urls=["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4"],
            expected=1.0,
        )

        await test_and_or(
            "AND-OR: Single requirement, multiple options - none matches",
            gt_urls=[
                [
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4",
                ]
            ],
            test_urls=["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=5"],
            expected=0.0,
        )

        # Multiple ANDs, each with single OR
        await test_and_or(
            "AND-OR: Two requirements, both covered",
            gt_urls=[
                ["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
                ["https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500k"],
            ],
            test_urls=[
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                "https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500000",
            ],
            expected=1.0,
        )

        await test_and_or(
            "AND-OR: Two requirements, only first covered",
            gt_urls=[
                ["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
                ["https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500k"],
            ],
            test_urls=["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
            expected=0.5,
        )

        await test_and_or(
            "AND-OR: Two requirements, only second covered",
            gt_urls=[
                ["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
                ["https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500k"],
            ],
            test_urls=["https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500000"],
            expected=0.5,
        )

        await test_and_or(
            "AND-OR: Two requirements, none covered",
            gt_urls=[
                ["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
                ["https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500k"],
            ],
            test_urls=["https://www.redfin.com/city/3/NY/New-York/filter/min-beds=2"],
            expected=0.0,
        )

        # Multiple ANDs with multiple ORs
        await test_and_or(
            "AND-OR: Two requirements with alternatives, both covered",
            gt_urls=[
                [
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                    "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4",
                ],
                [
                    "https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500k",
                    "https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=600k",
                ],
            ],
            test_urls=[
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4",
                "https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=600000",
            ],
            expected=1.0,
        )

        # Three requirements
        await test_and_or(
            "AND-OR: Three requirements, all covered",
            gt_urls=[
                ["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
                ["https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500k"],
                ["https://www.redfin.com/city/3/NY/New-York/filter/property-type=condo"],
            ],
            test_urls=[
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                "https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500000",
                "https://www.redfin.com/city/3/NY/New-York/filter/property-type=condo",
            ],
            expected=1.0,
        )

        await test_and_or(
            "AND-OR: Three requirements, two covered",
            gt_urls=[
                ["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"],
                ["https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500k"],
                ["https://www.redfin.com/city/3/NY/New-York/filter/property-type=condo"],
            ],
            test_urls=[
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                "https://www.redfin.com/city/2/CA/San-Francisco/filter/max-price=500000",
            ],
            expected=2.0 / 3.0,
        )

        # Legacy format compatibility
        await test_and_or(
            "Legacy: flat list treated as single OR group",
            gt_urls=[
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3",
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4",
            ],
            test_urls=["https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4"],
            expected=1.0,
        )

        # ================================================================
        # FINAL RESULTS
        # ================================================================
        print("\n" + "=" * 80)
        print("FINAL RESULTS")
        print("=" * 80)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests / total_tests) * 100:.1f}%")
        print("=" * 80)

        if passed_tests == total_tests:
            print("\n🎉 ALL TESTS PASSED!")
        else:
            print(f"\n⚠️  {total_tests - passed_tests} test(s) failed.")

    asyncio.run(run_tests())
