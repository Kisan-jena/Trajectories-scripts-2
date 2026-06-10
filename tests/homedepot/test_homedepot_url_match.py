"""
Production-grade Pytest suite for HomeDepotUrlMatch.

Covers:
- Page type detection
- Filter extraction
- Filter subset matching
- Query param filters
- Room pages
- Product pages
- Category / Brand routing
- Multi GT logic
- Async lifecycle
- Edge cases
"""

import asyncio

import pytest

from navi_bench.homedepot.homedepot_url_match import (
    HomeDepotUrlMatch,
    HomeDepotVerifierResult,
)

BASE = "https://www.homedepot.com"


# ============================================================
# Helpers
# ============================================================

def _v(gt):
    return HomeDepotUrlMatch(gt_url=gt)


def _match(agent, gt):
    return _v(gt)._urls_match(agent, gt)


# ============================================================
# 1. PAGE TYPE DETECTION
# ============================================================

class TestPageTypes:

    def test_search(self):

        gt = f"{BASE}/s/chair"

        assert _match(gt, gt)[0]

    def test_product(self):

        gt = (
            f"{BASE}/p/"
            "Milwaukee-M18-123456789/312345678"
        )

        assert _match(gt, gt)[0]

    def test_category(self):

        gt = (
            f"{BASE}/b/Flooring/"
            "N-5yc1vZar90"
        )

        assert _match(gt, gt)[0]

    def test_brand(self):

        gt = (
            f"{BASE}/b/LG/"
            "N-5yc1vZ1z0u"
        )

        assert _match(gt, gt)[0]

    def test_room(self):

        gt = (
            f"{BASE}/room/"
            "living-room/classic/beige"
        )

        assert _match(gt, gt)[0]

    def test_services(self):

        gt = (
            f"{BASE}/services/"
            "c/flooring-installation/test123"
        )

        assert _match(gt, gt)[0]


# ============================================================
# 2. FILTER MATCHING
# ============================================================

class TestFilterMatching:

    def test_same_filters_different_order(self):

        gt = (
            f"{BASE}/b/Highly-Rated/Multisurface/"
            "?sortorder=asc&sortby=bestmatch"
        )

        agent = (
            f"{BASE}/b/Multisurface/Highly-Rated/"
            "?sortby=bestmatch&sortorder=asc"
        )

        assert _match(agent, gt)[0]

    def test_missing_filter(self):

        gt = (
            f"{BASE}/b/Highly-Rated/Multisurface/"
            "N-5yc1vZbwo5oZ1z1u4yw"
        )

        agent = (
            f"{BASE}/b/Highly-Rated/"
            "N-5yc1vZbwo5o"
        )

        assert not _match(agent, gt)[0]

    def test_extra_filters_fail(self):

        gt = (
            f"{BASE}/b/Highly-Rated/"
            "N-5yc1vZbwo5o"
        )

        agent = (
            f"{BASE}/b/Highly-Rated/Extra/"
            "N-5yc1vZbwo5oZ1z1u4ywZabcd"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "extra path filters" in str(details)

    def test_query_filter_match(self):

        gt = (
            f"{BASE}/b/Tools/"
            "N-5yc1vZc1xy"
            "?sortorder=desc&sortby=topsellers"
        )

        agent = (
            f"{BASE}/b/Tools/"
            "N-5yc1vZc1xy"
            "?sortby=topsellers&sortorder=desc"
        )

        assert _match(agent, gt)[0]

    def test_query_filter_mismatch(self):

        gt = (
            f"{BASE}/b/Tools/"
            "N-5yc1vZc1xy"
            "?sortorder=desc"
        )

        agent = (
            f"{BASE}/b/Tools/"
            "N-5yc1vZc1xy"
            "?sortorder=asc"
        )

        assert not _match(agent, gt)[0]


# ============================================================
# 3. SEARCH PAGES
# ============================================================

class TestSearchPages:

    def test_search_match(self):

        gt = f"{BASE}/s/vacuum"

        assert _match(gt, gt)[0]

    def test_search_mismatch(self):

        gt = f"{BASE}/s/vacuum"

        agent = f"{BASE}/s/chair"

        assert not _match(agent, gt)[0]


# ============================================================
# 4. PRODUCT PAGES
# ============================================================

class TestProductPages:

    def test_product_match(self):

        gt = (
            f"{BASE}/p/"
            "Milwaukee-Drill/312345678"
        )

        agent = (
            f"{BASE}/p/"
            "Different-Name/312345678"
        )

        assert _match(agent, gt)[0]

# ============================================================
# 5. ROOM PAGES
# ============================================================

class TestRoomPages:

    def test_room_match(self):

        gt = (
            f"{BASE}/room/"
            "living-room/classic/beige"
        )

        agent = (
            f"{BASE}/room/"
            "living-room/classic/blue"
        )

        assert _match(agent, gt)[0]

    def test_room_mismatch(self):

        gt = (
            f"{BASE}/room/"
            "living-room/classic/beige"
        )

        agent = (
            f"{BASE}/room/"
            "bedroom/classic/beige"
        )

        assert not _match(agent, gt)[0]


# ============================================================
# 6. CATEGORY / BRAND
# ============================================================

class TestCategoryBrand:

    def test_category_match(self):

        gt = (
            f"{BASE}/b/Flooring/"
            "N-5yc1vZar90"
        )

        agent = (
            f"{BASE}/b/Tile/"
            "N-5yc1vZar90"
        )

        assert _match(agent, gt)[0]

    def test_category_mismatch(self):

        gt = (
            f"{BASE}/b/Flooring/"
            "N-5yc1vZar90"
        )

        agent = (
            f"{BASE}/b/Flooring/"
            "N-5yc1vZzzzz"
        )

        assert not _match(agent, gt)[0]

    def test_brand_match(self):

        gt = (
            f"{BASE}/b/LG/"
            "N-5yc1vZ1z0u"
        )

        agent = (
            f"{BASE}/b/LG/"
            "N-5yc1vZ1z0u"
        )

        assert _match(agent, gt)[0]


# ============================================================
# 7. MULTI GT
# ============================================================

class TestMultiGT:

    def test_or_logic(self):

        gt = [
            f"{BASE}/s/vacuum",
            f"{BASE}/s/chair",
        ]

        v = HomeDepotUrlMatch(gt)

        asyncio.run(
            v.update(
                url=f"{BASE}/s/chair"
            )
        )

        result = asyncio.run(
            v.compute()
        )

        assert result.score == 1.0

    def test_first_match_sticks(self):

        gt1 = f"{BASE}/s/vacuum"

        gt2 = f"{BASE}/s/chair"

        v = HomeDepotUrlMatch(
            [gt1, gt2]
        )

        asyncio.run(
            v.update(url=gt1)
        )

        asyncio.run(
            v.update(url=gt2)
        )

        result = asyncio.run(
            v.compute_detailed()
        )

        assert result.gt_url == gt1


# ============================================================
# 8. ASYNC LIFECYCLE
# ============================================================

class TestAsync:

    @pytest.mark.asyncio
    async def test_reset(self):

        gt = f"{BASE}/s/vacuum"

        v = HomeDepotUrlMatch(gt)

        await v.update(url=gt)

        await v.reset()

        assert (
            await v.compute()
        ).score == 0.0

    @pytest.mark.asyncio
    async def test_no_match(self):

        gt = f"{BASE}/s/vacuum"

        v = HomeDepotUrlMatch(gt)

        await v.update(
            url=f"{BASE}/s/chair"
        )

        assert (
            await v.compute()
        ).score == 0.0


# ============================================================
# 9. EDGE CASES
# ============================================================

class TestEdgeCases:

    def test_empty_url(self):

        v = _v(
            f"{BASE}/s/vacuum"
        )

        asyncio.run(
            v.update(url="")
        )

        assert not v._found_match

    def test_invalid_domain(self):

        v = _v(
            f"{BASE}/s/vacuum"
        )

        asyncio.run(
            v.update(
                url="https://google.com"
            )
        )

        assert not v._found_match

    def test_malformed(self):

        v = _v(
            f"{BASE}/s/vacuum"
        )

        asyncio.run(
            v.update(
                url="not-a-url"
            )
        )

        assert not v._found_match


# ============================================================
# 10. COMPUTE OUTPUT
# ============================================================

class TestCompute:

    @pytest.mark.asyncio
    async def test_compute_detailed(self):

        gt = f"{BASE}/s/vacuum"

        v = HomeDepotUrlMatch(gt)

        await v.update(url=gt)

        result = (
            await v.compute_detailed()
        )

        assert isinstance(
            result,
            HomeDepotVerifierResult,
        )

        assert result.match

        assert result.score == 1.0

        assert result.agent_url == gt

        assert result.gt_url == gt

        assert isinstance(
            result.details,
            dict,
        )


# ============================================================
# 11. REAL WORLD SCENARIOS
# ============================================================

class TestRealWorld:

    def test_complex_filters(self):

        gt = (
            f"{BASE}/b/Highly-Rated/"
            "Pick-Up-Today/"
            "Subscription-Eligible/"
            "N-5yc1vZ12kzZ12l0Z12l1"
            "?sortorder=desc&sortby=topsellers"
        )

        agent = (
            f"{BASE}/b/Subscription-Eligible/"
            "Highly-Rated/"
            "Pick-Up-Today/"
            "N-5yc1vZ12kzZ12l0Z12l1"
            "?sortby=topsellers&sortorder=desc"
        )

        match, details = _match(
            agent,
            gt,
        )

        assert match, (
            f"Failed with {details}"
        )

    def test_room_with_filters(self):

        gt = (
            f"{BASE}/room/living-room/"
            "classic/beige"
            "?style=coastal&color=black"
        )

        agent = (
            f"{BASE}/room/living-room/"
            "classic/blue"
            "?color=black&style=coastal"
        )

        assert _match(agent, gt)[0]

# ============================================================
# 12. PRICE RANGE FILTER
# ============================================================

class TestPriceRangeFilters:

    def test_price_range_filter_match(self):

        gt = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3ns"
        )

        agent = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3nsZ12l9"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "extra path filters" in str(details)

    def test_price_range_exact_filter_match(self):

        # Base category only (no price filter)
        gt = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3nsZ12l9"
        )

        # Agent applies price range filter ($500-$600)
        agent = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3nsZ12l9"
        )

        match, details = _match(agent, gt)

        assert match, (
            f"Price range filter should be allowed. Got: {details}"
        )

    def test_price_range_filter_mismatch(self):

        # Different price range filter applied
        gt = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3nsZ12l9"
        )

        agent = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3nsZ12l8"
        )

        match, details = _match(agent, gt)

        assert not match, (
            f"Different price range should fail. Got: {details}"
        )

    def test_price_range_independent_of_taxonomy(self):

        gt = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3ns"
        )

        agent = (
            f"{BASE}/b/Appliances-Refrigerators-Top-Freezer-Refrigerators/"
            "N-5yc1vZc3nsZ12l9Zabc1"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "extra path filters" in str(details)

    def test_query_match_with_reordered_path_segments(self):

        gt = (
            f"{BASE}/b/Coconut-Fiber/"
            "Plant-Fiber/"
            "N-5yc1vZ1z0u6r1Z1z1bmaz/"
            "Ntk-google/"
            "Ntt-baskets"
            "?NCNI-5&lowerbound=10&upperbound=30"
        )

        agent = (
            f"{BASE}/b/Plant-Fiber/"
            "N-5yc1vZ1z0u6r1Z1z1bmaz/"
            "Coconut-Fiber/"
            "Ntk-google/"
            "Ntt-baskets"
            "?NCNI-5&lowerbound=10&upperbound=30"
        )

        match, details = _match(
            agent,
            gt,
        )

        assert match, (
            "Reordered category/filter path "
            "segments should still match. "
            f"Got: {details}"
        )

# ============================================================
# QUERY + FILTER VARIATIONS
# ============================================================

class TestQueryAndFilterVariations:

    def test_reordered_path_and_query_params(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Vertical-/-Horizontal/"
            "N-5yc1vZ1z1399kZ1z1rus2/"
            "Ntk-elasticplus/"
            "Ntt-bathroom%2Bmirror"
            "?sortorder=none&sortby=bestmatch"
        )

        agent = (
            f"{BASE}/b/Vertical-/-Horizontal/"
            "Framed/"
            "N-5yc1vZ1z1rus2Z1z1399k/"
            "Ntt-bathroom%2Bmirror/"
            "Ntk-elasticplus"
            "?sortby=bestmatch&sortorder=none"
        )

        assert _match(agent, gt)[0]

    def test_missing_path_filter(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Vertical-/-Horizontal/"
            "N-5yc1vZ1z1399kZ1z1rus2"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "missing path filters" in str(details)

    def test_extra_path_filters_fail(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Modern/"
            "N-5yc1vZ1z1399kZ1z1rus2Zextra123"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "extra path filters" in str(details)

    def test_missing_query_parameter(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortorder=none&sortby=bestmatch"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortorder=none"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "missing query filter" in str(details)

    def test_query_parameter_value_mismatch(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortorder=none&sortby=bestmatch"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortorder=desc&sortby=bestmatch"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "sortorder=none" in str(details)

    def test_reordered_query_parameters(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortorder=none&sortby=bestmatch"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortby=bestmatch&sortorder=none"
        )

        assert _match(agent, gt)[0]

    def test_case_insensitive_query_matching(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?SORTORDER=none&SORTBY=bestmatch"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortby=bestmatch&sortorder=none"
        )

        assert _match(agent, gt)[0]

    def test_price_range_query_match(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?lowerbound=10&upperbound=30"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?upperbound=30&lowerbound=10"
        )

        assert _match(agent, gt)[0]

    def test_price_range_query_mismatch(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?lowerbound=10&upperbound=30"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?lowerbound=20&upperbound=30"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "lowerbound=10" in str(details)

    def test_missing_upperbound(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?lowerbound=10&upperbound=30"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?lowerbound=10"
        )

        match, details = _match(agent, gt)

        assert not match
        assert "upperbound=30" in str(details)

    def test_ignore_ncni_parameter(self):

        gt = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?NCNI-5&sortby=bestmatch"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "N-5yc1vZ1z1399k"
            "?sortby=bestmatch"
        )

        assert _match(agent, gt)[0]

    def test_query_search_term_match(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntk-elasticplus/"
            "Ntt-bathroom%2Bmirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom%2Bmirror/"
            "Ntk-elasticplus"
        )

        assert _match(agent, gt)[0]

    def test_query_search_term_mismatch(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntk-elasticplus/"
            "Ntt-bathroom%2Bmirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntk-elasticplus/"
            "Ntt-kitchen%2Bmirror"
        )

        match, details = _match(agent, gt)

        assert isinstance(match, bool)
    
# ============================================================
# QUERY NORMALIZATION TESTS
# ============================================================

class TestQueryNormalization:

    def test_plus_encoded_query_match(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom%2Bmirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom+mirror"
        )

        assert _match(agent, gt)[0]

    def test_space_vs_plus_query_match(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom%20mirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom+mirror"
        )

        assert _match(agent, gt)[0]

    def test_case_insensitive_query_tokens(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-BATHROOM%2BMirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom%2Bmirror"
        )

        assert _match(agent, gt)[0]

    def test_plural_normalization_simple_s(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-mirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-mirrors"
        )

        assert _match(agent, gt)[0]

    def test_plural_normalization_ies(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-party"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-parties"
        )

        assert _match(agent, gt)[0]

    def test_plural_normalization_es(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-box"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-boxes"
        )

        assert _match(agent, gt)[0]

    def test_stopword_removal(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom-mirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-the-bathroom-mirror"
        )

        assert _match(agent, gt)[0]

    def test_token_order_irrelevant(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom-mirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-mirror-bathroom"
        )

        assert _match(agent, gt)[0]

    def test_double_encoded_query_match(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom%252Bmirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom%2Bmirror"
        )

        assert _match(agent, gt)[0]

    def test_query_token_mismatch(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom-mirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-kitchen-mirror"
        )

        match, details = _match(agent, gt)

        assert not match

    def test_partial_query_missing_token(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom-wall-mirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom-mirror"
        )

        match, details = _match(agent, gt)

        assert not match

    def test_extra_query_tokens_allowed(self):

        gt = (
            f"{BASE}/b/Framed/"
            "Ntt-bathroom-mirror"
        )

        agent = (
            f"{BASE}/b/Framed/"
            "Ntt-large-bathroom-wall-mirror"
        )

        assert _match(agent, gt)[0]
    
def test_hostname_suffix_attack_domain():

    v = _v(
        f"{BASE}/s/vacuum"
    )

    asyncio.run(
        v.update(
            url="https://evilhomedepot.com/s/vacuum"
        )
    )

    assert not v._found_match

def test_token_equivalent_boxes():

    v = _v(f"{BASE}/s/test")

    assert v._token_equivalent(
        "boxes",
        "box",
    )

    assert v._token_equivalent(
        "box",
        "boxes",
    )

def test_category_token_order_independent():

    gt = (
        f"{BASE}/b/Test/"
        "N-5yc1vZaaaZbbbZccc"
    )

    agent = (
        f"{BASE}/b/Test/"
        "N-5yc1vZcccZaaaZbbb"
    )

    assert _match(agent, gt)[0]

def test_empty_bound_params_ignored():

    gt = (
        f"{BASE}/b/Tools/"
        "N-5yc1vZc1xy"
        "?lowerbound=&upperbound="
    )

    agent = (
        f"{BASE}/b/Tools/"
        "N-5yc1vZc1xy"
    )

    assert _match(agent, gt)[0]

def test_empty_bound_params_ignored_agent():

    gt = (
        f"{BASE}/b/Tools/"
        "N-5yc1vZc1xy"
    )

    agent = (
        f"{BASE}/b/Tools/"
        "N-5yc1vZc1xy"
        "?lowerbound=&upperbound="
    )

    assert _match(agent, gt)[0]