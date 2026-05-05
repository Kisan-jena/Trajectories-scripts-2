"""Comprehensive test suite for Mercari URL verifier.

Tests cover:
- URL parsing (query parameters, path segments)
- Query text normalization (case, whitespace, URL-encoding)
- Price range matching (min/max in CENTS, presets, mismatch)
- Item condition normalization and multi-select matching
- Sort order normalization and matching
- Category ID matching (query param and path extraction)
- Brand ID matching
- Shipping & origin filter matching
- Deals & status filter matching
- Full URL matching integration (all field mismatches)
- Domain validation (mercari.com, www, subdomains, rejection)
- Async lifecycle (reset/update/compute)
- Multi-GT URL OR semantics
- Edge cases (empty, non-Mercari, item pages)
- Normalization helpers
"""

import pytest

from navi_bench.mercari.mercari_url_match import (
    MercariUrlMatch,
    _extract_category_from_path,
    _normalize_conditions,
    _normalize_country_source,
    _normalize_query_text,
    _normalize_shipping_payer,
    _normalize_sort_order,
    _normalize_status,
    parse_mercari_url,
)


# =========================================================================
# 1. URL Parsing
# =========================================================================


class TestUrlParsing:
    """Tests for parse_mercari_url()."""

    def test_basic_search(self):
        url = "https://www.mercari.com/search/?keyword=iphone+15&minPrice=20000&maxPrice=50000"
        p = parse_mercari_url(url)
        assert p["keyword"] == "iphone 15"
        assert p["min_price"] == 20000
        assert p["max_price"] == 50000

    def test_all_filters(self):
        url = (
            "https://www.mercari.com/search/?keyword=nike+shoes"
            "&minPrice=5000&maxPrice=15000&sortBy=3"
            "&itemConditions=1-2&categoryIds=77&brandIds=4578"
            "&shippingPayerIds=2&countrySources=1"
            "&withDealsOnly=true&statusIds=1&colorIds=1"
        )
        p = parse_mercari_url(url)
        assert p["keyword"] == "nike shoes"
        assert p["min_price"] == 5000
        assert p["max_price"] == 15000
        assert p["sort_by"] == "3"
        assert p["item_conditions"] == ["1", "2"]
        assert p["category_ids"] == "77"
        assert p["brand_ids"] == "4578"
        assert p["shipping_payer_ids"] == "2"
        assert p["country_sources"] == "1"
        assert p["with_deals_only"] == "true"
        assert p["status_ids"] == "1"
        assert p["color_ids"] == "1"

    def test_category_url(self):
        url = "https://www.mercari.com/us/category/electronics-7/"
        p = parse_mercari_url(url)
        assert p["category_from_path"] == "7"

    def test_missing_all_params(self):
        url = "https://www.mercari.com/search/"
        p = parse_mercari_url(url)
        assert p["keyword"] == ""
        assert p["min_price"] is None
        assert p["max_price"] is None
        assert p["sort_by"] == ""
        assert p["item_conditions"] == []

    def test_url_encoded_query(self):
        url = "https://www.mercari.com/search/?keyword=macbook%20pro%2016"
        p = parse_mercari_url(url)
        assert p["keyword"] == "macbook pro 16"

    def test_category_from_path_women(self):
        url = "https://www.mercari.com/us/category/women-1/"
        p = parse_mercari_url(url)
        assert p["category_from_path"] == "1"

    def test_case_insensitive_params(self):
        url = "https://www.mercari.com/search/?keyword=test&sortby=2"
        p = parse_mercari_url(url)
        assert p["sort_by"] == "2"

    def test_item_listing_url(self):
        url = "https://www.mercari.com/us/item/m72277772433/"
        p = parse_mercari_url(url)
        assert p["keyword"] == ""


# =========================================================================
# 2. Query Text Normalization
# =========================================================================


class TestQueryNormalization:
    def test_lowercase(self):
        assert _normalize_query_text("iPhone 15 Pro") == "iphone 15 pro"

    def test_whitespace_collapse(self):
        assert _normalize_query_text("  iphone   15  ") == "iphone 15"

    def test_url_decode(self):
        assert _normalize_query_text("macbook%20pro") == "macbook pro"

    def test_empty(self):
        assert _normalize_query_text("") == ""

    def test_special_characters(self):
        assert _normalize_query_text('32" Monitor') == '32" monitor'

    def test_strip(self):
        assert _normalize_query_text("  hello  ") == "hello"


# =========================================================================
# 3. Price Range Matching
# =========================================================================


class TestPriceRange:
    def test_both_prices_match(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000&maxPrice=15000"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_min_price_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000&maxPrice=15000"
        agent = "https://www.mercari.com/search/?keyword=desk&minPrice=7500&maxPrice=15000"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Min price" in d["mismatches"][0]

    def test_max_price_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000&maxPrice=15000"
        agent = "https://www.mercari.com/search/?keyword=desk&minPrice=5000&maxPrice=20000"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Max price" in d["mismatches"][0]

    def test_missing_min_price(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000"
        agent = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "missing" in d["mismatches"][0].lower()

    def test_missing_max_price(self):
        gt = "https://www.mercari.com/search/?keyword=desk&maxPrice=15000"
        agent = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False

    def test_min_only(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=20000"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_max_only(self):
        gt = "https://www.mercari.com/search/?keyword=desk&maxPrice=2500"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_cents_encoding(self):
        """$50 = 5000 cents, $150 = 15000 cents."""
        gt = "https://www.mercari.com/search/?keyword=shoes&minPrice=5000&maxPrice=15000"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True


# =========================================================================
# 4. Item Condition Matching
# =========================================================================


class TestConditionMatching:
    def test_normalize_new(self):
        assert _normalize_conditions("1") == ["1"]

    def test_normalize_like_new(self):
        assert _normalize_conditions("2") == ["2"]

    def test_normalize_all(self):
        assert _normalize_conditions("1-2-3-4-5") == ["1", "2", "3", "4", "5"]

    def test_multi_select_hyphen(self):
        assert _normalize_conditions("1-2") == ["1", "2"]

    def test_multi_select_comma(self):
        assert _normalize_conditions("3,4") == ["3", "4"]

    def test_alias_new(self):
        assert _normalize_conditions("new") == ["1"]

    def test_alias_like_new(self):
        assert _normalize_conditions("like_new") == ["2"]

    def test_condition_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=phone&itemConditions=1"
        agent = "https://www.mercari.com/search/?keyword=phone&itemConditions=3"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Condition" in d["mismatches"][0]

    def test_condition_missing(self):
        gt = "https://www.mercari.com/search/?keyword=phone&itemConditions=1"
        agent = "https://www.mercari.com/search/?keyword=phone"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "missing" in d["mismatches"][0].lower()

    def test_empty(self):
        assert _normalize_conditions("") == []


# =========================================================================
# 5. Sort Order Matching
# =========================================================================


class TestSortMatching:
    def test_best_match(self):
        assert _normalize_sort_order("1") == "1"

    def test_newest(self):
        assert _normalize_sort_order("2") == "2"

    def test_price_asc(self):
        assert _normalize_sort_order("3") == "3"

    def test_price_desc(self):
        assert _normalize_sort_order("4") == "4"

    def test_alias_newest(self):
        assert _normalize_sort_order("newest") == "2"

    def test_alias_lowest_price(self):
        assert _normalize_sort_order("lowest_price") == "3"

    def test_alias_highest_price(self):
        assert _normalize_sort_order("highest_price") == "4"

    def test_sort_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=chair&sortBy=3"
        agent = "https://www.mercari.com/search/?keyword=chair&sortBy=4"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Sort order" in d["mismatches"][0]

    def test_empty(self):
        assert _normalize_sort_order("") == ""


# =========================================================================
# 6. Category Matching
# =========================================================================


class TestCategoryMatching:
    def test_path_electronics(self):
        assert _extract_category_from_path("/us/category/electronics-7/") == "7"

    def test_path_women(self):
        assert _extract_category_from_path("/us/category/women-1/") == "1"

    def test_path_men(self):
        assert _extract_category_from_path("/us/category/men-2/") == "2"

    def test_no_category_in_search(self):
        assert _extract_category_from_path("/search/") == ""

    def test_category_match_query_param(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&categoryIds=7"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_category_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&categoryIds=7"
        agent = "https://www.mercari.com/search/?keyword=shoes&categoryIds=1"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Category" in d["mismatches"][0]


# =========================================================================
# 7. Brand Matching
# =========================================================================


class TestBrandMatching:
    def test_brand_match(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&brandIds=4578"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_brand_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&brandIds=4578"
        agent = "https://www.mercari.com/search/?keyword=shoes&brandIds=9999"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Brand" in d["mismatches"][0]

    def test_brand_missing(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&brandIds=4578"
        agent = "https://www.mercari.com/search/?keyword=shoes"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "missing" in d["mismatches"][0].lower()


# =========================================================================
# 8. Shipping & Origin Matching
# =========================================================================


class TestShippingOrigin:
    def test_free_shipping_match(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&shippingPayerIds=2"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_shipping_alias(self):
        assert _normalize_shipping_payer("free") == "2"
        assert _normalize_shipping_payer("free_shipping") == "2"

    def test_origin_usa(self):
        assert _normalize_country_source("usa") == "1"
        assert _normalize_country_source("us") == "1"

    def test_origin_japan(self):
        assert _normalize_country_source("japan") == "2"
        assert _normalize_country_source("jp") == "2"

    def test_origin_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=bag&countrySources=2"
        agent = "https://www.mercari.com/search/?keyword=bag&countrySources=1"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Country source" in d["mismatches"][0]

    def test_shipping_missing(self):
        gt = "https://www.mercari.com/search/?keyword=bag&shippingPayerIds=2"
        agent = "https://www.mercari.com/search/?keyword=bag"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False


# =========================================================================
# 9. Deals & Status Matching
# =========================================================================


class TestDealsStatus:
    def test_deals_match(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&withDealsOnly=true"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_deals_missing(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&withDealsOnly=true"
        agent = "https://www.mercari.com/search/?keyword=shoes"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False

    def test_status_match(self):
        gt = "https://www.mercari.com/search/?keyword=watch&statusIds=1"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_status_alias(self):
        assert _normalize_status("on_sale") == "1"
        assert _normalize_status("sold_out") == "2"
        assert _normalize_status("sold") == "2"


# =========================================================================
# 10. Full URL Matching Integration
# =========================================================================


class TestUrlMatchingIntegration:
    def test_identical_urls(self):
        url = (
            "https://www.mercari.com/search/?keyword=desk"
            "&minPrice=5000&maxPrice=15000&sortBy=3&itemConditions=1"
        )
        v = MercariUrlMatch(gt_url=url)
        match, _ = v._urls_match(url, url)
        assert match is True

    def test_query_case_insensitive(self):
        gt = "https://www.mercari.com/search/?keyword=iPhone+15+Pro"
        agent = "https://www.mercari.com/search/?keyword=iphone+15+pro"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(agent, gt)
        assert match is True

    def test_query_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=iphone+15"
        agent = "https://www.mercari.com/search/?keyword=samsung+galaxy"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Keyword" in d["mismatches"][0]

    def test_query_missing(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        agent = "https://www.mercari.com/search/"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "missing" in d["mismatches"][0].lower()

    def test_extra_agent_params_ignored(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        agent = "https://www.mercari.com/search/?keyword=desk&sortBy=3&colorIds=1"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(agent, gt)
        assert match is True

    def test_all_filters_combined(self):
        url = (
            "https://www.mercari.com/search/?keyword=nike+shoes"
            "&minPrice=5000&maxPrice=15000&sortBy=3"
            "&itemConditions=1&brandIds=4578"
            "&shippingPayerIds=2&countrySources=1"
        )
        v = MercariUrlMatch(gt_url=url)
        match, _ = v._urls_match(url, url)
        assert match is True

    def test_color_match(self):
        gt = "https://www.mercari.com/search/?keyword=bag&colorIds=1"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(gt, gt)
        assert match is True

    def test_color_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=bag&colorIds=1"
        agent = "https://www.mercari.com/search/?keyword=bag&colorIds=2"
        v = MercariUrlMatch(gt_url=gt)
        match, d = v._urls_match(agent, gt)
        assert match is False
        assert "Color" in d["mismatches"][0]

    def test_sort_alias_match(self):
        gt = "https://www.mercari.com/search/?keyword=shoes&sortBy=2"
        agent = "https://www.mercari.com/search/?keyword=shoes&sortBy=newest"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(agent, gt)
        assert match is True

    def test_condition_order_independent(self):
        gt = "https://www.mercari.com/search/?keyword=bag&itemConditions=1-2"
        agent = "https://www.mercari.com/search/?keyword=bag&itemConditions=2-1"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(agent, gt)
        assert match is True

    def test_tracking_params_ignored(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000"
        agent = "https://www.mercari.com/search/?keyword=desk&minPrice=5000&utm_source=google&ref=homepage"
        v = MercariUrlMatch(gt_url=gt)
        match, _ = v._urls_match(agent, gt)
        assert match is True


# =========================================================================
# 11. Domain Validation
# =========================================================================


class TestDomainValidation:
    def test_www_mercari(self):
        assert MercariUrlMatch._is_valid_mercari_domain("www.mercari.com") is True

    def test_mercari(self):
        assert MercariUrlMatch._is_valid_mercari_domain("mercari.com") is True

    def test_subdomain(self):
        assert MercariUrlMatch._is_valid_mercari_domain("m.mercari.com") is True

    def test_reject_non_mercari(self):
        assert MercariUrlMatch._is_valid_mercari_domain("google.com") is False

    def test_reject_similar(self):
        assert MercariUrlMatch._is_valid_mercari_domain("fakemercari.com") is False

    def test_reject_different_tld(self):
        assert MercariUrlMatch._is_valid_mercari_domain("mercari.co.jp") is False


# =========================================================================
# 12. Async Lifecycle
# =========================================================================


class TestAsyncLifecycle:
    @pytest.mark.asyncio
    async def test_match_lifecycle(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000"
        v = MercariUrlMatch(gt_url=gt)
        await v.reset()
        await v.update(url=gt)
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_no_match_lifecycle(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000"
        agent = "https://www.mercari.com/search/?keyword=chair&minPrice=5000"
        v = MercariUrlMatch(gt_url=gt)
        await v.reset()
        await v.update(url=agent)
        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reset_clears_match(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        await v.update(url=gt)
        r1 = await v.compute()
        assert r1.score == 1.0
        await v.reset()
        r2 = await v.compute()
        assert r2.score == 0.0

    @pytest.mark.asyncio
    async def test_match_persists(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        await v.update(url=gt)
        await v.update(url="https://www.mercari.com/search/?keyword=chair")
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_empty_url_ignored(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        await v.update(url="")
        result = await v.compute()
        assert result.score == 0.0


# =========================================================================
# 13. Multi-GT URL OR Semantics
# =========================================================================


class TestMultiGtUrls:
    @pytest.mark.asyncio
    async def test_match_first(self):
        gts = [
            "https://www.mercari.com/search/?keyword=desk&minPrice=5000",
            "https://www.mercari.com/search/?keyword=desk&minPrice=10000",
        ]
        v = MercariUrlMatch(gt_url=gts)
        await v.update(url=gts[0])
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_match_second(self):
        gts = [
            "https://www.mercari.com/search/?keyword=desk&minPrice=5000",
            "https://www.mercari.com/search/?keyword=desk&minPrice=10000",
        ]
        v = MercariUrlMatch(gt_url=gts)
        await v.update(url=gts[1])
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_match_none(self):
        gts = [
            "https://www.mercari.com/search/?keyword=desk&minPrice=5000",
            "https://www.mercari.com/search/?keyword=desk&minPrice=10000",
        ]
        v = MercariUrlMatch(gt_url=gts)
        await v.update(url="https://www.mercari.com/search/?keyword=chair")
        result = await v.compute()
        assert result.score == 0.0


# =========================================================================
# 14. Edge Cases
# =========================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_non_mercari_url_ignored(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        await v.update(url="https://www.google.com/search?q=desk")
        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_item_listing_ignored(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        await v.update(url="https://www.mercari.com/us/item/m72277772433/")
        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_detailed_result_mismatch(self):
        gt = "https://www.mercari.com/search/?keyword=desk&minPrice=5000"
        agent = "https://www.mercari.com/search/?keyword=chair&minPrice=10000"
        v = MercariUrlMatch(gt_url=gt)
        await v.update(url=agent)
        result = await v.compute_detailed()
        assert result.score == 0.0
        assert result.match is False
        assert result.agent_url == agent

    def test_repr(self):
        v = MercariUrlMatch(gt_url="https://www.mercari.com/search/?keyword=test")
        assert "MercariUrlMatch" in repr(v)

    @pytest.mark.asyncio
    async def test_homepage_url(self):
        gt = "https://www.mercari.com/search/?keyword=desk"
        v = MercariUrlMatch(gt_url=gt)
        await v.update(url="https://www.mercari.com/")
        result = await v.compute()
        assert result.score == 0.0


# =========================================================================
# 15. Normalization Helpers
# =========================================================================


class TestNormalizationHelpers:
    def test_shipping_free(self):
        assert _normalize_shipping_payer("2") == "2"
        assert _normalize_shipping_payer("free") == "2"

    def test_shipping_empty(self):
        assert _normalize_shipping_payer("") == ""

    def test_country_source_values(self):
        assert _normalize_country_source("1") == "1"
        assert _normalize_country_source("2") == "2"

    def test_status_values(self):
        assert _normalize_status("1") == "1"
        assert _normalize_status("active") == "1"

    def test_sort_aliases(self):
        assert _normalize_sort_order("price_asc") == "3"
        assert _normalize_sort_order("price_desc") == "4"
        assert _normalize_sort_order("best_match") == "1"

    def test_condition_aliases(self):
        assert _normalize_conditions("good") == ["3"]
        assert _normalize_conditions("fair") == ["4"]
        assert _normalize_conditions("poor") == ["5"]
