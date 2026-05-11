"""
Production-grade Pytest suite for StockxUrlMatch.

Covers:
- Query normalization
- Filters
- Attributes
- Routing (search/category/brand/browse)
- Multi-GT
- Async lifecycle
- Edge cases
"""

import pytest
import asyncio

from navi_bench.stockx.stockx_url_match import (
    StockxUrlMatch,
    StockxVerifierResult,
)

BASE = "https://www.stockx.com"


# ============================================================
# Helpers
# ============================================================

def _v(gt):
    return StockxUrlMatch(gt_url=gt)


def _match(agent, gt):
    return _v(gt)._urls_match(agent, gt)


# ============================================================
# 1. QUERY NORMALIZATION
# ============================================================

class TestQueryNormalization:

    def test_subset_match(self):
        gt = f"{BASE}/search?s=nike+dunk"
        agent = f"{BASE}/search?s=nike+dunk+low"
        assert _match(agent, gt)[0]

    def test_plural_s(self):
        gt = f"{BASE}/search?s=shoe"
        agent = f"{BASE}/search?s=shoes"
        assert _match(agent, gt)[0]

    def test_plural_ies(self):
        gt = f"{BASE}/search?s=party"
        agent = f"{BASE}/search?s=parties"
        assert _match(agent, gt)[0]

    def test_separator_variants(self):
        gt = f"{BASE}/search?s=nike-dunk"
        agent = f"{BASE}/search?s=nike+dunk"
        assert _match(agent, gt)[0]

    def test_query_mismatch(self):
        gt = f"{BASE}/search?s=nike"
        agent = f"{BASE}/search?s=adidas"
        assert not _match(agent, gt)[0]


# ============================================================
# 2. PRICE FILTERS
# ============================================================

class TestPrice:

    def test_exact_match(self):
        gt = f"{BASE}/search?s=shoes&lowest-ask-range=100-200"
        assert _match(gt, gt)[0]

    def test_price_mismatch(self):
        gt = f"{BASE}/search?s=shoes&lowest-ask-range=100-200"
        agent = f"{BASE}/search?s=shoes&lowest-ask-range=150-300"
        assert not _match(agent, gt)[0]


# ============================================================
# 3. BOOLEAN FILTERS
# ============================================================

class TestBooleanFilters:

    def test_available_now(self):
        gt = f"{BASE}/search?s=shoes&available-now=true"
        assert _match(gt, gt)[0]

    def test_xpress_ship_mismatch(self):
        gt = f"{BASE}/search?s=shoes&xpress-ship=true"
        agent = f"{BASE}/search?s=shoes&xpress-ship=false"
        assert not _match(agent, gt)[0]


# ============================================================
# 4. MULTI VALUE FILTERS
# ============================================================

class TestMultiFilters:

    def test_brand_subset(self):
        gt = f"{BASE}/search?s=shoes&brand=nike"
        agent = f"{BASE}/search?s=shoes&brand=nike,adidas"
        assert _match(agent, gt)[0]

    def test_gender_mismatch(self):
        gt = f"{BASE}/search?s=shoes&gender=men"
        agent = f"{BASE}/search?s=shoes&gender=women"
        assert not _match(agent, gt)[0]

    def test_color_subset(self):
        gt = f"{BASE}/search?s=shoes&color=black"
        agent = f"{BASE}/search?s=shoes&color=black,white"
        assert _match(agent, gt)[0]


# ============================================================
# 5. ATTRIBUTE MATCHING
# ============================================================

class TestAttributes:

    def test_subset(self):
        gt = f"{BASE}/search?s=shoes&size=10"
        agent = f"{BASE}/search?s=shoes&size=10,11"
        assert _match(agent, gt)[0]

    def test_missing_attribute(self):
        gt = f"{BASE}/search?s=shoes&size=10"
        agent = f"{BASE}/search?s=shoes"
        assert not _match(agent, gt)[0]

    def test_attribute_mismatch(self):
        gt = f"{BASE}/search?s=shoes&size=10"
        agent = f"{BASE}/search?s=shoes&size=9"
        assert not _match(agent, gt)[0]


# ============================================================
# 6. ROUTING (PAGE TYPES)
# ============================================================

class TestRouting:

    def test_search_match(self):
        gt = f"{BASE}/search?s=nike"
        assert _match(gt, gt)[0]

    def test_category_match(self):
        gt = f"{BASE}/category/sneakers"
        assert _match(gt, gt)[0]

    def test_category_mismatch(self):
        gt = f"{BASE}/category/sneakers"
        agent = f"{BASE}/category/apparel"
        assert not _match(agent, gt)[0]

    def test_brand_match(self):
        gt = f"{BASE}/brands/nike"
        assert _match(gt, gt)[0]

    def test_brand_mismatch(self):
        gt = f"{BASE}/brands/nike"
        agent = f"{BASE}/brands/adidas"
        assert not _match(agent, gt)[0]

    def test_browse_match(self):
        gt = f"{BASE}/browse/popular"
        assert _match(gt, gt)[0]

    def test_browse_mismatch(self):
        gt = f"{BASE}/browse/popular"
        agent = f"{BASE}/browse/new"
        assert not _match(agent, gt)[0]


# ============================================================
# 7. UNKNOWN URL TYPE
# ============================================================

class TestUnknownType:

    def test_unknown_path(self):
        gt = f"{BASE}/unknown/path"
        v = _v(gt)

        match, details = v._urls_match(gt, gt)

        assert not match
        assert "Unknown StockX URL type" in details["mismatches"]


# ============================================================
# 8. MULTI-GT LOGIC
# ============================================================

class TestMultiGT:

    def test_or_logic(self):
        gt = [
            f"{BASE}/search?s=nike",
            f"{BASE}/search?s=adidas",
        ]

        v = StockxUrlMatch(gt)

        asyncio.run(v.update(url=f"{BASE}/search?s=adidas"))
        result = asyncio.run(v.compute())

        assert result.score == 1.0

    def test_first_match_sticks(self):
        gt1 = f"{BASE}/search?s=nike"
        gt2 = f"{BASE}/search?s=adidas"

        v = StockxUrlMatch([gt1, gt2])

        asyncio.run(v.update(url=gt1))
        asyncio.run(v.update(url=gt2))

        result = asyncio.run(v.compute_detailed())

        assert result.gt_url == gt1


# ============================================================
# 9. ASYNC LIFECYCLE
# ============================================================

class TestAsync:

    @pytest.mark.asyncio
    async def test_reset(self):
        gt = f"{BASE}/search?s=nike"
        v = StockxUrlMatch(gt)

        await v.update(url=gt)
        await v.reset()

        assert (await v.compute()).score == 0.0

    @pytest.mark.asyncio
    async def test_no_match(self):
        gt = f"{BASE}/search?s=nike"
        v = StockxUrlMatch(gt)

        await v.update(url=f"{BASE}/search?s=adidas")
        assert (await v.compute()).score == 0.0


# ============================================================
# 10. EDGE CASES
# ============================================================

class TestEdgeCases:

    def test_empty_url(self):
        v = _v(f"{BASE}/search?s=nike")
        asyncio.run(v.update(url=""))
        assert not v._found_match

    def test_invalid_domain(self):
        v = _v(f"{BASE}/search?s=nike")
        asyncio.run(v.update(url="https://google.com"))
        assert not v._found_match

    def test_malformed(self):
        v = _v(f"{BASE}/search?s=nike")
        asyncio.run(v.update(url="not-a-url"))
        assert not v._found_match


# ============================================================
# 11. COMPUTE OUTPUT
# ============================================================

class TestCompute:

    @pytest.mark.asyncio
    async def test_compute_detailed(self):
        gt = f"{BASE}/search?s=nike"
        v = StockxUrlMatch(gt)

        await v.update(url=gt)
        result = await v.compute_detailed()

        assert isinstance(result, StockxVerifierResult)
        assert result.match
        assert result.score == 1.0
        assert result.agent_url == gt
        assert result.gt_url == gt
        assert isinstance(result.details, dict)


# ============================================================
# 12. REAL WORLD SCENARIO
# ============================================================

class TestRealScenario:

    def test_complex_search(self):
        gt = (
            f"{BASE}/search?s=nike+dunk"
            "&brand=nike&color=black"
            "&lowest-ask-range=100-300"
            "&available-now=true"
        )

        agent = (
            f"{BASE}/search?s=nike+dunk+low"
            "&brand=nike,adidas&color=black,white"
            "&lowest-ask-range=100-300"
            "&available-now=true"
        )

        match, details = _match(agent, gt)

        assert match, f"Failed with {details}"
