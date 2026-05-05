"""
Production-grade Pytest suite for EbayUrlMatch.

High coverage across:
- Parsing
- Matching logic
- Filters
- Attributes
- Routing
- Edge cases
- Async lifecycle
"""

import pytest
import asyncio

from navi_bench.ebay.ebay_url_match import (
    EbayUrlMatch,
    EbayVerifierResult,
)

BASE = "https://www.ebay.com"


# ============================================================
# Helpers
# ============================================================

def _v(gt):
    return EbayUrlMatch(gt_url=gt)


def _match(agent, gt):
    return _v(gt)._urls_match(agent, gt)


def _parse(url):
    return _v(f"{BASE}/sch/i.html?_nkw=test")._parse_search_url(url)


# ============================================================
# 1. QUERY NORMALIZATION
# ============================================================

class TestQueryNormalization:

    def test_subset_match(self):
        gt = f"{BASE}/sch/i.html?_nkw=gold+ring"
        agent = f"{BASE}/sch/i.html?_nkw=gold+diamond+ring"
        assert _match(agent, gt)[0]

    def test_plural_s(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring"
        agent = f"{BASE}/sch/i.html?_nkw=rings"
        assert _match(agent, gt)[0]

    def test_plural_ies(self):
        gt = f"{BASE}/sch/i.html?_nkw=party"
        agent = f"{BASE}/sch/i.html?_nkw=parties"
        assert _match(agent, gt)[0]

    def test_plural_es(self):
        gt = f"{BASE}/sch/i.html?_nkw=box"
        agent = f"{BASE}/sch/i.html?_nkw=boxes"
        assert _match(agent, gt)[0]

    def test_stopwords_removed(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring"
        agent = f"{BASE}/sch/i.html?_nkw=the+ring+for+men"
        assert _match(agent, gt)[0]

    def test_separator_variants(self):
        gt = f"{BASE}/sch/i.html?_nkw=gold-ring"
        agent = f"{BASE}/sch/i.html?_nkw=gold+ring"
        assert _match(agent, gt)[0]

    def test_query_mismatch(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring"
        agent = f"{BASE}/sch/i.html?_nkw=watch"
        assert not _match(agent, gt)[0]


# ============================================================
# 2. PRICE + TOLERANCE
# ============================================================

class TestPrice:

    def test_exact_match(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&_udlo=10&_udhi=50"
        assert _match(gt, gt)[0]

    def test_tolerance_pass(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&_udlo=10"
        agent = f"{BASE}/sch/i.html?_nkw=ring&_udlo=10.001"
        assert _match(agent, gt)[0]

    def test_tolerance_fail(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&_udlo=10"
        agent = f"{BASE}/sch/i.html?_nkw=ring&_udlo=11"
        assert not _match(agent, gt)[0]


# ============================================================
# 3. FULL FILTER COVERAGE
# ============================================================

class TestFilters:

    def test_all_filters_match(self):
        gt = (
            f"{BASE}/sch/i.html?_nkw=ring"
            "&LH_Auction=true&LH_BIN=true"
            "&LH_FS=true&LH_LPickup=true"
            "&LH_Savings=true&LH_AS=true"
            "&LH_FR=true&LH_RPA=true"
            "&LH_PrefLoc=1&_sop=10"
        )
        assert _match(gt, gt)[0]

    def test_filter_mismatch(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&LH_FS=true"
        agent = f"{BASE}/sch/i.html?_nkw=ring&LH_FS=false"

        match, details = _match(agent, gt)
        assert not match
        assert "free_shipping mismatch" in details["mismatches"]

    def test_location_mismatch(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&LH_PrefLoc=1"
        agent = f"{BASE}/sch/i.html?_nkw=ring&LH_PrefLoc=2"
        assert not _match(agent, gt)[0]

    def test_sort_mismatch(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&_sop=10"
        agent = f"{BASE}/sch/i.html?_nkw=ring&_sop=12"
        assert not _match(agent, gt)[0]


# ============================================================
# 4. ATTRIBUTE MATCHING
# ============================================================

class TestAttributes:

    def test_subset(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&Brand=Apple"
        agent = f"{BASE}/sch/i.html?_nkw=ring&Brand=Apple,Samsung"
        assert _match(agent, gt)[0]

    def test_multi_value_pipe(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&Brand=Apple|Samsung"
        agent = f"{BASE}/sch/i.html?_nkw=ring&Brand=Apple|Samsung|Sony"
        assert _match(agent, gt)[0]

    def test_missing_attribute(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&Brand=Apple"
        agent = f"{BASE}/sch/i.html?_nkw=ring"
        assert not _match(agent, gt)[0]

    def test_attribute_mismatch(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring&Brand=Apple"
        agent = f"{BASE}/sch/i.html?_nkw=ring&Brand=Samsung"
        assert not _match(agent, gt)[0]

# ============================================================
# 5. CATEGORY & BRAND ROUTING
# ============================================================

class TestRouting:

    def test_category_match(self):
        gt = f"{BASE}/b/Rings/1234"
        assert _match(gt, gt)[0]

    def test_category_missing(self):
        gt = f"{BASE}/b/Rings/1234"
        agent = f"{BASE}/b/Rings"
        assert not _match(agent, gt)[0]

    def test_bn_match(self):
        gt = f"{BASE}/b/Nike/bn_123"
        assert _match(gt, gt)[0]

    def test_bn_missing(self):
        gt = f"{BASE}/b/Nike/bn_123"
        agent = f"{BASE}/b/Nike"
        assert not _match(agent, gt)[0]


# ============================================================
# 6. UNKNOWN URL TYPE
# ============================================================

class TestUnknownType:

    def test_unknown_path(self):
        gt = f"{BASE}/unknown/path"
        v = _v(gt)
        match, details = v._urls_match(gt, gt)

        assert not match
        assert "Unknown eBay URL type" in details["mismatches"]


# ============================================================
# 7. MULTI-GT LOGIC
# ============================================================

class TestMultiGT:

    def test_or_logic(self):
        gt = [
            f"{BASE}/sch/i.html?_nkw=ring",
            f"{BASE}/sch/i.html?_nkw=watch",
        ]

        v = EbayUrlMatch(gt)

        asyncio.run(v.update(url=f"{BASE}/sch/i.html?_nkw=watch"))
        result = asyncio.run(v.compute())

        assert result.score == 1.0

    def test_first_match_sticks(self):
        gt1 = f"{BASE}/sch/i.html?_nkw=ring"
        gt2 = f"{BASE}/sch/i.html?_nkw=watch"

        v = EbayUrlMatch([gt1, gt2])

        asyncio.run(v.update(url=gt1))
        asyncio.run(v.update(url=gt2))

        result = asyncio.run(v.compute_detailed())

        assert result.gt_url == gt1


# ============================================================
# 8. ASYNC LIFECYCLE
# ============================================================

class TestAsync:

    @pytest.mark.asyncio
    async def test_reset(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring"
        v = EbayUrlMatch(gt)

        await v.update(url=gt)
        await v.reset()

        assert (await v.compute()).score == 0.0

    @pytest.mark.asyncio
    async def test_no_match(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring"
        v = EbayUrlMatch(gt)

        await v.update(url=f"{BASE}/sch/i.html?_nkw=watch")
        assert (await v.compute()).score == 0.0


# ============================================================
# 9. EDGE CASES
# ============================================================

class TestEdgeCases:

    def test_empty_url(self):
        v = _v(f"{BASE}/sch/i.html?_nkw=ring")
        asyncio.run(v.update(url=""))
        assert not v._found_match

    def test_invalid_domain(self):
        v = _v(f"{BASE}/sch/i.html?_nkw=ring")
        asyncio.run(v.update(url="https://google.com"))
        assert not v._found_match

    def test_malformed(self):
        v = _v(f"{BASE}/sch/i.html?_nkw=ring")
        asyncio.run(v.update(url="not-a-url"))
        assert not v._found_match


# ============================================================
# 10. COMPUTE OUTPUT
# ============================================================

class TestCompute:

    @pytest.mark.asyncio
    async def test_compute_detailed(self):
        gt = f"{BASE}/sch/i.html?_nkw=ring"
        v = EbayUrlMatch(gt)

        await v.update(url=gt)
        result = await v.compute_detailed()

        assert isinstance(result, EbayVerifierResult)
        assert result.match
        assert result.score == 1.0
        assert result.agent_url == gt
        assert result.gt_url == gt
        assert isinstance(result.details, dict)


# ============================================================
# 11. REAL WORLD SCENARIO
# ============================================================

class TestRealScenario:

    def test_complex_search(self):
        gt = (
            f"{BASE}/sch/i.html?_nkw=macbook+pro"
            "&LH_FS=true&_udlo=500&_udhi=1500"
            "&LH_ItemCondition=1000&_sop=10"
        )

        agent = (
            f"{BASE}/sch/i.html?_nkw=apple+macbook+pro"
            "&LH_FS=true&_udlo=500&_udhi=1500"
            "&LH_ItemCondition=1000|3000&_sop=10"
        )

        match, details = _match(agent, gt)

        assert match, f"Failed with {details}"