"""
Covers:
- Query normalization
- Filters
- Routing (homepage/search/category/brand/collection/product)
- Multi-GT
- Async lifecycle
- Edge cases
- Parser robustness
- URL decoding
- Boundary conditions
"""

import asyncio
import pytest

from navi_bench.goat.goat_url_match import (
    GoatUrlMatch,
    GoatVerifierResult,
)

BASE = "https://www.goat.com"


# ============================================================
# Helpers
# ============================================================

def _v(gt):
    return GoatUrlMatch(gt_url=gt)


def _match(agent, gt):
    return _v(gt)._urls_match(agent, gt)


# ============================================================
# 1. QUERY NORMALIZATION
# ============================================================

class TestQueryNormalization:

    def test_subset_match(self):
        gt = f"{BASE}/search?query=nike+dunk"
        agent = f"{BASE}/search?query=nike+dunk+low"

        assert _match(agent, gt)[0]

    def test_plural_s(self):
        gt = f"{BASE}/search?query=shoe"
        agent = f"{BASE}/search?query=shoes"

        assert _match(agent, gt)[0]

    def test_plural_ies(self):
        gt = f"{BASE}/search?query=party"
        agent = f"{BASE}/search?query=parties"

        assert _match(agent, gt)[0]

    def test_plural_es(self):
        gt = f"{BASE}/search?query=watch"
        agent = f"{BASE}/search?query=watches"

        assert _match(agent, gt)[0]

    def test_case_insensitive_query(self):
        gt = f"{BASE}/search?query=Nike+Dunk"
        agent = f"{BASE}/search?query=nike+dunk"

        assert _match(agent, gt)[0]

    def test_double_encoded_query(self):
        gt = f"{BASE}/search?query=nike dunk"
        agent = f"{BASE}/search?query=nike%2520dunk"

        assert _match(agent, gt)[0]

    def test_query_mismatch(self):
        gt = f"{BASE}/search?query=nike"
        agent = f"{BASE}/search?query=adidas"

        assert not _match(agent, gt)[0]

    def test_empty_gt_query(self):
        gt = f"{BASE}/search"
        agent = f"{BASE}/search?query=nike"

        assert _match(agent, gt)[0]


# ============================================================
# 2. MULTI VALUE FILTERS
# ============================================================

class TestMultiValueFilters:

    def test_brand_subset(self):
        gt = f"{BASE}/search?query=shoes&brands=nike"

        agent = (
            f"{BASE}/search?query=shoes"
            "&brands=nike,adidas"
        )

        assert _match(agent, gt)[0]

    def test_pipe_separated_filters(self):
        gt = f"{BASE}/search?brands=nike"
        agent = f"{BASE}/search?brands=nike|adidas"

        assert _match(agent, gt)[0]

    def test_double_encoded_filter(self):
        gt = f"{BASE}/search?brands=nike"

        agent = (
            f"{BASE}/search"
            "?brands=nike%252Cadidas"
        )

        assert _match(agent, gt)[0]

    def test_category_subset(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&categories=sneakers"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&categories=sneakers,apparel"
        )

        assert _match(agent, gt)[0]

    def test_gender_mismatch(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&genders=men"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&genders=women"
        )

        assert not _match(agent, gt)[0]

    def test_color_subset(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&colors=black"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&colors=black,white"
        )

        assert _match(agent, gt)[0]

    def test_size_subset(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&sizes=10"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&sizes=10,11"
        )

        assert _match(agent, gt)[0]

    def test_missing_multi_filter(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&brands=nike"
        )

        agent = f"{BASE}/search?query=shoes"

        assert not _match(agent, gt)[0]

    def test_case_insensitive_filters(self):
        gt = f"{BASE}/search?brands=Nike"
        agent = f"{BASE}/search?brands=nike"

        assert _match(agent, gt)[0]

    def test_extra_agent_filters_allowed(self):
        gt = f"{BASE}/search?query=nike"

        agent = (
            f"{BASE}/search"
            "?query=nike"
            "&brands=nike"
            "&colors=black"
        )

        assert _match(agent, gt)[0]


# ============================================================
# 3. BOOLEAN FILTERS
# ============================================================

class TestBooleanFilters:

    def test_instant_ship_match(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&instantShip=true"
        )

        assert _match(gt, gt)[0]

    def test_boolean_case_insensitive(self):
        gt = (
            f"{BASE}/search"
            "?instantShip=true"
        )

        agent = (
            f"{BASE}/search"
            "?instantShip=TRUE"
        )

        assert _match(agent, gt)[0]

    def test_under_retail_mismatch(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&underRetail=true"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&underRetail=false"
        )

        assert not _match(agent, gt)[0]

    def test_in_stock_match(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&inStock=true"
        )

        assert _match(gt, gt)[0]

    def test_sale_mismatch(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&sale=true"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&sale=false"
        )

        assert not _match(agent, gt)[0]

    def test_numeric_boolean_not_true(self):
        gt = (
            f"{BASE}/search"
            "?instantShip=true"
        )

        agent = (
            f"{BASE}/search"
            "?instantShip=1"
        )

        assert not _match(agent, gt)[0]


# ============================================================
# 4. NUMERIC FILTERS
# ============================================================

class TestNumericFilters:

    def test_price_match(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&priceMin=100"
            "&priceMax=200"
        )

        assert _match(gt, gt)[0]

    def test_price_mismatch(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&priceMin=100"
            "&priceMax=200"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&priceMin=150"
            "&priceMax=300"
        )

        assert not _match(agent, gt)[0]

    def test_invalid_price_number(self):
        gt = (
            f"{BASE}/search"
            "?priceMin=100"
        )

        agent = (
            f"{BASE}/search"
            "?priceMin=abc"
        )

        assert not _match(agent, gt)[0]

    def test_release_date_match(self):
        gt = (
            f"{BASE}/search"
            "?query=jordans"
            "&releaseDateStart=20200101"
            "&releaseDateEnd=20231231"
        )

        assert _match(gt, gt)[0]

    def test_release_date_mismatch(self):
        gt = (
            f"{BASE}/search"
            "?query=jordans"
            "&releaseDateStart=20200101"
        )

        agent = (
            f"{BASE}/search"
            "?query=jordans"
            "&releaseDateStart=20220101"
        )

        assert not _match(agent, gt)[0]


# ============================================================
# 5. STRING FILTERS
# ============================================================

class TestStringFilters:

    def test_sort_match(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&sortType=price_low_to_high"
        )

        assert _match(gt, gt)[0]

    def test_sort_mismatch(self):
        gt = (
            f"{BASE}/search"
            "?query=shoes"
            "&sortType=price_low_to_high"
        )

        agent = (
            f"{BASE}/search"
            "?query=shoes"
            "&sortType=most_popular"
        )

        assert not _match(agent, gt)[0]


# ============================================================
# 6. ROUTING (PAGE TYPES)
# ============================================================

class TestRouting:

    def test_homepage_match(self):
        gt = f"{BASE}/"

        assert _match(gt, gt)[0]

    def test_search_match(self):
        gt = f"{BASE}/search?query=nike"

        assert _match(gt, gt)[0]

    def test_collection_match(self):
        gt = f"{BASE}/collections/new-releases"

        assert _match(gt, gt)[0]

    def test_collection_mismatch(self):
        gt = f"{BASE}/collections/new-releases"

        agent = (
            f"{BASE}/collections/best-sellers"
        )

        assert not _match(agent, gt)[0]

    def test_brand_match(self):
        gt = f"{BASE}/brand/nike"

        assert _match(gt, gt)[0]

    def test_brand_mismatch(self):
        gt = f"{BASE}/brand/nike"

        agent = f"{BASE}/brand/adidas"

        assert not _match(agent, gt)[0]

    def test_product_match(self):
        gt = (
            f"{BASE}/sneakers/"
            "air-jordan-1-retro-high-og-chicago-2015"
        )

        assert _match(gt, gt)[0]

    def test_product_mismatch(self):
        gt = (
            f"{BASE}/sneakers/"
            "air-jordan-1-retro-high-og-chicago-2015"
        )

        agent = (
            f"{BASE}/sneakers/"
            "nike-dunk-low-panda"
        )

        assert not _match(agent, gt)[0]

    def test_not_product_when_slug_short(self):
        gt = f"{BASE}/sneakers/dunk-low"

        v = _v(gt)

        parsed = v._parse_url(gt)

        assert parsed["page_type"] != "product"

    def test_category_match(self):
        gt = f"{BASE}/sneakers/running"

        assert _match(gt, gt)[0]

    def test_category_prefix_match(self):
        gt = f"{BASE}/sneakers"

        agent = f"{BASE}/sneakers/running"

        assert _match(agent, gt)[0]

    def test_category_mismatch(self):
        gt = f"{BASE}/sneakers"

        agent = f"{BASE}/apparel"

        assert not _match(agent, gt)[0]


# ============================================================
# 7. IGNORED PARAMS
# ============================================================

class TestIgnoredParams:

    def test_utm_ignored(self):
        gt = f"{BASE}/search?query=nike"

        agent = (
            f"{BASE}/search"
            "?query=nike"
            "&utm_source=google"
            "&fbclid=123"
        )

        assert _match(agent, gt)[0]

    def test_page_number_ignored(self):
        gt = f"{BASE}/search?query=nike"

        agent = (
            f"{BASE}/search"
            "?query=nike"
            "&pageNumber=2"
        )

        assert _match(agent, gt)[0]

    def test_unknown_query_params_ignored(self):
        gt = f"{BASE}/search?query=nike"

        agent = (
            f"{BASE}/search"
            "?query=nike"
            "&randomParam=test"
        )

        assert _match(agent, gt)[0]


# ============================================================
# 8. MULTI GT LOGIC
# ============================================================

class TestMultiGT:

    def test_or_logic(self):
        gt = [
            f"{BASE}/search?query=nike",
            f"{BASE}/search?query=adidas",
        ]

        v = GoatUrlMatch(gt)

        asyncio.run(
            v.update(
                url=f"{BASE}/search?query=adidas"
            )
        )

        result = asyncio.run(v.compute())

        assert result.score == 1.0

    def test_latest_match_evaluated(self):
        gt1 = f"{BASE}/search?query=nike"
        gt2 = f"{BASE}/search?query=adidas"

        v = GoatUrlMatch([gt1, gt2])

        asyncio.run(v.update(url=gt1))
        asyncio.run(v.update(url=gt2))

        result = asyncio.run(
            v.compute_detailed()
        )

        assert result.gt_url == gt2


# ============================================================
# 9. ASYNC LIFECYCLE
# ============================================================

class TestAsync:

    @pytest.mark.asyncio
    async def test_reset(self):
        gt = f"{BASE}/search?query=nike"

        v = GoatUrlMatch(gt)

        await v.update(url=gt)
        await v.reset()

        assert (await v.compute()).score == 0.0

    @pytest.mark.asyncio
    async def test_no_match(self):
        gt = f"{BASE}/search?query=nike"

        v = GoatUrlMatch(gt)

        await v.update(
            url=f"{BASE}/search?query=adidas"
        )

        assert (await v.compute()).score == 0.0


# ============================================================
# 10. EDGE CASES
# ============================================================

class TestEdgeCases:

    def test_empty_url(self):
        v = _v(f"{BASE}/search?query=nike")

        asyncio.run(v.update(url=""))

        assert not v._found_match

    def test_invalid_domain(self):
        v = _v(f"{BASE}/search?query=nike")

        asyncio.run(
            v.update(
                url="https://google.com"
            )
        )

        assert not v._found_match

    def test_malformed(self):
        v = _v(f"{BASE}/search?query=nike")

        asyncio.run(
            v.update(
                url="not-a-url"
            )
        )

        assert not v._found_match


# ============================================================
# 11. COMPUTE OUTPUT
# ============================================================

class TestCompute:

    @pytest.mark.asyncio
    async def test_compute_detailed(self):
        gt = f"{BASE}/search?query=nike"

        v = GoatUrlMatch(gt)

        await v.update(url=gt)

        result = await v.compute_detailed()

        assert isinstance(
            result,
            GoatVerifierResult,
        )

        assert result.match
        assert result.score == 1.0
        assert result.agent_url == gt
        assert result.gt_url == gt
        assert isinstance(result.details, dict)


# ============================================================
# 12. REAL WORLD SCENARIOS
# ============================================================

class TestRealScenario:

    def test_complex_search(self):

        gt = (
            f"{BASE}/search"
            "?query=nike+dunk"
            "&brands=nike"
            "&colors=black"
            "&priceMin=100"
            "&priceMax=300"
            "&instantShip=true"
            "&sortType=price_low_to_high"
        )

        agent = (
            f"{BASE}/search"
            "?query=nike+dunk+low"
            "&brands=nike,adidas"
            "&colors=black,white"
            "&priceMin=100"
            "&priceMax=300"
            "&instantShip=true"
            "&sortType=price_low_to_high"
        )

        match, details = _match(agent, gt)

        assert match, f"Failed with {details}"

    def test_complex_filter_failure(self):

        gt = (
            f"{BASE}/search"
            "?query=nike+dunk"
            "&brands=nike"
            "&colors=black"
        )

        agent = (
            f"{BASE}/search"
            "?query=nike+dunk"
            "&brands=adidas"
            "&colors=white"
        )

        assert not _match(agent, gt)[0]
