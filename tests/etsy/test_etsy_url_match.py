"""
Pytest unit tests for Etsy URL Match verifier.

Tests EtsyUrlMatch for search/category/group URL verification.

Categories:
 1. Search URL Parsing
 2. Category URL Parsing
 3. Group/Collection URL Parsing
 4. Query Token Matching
 5. Price Filters
 6. Boolean Flags (shipping, discounts, etc.)
 7. Location & Delivery
 8. Item Type & Format
 9. Sort Matching
10. Attribute Matching
11. Page Type Routing
12. Multi-GT OR Logic
13. Async Lifecycle (update/reset/compute)
14. Edge Cases & Robustness
"""

import pytest

from navi_bench.etsy.etsy_url_match import EtsyUrlMatch, EtsyVerifierResult


# ============================================================
# Helpers
# ============================================================

BASE = "https://www.etsy.com"


def _v(gt_url: str | list[str]):
    return EtsyUrlMatch(gt_url=gt_url)


def _parse(url: str) -> dict:
    v = _v(f"{BASE}/search?q=test")
    return v._parse_search_url(url)


def _match(agent: str, gt: str) -> tuple[bool, dict]:
    v = _v(gt)
    return v._urls_match(agent, gt)


# ============================================================
# 1. SEARCH URL PARSING
# ============================================================

class TestSearchParsing:

    def test_query_parsed(self):
        r = _parse(f"{BASE}/search?q=handmade+jewelry")
        assert "handmade" in r["query"]
        assert "jewelry" in r["query"]

    def test_price_parsed(self):
        r = _parse(f"{BASE}/search?q=ring&min=10&max=50")
        assert r["min_price"] == 10
        assert r["max_price"] == 50

    def test_booleans_parsed(self):
        r = _parse(f"{BASE}/search?q=ring&free_shipping=true&is_discounted=true")
        assert r["free_shipping"] is True
        assert r["is_discounted"] is True

    def test_location_parsed(self):
        r = _parse(f"{BASE}/search?q=ring&ship_to=US&locationQuery=NY")
        assert r["ship_to"] == "us"
        assert r["location_query"] == "ny"

    def test_sort_parsed(self):
        r = _parse(f"{BASE}/search?q=ring&order=price_asc")
        assert r["sort"] == "price_asc"


# ============================================================
# 2. SEARCH MATCHING (CORE LOGIC)
# ============================================================

class TestSearchMatching:

    def test_query_subset_match(self):
        gt = f"{BASE}/search?q=handmade+jewelry"
        agent = f"{BASE}/search?q=handmade+silver+jewelry+ring"
        match, _ = _match(agent, gt)
        assert match is True

    def test_query_mismatch(self):
        gt = f"{BASE}/search?q=handmade+jewelry"
        agent = f"{BASE}/search?q=vintage+ring"
        match, _ = _match(agent, gt)
        assert match is False

    def test_missing_query_fails(self):
        gt = f"{BASE}/search?q=ring"
        agent = f"{BASE}/search"
        match, _ = _match(agent, gt)
        assert match is False

    def test_price_mismatch(self):
        gt = f"{BASE}/search?q=ring&min=10&max=50"
        agent = f"{BASE}/search?q=ring&min=10&max=100"
        match, _ = _match(agent, gt)
        assert match is False

    def test_free_shipping_mismatch(self):
        gt = f"{BASE}/search?q=ring&free_shipping=true"
        agent = f"{BASE}/search?q=ring&free_shipping=false"
        match, _ = _match(agent, gt)
        assert match is False


# ============================================================
# 3. CATEGORY URLS
# ============================================================

class TestCategoryMatching:

    def test_category_match(self):
        gt = f"{BASE}/c/jewelry/rings"
        agent = f"{BASE}/c/jewelry/rings"
        v = _v(gt)
        assert v._urls_match(agent, gt)[0] is True

    def test_category_mismatch(self):
        gt = f"{BASE}/c/jewelry/rings"
        agent = f"{BASE}/c/home/decor"
        v = _v(gt)
        assert v._urls_match(agent, gt)[0] is False


# ============================================================
# 4. GROUP URLS
# ============================================================

class TestGroupMatching:

    def test_group_match(self):
        gt = f"{BASE}/r/collections?min_price=10&max_price=50"
        agent = f"{BASE}/r/collections?min_price=10&max_price=50"
        v = _v(gt)
        assert v._urls_match(agent, gt)[0] is True

    def test_group_mismatch(self):
        gt = f"{BASE}/r/collections?min_price=10"
        agent = f"{BASE}/r/collections?min_price=20"
        v = _v(gt)
        assert v._urls_match(agent, gt)[0] is False


# ============================================================
# 5. ATTRIBUTE MATCHING
# ============================================================

class TestAttributes:

    def test_attribute_subset_match(self):
        gt = f"{BASE}/search?q=ring&attr_material=gold"
        agent = f"{BASE}/search?q=ring&attr_material=gold,sterling"
        v = _v(gt)
        assert v._urls_match(agent, gt)[0] is True

    def test_missing_attribute_fails(self):
        gt = f"{BASE}/search?q=ring&attr_material=gold"
        agent = f"{BASE}/search?q=ring"
        v = _v(gt)
        assert v._urls_match(agent, gt)[0] is False


# ============================================================
# 6. PAGETYPE ROUTING
# ============================================================

class TestPageTypeRouting:

    def test_search_route(self):
        gt = f"{BASE}/search?q=ring"
        v = _v(gt)
        assert v._urls_match(gt, gt)[0] is True

    def test_category_route(self):
        gt = f"{BASE}/c/jewelry"
        v = _v(gt)
        assert v._urls_match(gt, gt)[0] is True

    def test_group_route(self):
        gt = f"{BASE}/r/collections"
        v = _v(gt)
        assert v._urls_match(gt, gt)[0] is True


# ============================================================
# 7. MULTI-GT OR LOGIC
# ============================================================

class TestMultiGT:

    # @pytest.mark.asyncio
    # async def test_any_gt_match(self):
    #     gt = [
    #         f"{BASE}/search?q=ring",
    #         f"{BASE}/search?q=necklace",
    #     ]

    #     v = EtsyUrlMatch(gt_url=gt)
    #     await v.reset()

    #     # match second GT
    #     await v.update(url=f"{BASE}/search?q=necklace")

    #     result = await v.compute()
    #     assert result.score == 1.0
    def test_any_gt_match(self):
        gt = [
            f"{BASE}/search?q=ring",
            f"{BASE}/search?q=necklace",
        ]

        v = EtsyUrlMatch(gt_url=gt)

        import asyncio
        asyncio.run(v.reset())

        # First update matches NONE
        asyncio.run(v.update(url=f"{BASE}/search?q=bracelet"))

        # Second update matches SECOND GT
        asyncio.run(v.update(url=f"{BASE}/search?q=necklace"))

        result = asyncio.run(v.compute())

        assert result.score == 1.0

    def test_no_gt_match(self):
        gt = [
            f"{BASE}/search?q=ring",
            f"{BASE}/search?q=necklace",
        ]
        v = _v(gt)
        assert v._urls_match(f"{BASE}/search?q=bracelet", gt[0])[0] is False


# ============================================================
# 8. ASYNC LIFECYCLE
# ============================================================

class TestAsyncLifecycle:

    @pytest.mark.asyncio
    async def test_exact_match_scores_1(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        await v.reset()
        await v.update(url=gt)
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_no_match_scores_0(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        await v.reset()
        await v.update(url=f"{BASE}/search?q=table")
        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        await v.update(url=gt)
        assert (await v.compute()).score == 1.0

        await v.reset()
        assert (await v.compute()).score == 0.0

    @pytest.mark.asyncio
    async def test_first_match_sticks(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        await v.update(url=gt)
        await v.update(url=f"{BASE}/search?q=wrong")
        assert (await v.compute()).score == 1.0


# ============================================================
# 9. EDGE CASES
# ============================================================

class TestEdgeCases:

    def test_non_etsy_url_rejected(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        v._is_valid = lambda x: False  # simulate invalid domain
        assert v._found_match is False

    def test_empty_url_update(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        # should not crash
        import asyncio
        asyncio.run(v.update(url=""))
        assert v._found_match is False

    def test_malformed_url(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        import asyncio
        asyncio.run(v.update(url="not-a-url"))
        assert v._found_match is False


# ============================================================
# 10. COMPUTE OUTPUT TYPE
# ============================================================

class TestComputeOutput:

    @pytest.mark.asyncio
    async def test_compute_detailed(self):
        gt = f"{BASE}/search?q=ring"
        v = EtsyUrlMatch(gt_url=gt)
        await v.update(url=gt)
        result = await v.compute_detailed()
        assert isinstance(result, EtsyVerifierResult)
        assert result.match is True
        assert result.score == 1.0
    
# ============================================================
# 11. REAL TASK SCENARIO TEST
# ============================================================

class TestRealTaskScenario:

    def test_macrame_swing_task(self):
        gt = (
            "https://www.etsy.com/search?"
            "q=macrame%20swing&is_discounted=true&"
            "min=500&max=700&is_star_seller=true&"
            "order=date_desc&free_shipping=true"
        )

        agent = (
            "https://www.etsy.com/search?"
            "q=macrame+swing&instant_download=false&explicit=1&"
            "is_discounted=true&is_star_seller=true&free_shipping=true&"
            "custom_price=1&min=500&max=700&order=date_desc"
        )

        v = EtsyUrlMatch(gt_url=gt)

        match, details = v._urls_match(agent, gt)

        assert match is True, f"Expected PASS but got mismatches: {details}"
    
    def test_dangle_earrings_task(self):
        gt = (
            "https://www.etsy.com/c/jewelry/earrings/dangle-earrings?"
            "free_shipping=true&is_merch_library=true&max=3000&"
            "gift_wrap=true&ship_to=US&order=highest_reviews"
        )

        agent = (
            "https://www.etsy.com/c/jewelry/earrings/dangle-earrings?"
            "explicit=1&free_shipping=true&is_merch_library=true&max=3000&"
            "gift_wrap=true&ship_to=US&order=highest_reviews"
        )

        v = EtsyUrlMatch(gt_url=gt)
        match, _ = v._urls_match(agent, gt)

        assert match is True
    
    def test_macrame_swing_missing_filters(self):
        gt = (
            "https://www.etsy.com/search?"
            "q=macrame%20swing&is_discounted=true&"
            "min=500&max=700&is_star_seller=true&"
            "order=date_desc&free_shipping=true"
        )

        agent = (
            "https://www.etsy.com/search?"
            "q=macrame+swing&instant_download=false&explicit=1&"
            "is_discounted=true&custom_price=1&"
            "min=500&max=700&order=date_desc"
        )

        v = EtsyUrlMatch(gt_url=gt)

        match, details = v._urls_match(agent, gt)

        assert match is False
        assert "is_star_seller mismatch" in details["mismatches"]
        assert "free_shipping mismatch" in details["mismatches"]
    
# ============================================================
# 12. SINGULAR / PLURAL NORMALIZATION
# ============================================================

class TestSingularPlural:

    def test_plural_gt_singular_agent(self):
        gt = f"{BASE}/search?q=wedding+invitation+templates"
        agent = f"{BASE}/search?q=wedding+invitation+template"

        match, _ = _match(agent, gt)
        assert match is True

    def test_singular_gt_plural_agent(self):
        gt = f"{BASE}/search?q=wedding+invitation+template"
        agent = f"{BASE}/search?q=wedding+invitation+templates"

        match, _ = _match(agent, gt)
        assert match is True

    def test_plural_variation_ies(self):
        gt = f"{BASE}/search?q=party"
        agent = f"{BASE}/search?q=parties"

        match, _ = _match(agent, gt)
        assert match is True

    def test_plural_variation_es(self):
        gt = f"{BASE}/search?q=box"
        agent = f"{BASE}/search?q=boxes"

        match, _ = _match(agent, gt)
        assert match is True

    def test_multiple_tokens_plural(self):
        gt = f"{BASE}/search?q=gift+boxes"
        agent = f"{BASE}/search?q=gifts+box"

        match, _ = _match(agent, gt)
        assert match is True

    def test_non_plural_word_should_not_match(self):
        gt = f"{BASE}/search?q=ring"
        agent = f"{BASE}/search?q=necklace"

        match, _ = _match(agent, gt)
        assert match is False

# ============================================================
# 13. SINGULAR / PLURAL EDGE CASES
# ============================================================

class TestSingularPluralHardEdgeCases:

    def test_series_vs_series_pass(self):
        gt = f"{BASE}/search?q=series"
        agent = f"{BASE}/search?q=series"

        match, _ = _match(agent, gt)
        assert match is True

    def test_status_vs_statuses_pass(self):
        gt = f"{BASE}/search?q=status"
        agent = f"{BASE}/search?q=statuses"

        match, _ = _match(agent, gt)
        assert match is True

    def test_bus_vs_buses_pass(self):
        gt = f"{BASE}/search?q=bus"
        agent = f"{BASE}/search?q=buses"

        match, _ = _match(agent, gt)
        assert match is True

    def test_gas_vs_gases_pass(self):
        gt = f"{BASE}/search?q=gas"
        agent = f"{BASE}/search?q=gases"

        match, _ = _match(agent, gt)
        assert match is True

    def test_mixed_tokens_subset_logic(self):
        gt = f"{BASE}/search?q=wedding+dress"
        agent = f"{BASE}/search?q=weddings+dresses+summer"

        match, _ = _match(agent, gt)
        assert match is True

    def test_reverse_subset_should_fail(self):
        gt = f"{BASE}/search?q=wedding+dresses+women"
        agent = f"{BASE}/search?q=wedding+dress"

        match, _ = _match(agent, gt)
        assert match is False
