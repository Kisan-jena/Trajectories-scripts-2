"""Comprehensive tests for IKEA US URL Match verifier.

Tests cover: URL parsing, keyword normalization, category slug extraction,
color ID normalization, sort normalization, filter parsing, domain validation,
URL matching rules, async lifecycle, multi-GT URLs, and edge cases.
"""

import pytest

from navi_bench.ikea.ikea_url_match import (
    COLOR_MAP,
    SORT_MAP,
    IkeaUrlMatch,
    IkeaVerifierResult,
    _detect_page_type,
    _extract_category_slug,
    _normalize_color,
    _normalize_keyword,
    _normalize_sort,
    _parse_filters,
    generate_task_config,
    parse_ikea_url,
)


# =============================================================================
# URL Parsing
# =============================================================================


class TestParseIkeaUrl:
    """Test full URL parsing pipeline."""

    def test_search_basic(self):
        r = parse_ikea_url("https://www.ikea.com/us/en/search/?q=desk")
        assert r["page_type"] == "search"
        assert r["keyword"] == "desk"
        assert r["filters"] == {}
        assert r["sort"] == ""

    def test_search_with_filters(self):
        r = parse_ikea_url(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"
        )
        assert r["page_type"] == "search"
        assert r["keyword"] == "desk"
        assert r["filters"] == {"f-colors": ["10156"]}
        assert r["sort"] == "PRICE_LOW_TO_HIGH"

    def test_category_basic(self):
        r = parse_ikea_url("https://www.ikea.com/us/en/cat/desks-20649/")
        assert r["page_type"] == "category"
        assert r["category_slug"] == "desks-20649"
        assert r["keyword"] == ""

    def test_category_with_filters(self):
        r = parse_ikea_url(
            "https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10003&sort=NEWEST"
        )
        assert r["page_type"] == "category"
        assert r["category_slug"] == "sofas-fu003"
        assert r["filters"] == {"f-colors": ["10003"]}
        assert r["sort"] == "NEWEST"

    def test_product_page(self):
        r = parse_ikea_url(
            "https://www.ikea.com/us/en/p/micke-desk-white-s30213076/"
        )
        assert r["page_type"] == "product"

    def test_multi_filter(self):
        r = parse_ikea_url(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156,f-price-buckets:PRICE_0_10000"
        )
        assert r["filters"] == {
            "f-colors": ["10156"],
            "f-price-buckets": ["PRICE_0_10000"],
        }

    def test_homepage(self):
        r = parse_ikea_url("https://www.ikea.com/us/en/")
        assert r["page_type"] == "other"

    def test_multi_word_keyword(self):
        r = parse_ikea_url("https://www.ikea.com/us/en/search/?q=bed+frame")
        assert r["keyword"] == "bed frame"


# =============================================================================
# Keyword Normalization
# =============================================================================


class TestNormalizeKeyword:
    def test_basic(self):
        assert _normalize_keyword("desk") == "desk"

    def test_case_insensitive(self):
        assert _normalize_keyword("DESK") == "desk"

    def test_whitespace_collapse(self):
        assert _normalize_keyword("  bed   frame  ") == "bed frame"

    def test_url_decode(self):
        assert _normalize_keyword("bed%20frame") == "bed frame"

    def test_empty(self):
        assert _normalize_keyword("") == ""


# =============================================================================
# Category Slug Extraction
# =============================================================================


class TestExtractCategorySlug:
    def test_basic(self):
        assert _extract_category_slug("/us/en/cat/desks-20649/") == "desks-20649"

    def test_complex_slug(self):
        assert (
            _extract_category_slug("/us/en/cat/bookcases-shelving-units-10382/")
            == "bookcases-shelving-units-10382"
        )

    def test_fu_suffix(self):
        assert _extract_category_slug("/us/en/cat/sofas-fu003/") == "sofas-fu003"

    def test_not_category(self):
        assert _extract_category_slug("/us/en/search/") == ""

    def test_empty(self):
        assert _extract_category_slug("") == ""


# =============================================================================
# Page Type Detection
# =============================================================================


class TestDetectPageType:
    def test_search(self):
        assert _detect_page_type("/us/en/search/") == "search"

    def test_category(self):
        assert _detect_page_type("/us/en/cat/desks-20649/") == "category"

    def test_product(self):
        assert _detect_page_type("/us/en/p/micke-desk-white-s30213076/") == "product"

    def test_homepage(self):
        assert _detect_page_type("/us/en/") == "other"

    def test_empty(self):
        assert _detect_page_type("") == "other"


# =============================================================================
# Color Normalization
# =============================================================================


class TestNormalizeColor:
    def test_canonical_white(self):
        assert _normalize_color("white") == "10156"

    def test_canonical_black(self):
        assert _normalize_color("black") == "10005"

    def test_canonical_beige(self):
        assert _normalize_color("beige") == "10003"

    def test_canonical_gray(self):
        assert _normalize_color("gray") == "10008"

    def test_alias_grey(self):
        assert _normalize_color("grey") == "10008"

    def test_alias_cream(self):
        assert _normalize_color("cream") == "10003"

    def test_alias_teal(self):
        assert _normalize_color("teal") == "10878"

    def test_alias_navy(self):
        assert _normalize_color("navy") == "10006"

    def test_numeric_passthrough(self):
        assert _normalize_color("10156") == "10156"

    def test_case_insensitive(self):
        assert _normalize_color("WHITE") == "10156"

    def test_brown(self):
        assert _normalize_color("brown") == "10017"

    def test_green(self):
        assert _normalize_color("green") == "10011"

    def test_empty(self):
        assert _normalize_color("") == ""


# =============================================================================
# Sort Normalization
# =============================================================================


class TestNormalizeSort:
    def test_canonical(self):
        assert _normalize_sort("PRICE_LOW_TO_HIGH") == "PRICE_LOW_TO_HIGH"

    def test_lowercase(self):
        assert _normalize_sort("price_low_to_high") == "PRICE_LOW_TO_HIGH"

    def test_alias_cheapest(self):
        assert _normalize_sort("cheapest") == "PRICE_LOW_TO_HIGH"

    def test_alias_most_expensive(self):
        assert _normalize_sort("most expensive") == "PRICE_HIGH_TO_LOW"

    def test_newest(self):
        assert _normalize_sort("NEWEST") == "NEWEST"

    def test_alias_newest_first(self):
        assert _normalize_sort("newest first") == "NEWEST"

    def test_rating(self):
        assert _normalize_sort("CUSTOMER_RATING") == "CUSTOMER_RATING"

    def test_alias_rating(self):
        assert _normalize_sort("rating") == "CUSTOMER_RATING"

    def test_name(self):
        assert _normalize_sort("NAME_ASCENDING") == "NAME_ASCENDING"

    def test_alias_alphabetical(self):
        assert _normalize_sort("alphabetical") == "NAME_ASCENDING"

    def test_most_popular(self):
        assert _normalize_sort("MOST_POPULAR") == "MOST_POPULAR"

    def test_empty(self):
        assert _normalize_sort("") == ""


# =============================================================================
# Filter Parsing
# =============================================================================


class TestParseFilters:
    def test_single_filter(self):
        r = _parse_filters("f-colors:10156")
        assert r == {"f-colors": ["10156"]}

    def test_multi_filter(self):
        r = _parse_filters("f-colors:10156,f-price-buckets:PRICE_0_10000")
        assert r == {
            "f-colors": ["10156"],
            "f-price-buckets": ["PRICE_0_10000"],
        }

    def test_empty(self):
        assert _parse_filters("") == {}

    def test_no_colon(self):
        assert _parse_filters("invalid") == {}

    def test_whitespace(self):
        r = _parse_filters("  f-colors:10156 , f-price-buckets:PRICE_0_10000  ")
        assert "f-colors" in r
        assert "f-price-buckets" in r

    def test_url_encoded(self):
        r = _parse_filters("f-colors%3A10156")
        # After unquote, f-colors:10156
        assert r == {"f-colors": ["10156"]}


# =============================================================================
# Domain Validation
# =============================================================================


class TestDomainValidation:
    def test_www(self):
        assert IkeaUrlMatch._is_valid_ikea_domain("www.ikea.com")

    def test_bare(self):
        assert IkeaUrlMatch._is_valid_ikea_domain("ikea.com")

    def test_subdomain(self):
        assert IkeaUrlMatch._is_valid_ikea_domain("m.ikea.com")

    def test_other_tld(self):
        assert not IkeaUrlMatch._is_valid_ikea_domain("ikea.co.uk")

    def test_fake(self):
        assert not IkeaUrlMatch._is_valid_ikea_domain("fakeikea.com")

    def test_trailing_dot(self):
        assert IkeaUrlMatch._is_valid_ikea_domain("www.ikea.com.")


# =============================================================================
# Search Matching
# =============================================================================


class TestSearchMatching:
    def test_exact_match(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk",
            "https://www.ikea.com/us/en/search/?q=desk",
        )
        assert match

    def test_case_insensitive_keyword(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=Desk",
            "https://www.ikea.com/us/en/search/?q=desk",
        )
        assert match

    def test_keyword_mismatch(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        match, details = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=sofa",
            "https://www.ikea.com/us/en/search/?q=desk",
        )
        assert not match
        assert any("keyword" in m.lower() for m in details["mismatches"])

    def test_keyword_missing(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        match, details = v._urls_match(
            "https://www.ikea.com/us/en/search/",
            "https://www.ikea.com/us/en/search/?q=desk",
        )
        assert not match

    def test_search_vs_category_mismatch(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/cat/desks-20649/",
            "https://www.ikea.com/us/en/search/?q=desk",
        )
        assert not match


# =============================================================================
# Category Matching
# =============================================================================


class TestCategoryMatching:
    def test_exact_match(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/cat/desks-20649/")
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/cat/desks-20649/",
            "https://www.ikea.com/us/en/cat/desks-20649/",
        )
        assert match

    def test_slug_mismatch(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/cat/desks-20649/")
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/cat/sofas-fu003/",
            "https://www.ikea.com/us/en/cat/desks-20649/",
        )
        assert not match

    def test_category_with_filter(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/cat/desks-20649/?filters=f-colors:10156"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/cat/desks-20649/?filters=f-colors:10156",
            "https://www.ikea.com/us/en/cat/desks-20649/?filters=f-colors:10156",
        )
        assert match

    def test_category_missing_filter(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/cat/desks-20649/?filters=f-colors:10156"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/cat/desks-20649/",
            "https://www.ikea.com/us/en/cat/desks-20649/?filters=f-colors:10156",
        )
        assert not match

    def test_case_insensitive_slug(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/cat/desks-20649/")
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/cat/Desks-20649/",
            "https://www.ikea.com/us/en/cat/desks-20649/",
        )
        assert match


# =============================================================================
# Color Filter Matching
# =============================================================================


class TestColorMatching:
    def test_exact_id_match(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156",
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156",
        )
        assert match

    def test_color_mismatch(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10005",
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156",
        )
        assert not match

    def test_color_missing(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk",
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156",
        )
        assert not match

    def test_extra_color_ok(self):
        """Agent has extra filter not in GT — should pass."""
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/search/?q=desk"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156",
            "https://www.ikea.com/us/en/search/?q=desk",
        )
        assert match


# =============================================================================
# Sort Matching
# =============================================================================


class TestSortMatching:
    def test_exact_match(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH",
            "https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH",
        )
        assert match

    def test_sort_mismatch(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&sort=NEWEST",
            "https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH",
        )
        assert not match

    def test_sort_missing(self):
        v = IkeaUrlMatch(
            gt_url="https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH"
        )
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk",
            "https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH",
        )
        assert not match


# =============================================================================
# Combination Matching
# =============================================================================


class TestCombinationMatching:
    def test_color_and_sort(self):
        gt = "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"
        v = IkeaUrlMatch(gt_url=gt)
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH",
            gt,
        )
        assert match

    def test_missing_one_filter(self):
        gt = "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"
        v = IkeaUrlMatch(gt_url=gt)
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH",
            gt,
        )
        assert not match

    def test_color_plus_price(self):
        gt = "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156,f-price-buckets:PRICE_0_10000"
        v = IkeaUrlMatch(gt_url=gt)
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156,f-price-buckets:PRICE_0_10000",
            gt,
        )
        assert match

    def test_extra_params_ok(self):
        gt = "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156"
        v = IkeaUrlMatch(gt_url=gt)
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&utm_source=google",
            gt,
        )
        assert match

    def test_category_color_sort(self):
        gt = "https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10003&sort=MOST_POPULAR"
        v = IkeaUrlMatch(gt_url=gt)
        match, _ = v._urls_match(
            "https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10003&sort=MOST_POPULAR",
            gt,
        )
        assert match


# =============================================================================
# Async Lifecycle
# =============================================================================


class TestAsyncLifecycle:
    @pytest.mark.asyncio
    async def test_update_and_compute_match(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        await v.reset()
        await v.update(url="https://www.ikea.com/us/en/search/?q=desk")
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_update_and_compute_no_match(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        await v.reset()
        await v.update(url="https://www.ikea.com/us/en/search/?q=sofa")
        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_sticky_match(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        await v.reset()
        await v.update(url="https://www.ikea.com/us/en/search/?q=desk")
        await v.update(url="https://www.ikea.com/us/en/search/?q=sofa")
        result = await v.compute()
        assert result.score == 1.0  # first match sticks

    @pytest.mark.asyncio
    async def test_empty_url_ignored(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        await v.reset()
        await v.update(url="")
        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_compute_detailed(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        await v.reset()
        await v.update(url="https://www.ikea.com/us/en/search/?q=desk")
        result = await v.compute_detailed()
        assert isinstance(result, IkeaVerifierResult)
        assert result.score == 1.0
        assert result.match is True


# =============================================================================
# Multi-GT URLs
# =============================================================================


class TestMultiGtUrls:
    @pytest.mark.asyncio
    async def test_first_matches(self):
        v = IkeaUrlMatch(
            gt_url=[
                "https://www.ikea.com/us/en/search/?q=desk",
                "https://www.ikea.com/us/en/search/?q=desks",
            ]
        )
        await v.reset()
        await v.update(url="https://www.ikea.com/us/en/search/?q=desk")
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_second_matches(self):
        v = IkeaUrlMatch(
            gt_url=[
                "https://www.ikea.com/us/en/search/?q=desk",
                "https://www.ikea.com/us/en/search/?q=desks",
            ]
        )
        await v.reset()
        await v.update(url="https://www.ikea.com/us/en/search/?q=desks")
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_none_match(self):
        v = IkeaUrlMatch(
            gt_url=[
                "https://www.ikea.com/us/en/search/?q=desk",
                "https://www.ikea.com/us/en/search/?q=desks",
            ]
        )
        await v.reset()
        await v.update(url="https://www.ikea.com/us/en/search/?q=sofa")
        result = await v.compute()
        assert result.score == 0.0


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_non_ikea_url_ignored(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        await v.reset()
        await v.update(url="https://www.wayfair.com/furniture/desks")
        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_product_page_ignored(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        await v.reset()
        await v.update(
            url="https://www.ikea.com/us/en/p/micke-desk-white-s30213076/"
        )
        result = await v.compute()
        assert result.score == 0.0

    def test_www_and_bare_domain(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        match, _ = v._urls_match(
            "https://ikea.com/us/en/search/?q=desk",
            "https://www.ikea.com/us/en/search/?q=desk",
        )
        assert match

    def test_repr(self):
        v = IkeaUrlMatch(gt_url="https://www.ikea.com/us/en/search/?q=desk")
        assert "IkeaUrlMatch" in repr(v)

    def test_generate_task_config_basic(self):
        cfg = generate_task_config(
            task="Search for desks on IKEA.",
            location="United States",
            timezone="America/Los_Angeles",
            gt_url=["https://www.ikea.com/us/en/search/?q=desk"],
        )
        assert cfg.url == "https://www.ikea.com/us/en/"
        assert "desk" in cfg.task.lower()
        assert "gt_url" in cfg.eval_config
