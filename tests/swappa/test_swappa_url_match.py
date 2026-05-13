"""Comprehensive tests for SwappaUrlMatch verifier.

Browser-verified against swappa.com (May 2026).
Tests cover: URL parsing, domain validation, product slug matching,
carrier/condition/storage/color/sort normalization, full URL comparison,
async lifecycle, multi-GT URLs, and edge cases.
"""

import pytest

from navi_bench.swappa.swappa_url_match import (
    SwappaUrlMatch,
    parse_swappa_url,
    _normalize_slug,
    _normalize_carrier,
    _normalize_condition,
    _normalize_sort,
    _normalize_storage,
    _normalize_color,
    _extract_product_slug,
    _extract_carrier_from_path,
)


# =============================================================================
# URL Parsing Tests
# =============================================================================


class TestParseSwappaUrl:
    """Test the full URL parser."""

    def test_listings_page_with_all_filters(self):
        url = "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint&storage=128gb&color=black&sort=price_low"
        result = parse_swappa_url(url)
        assert result["product_slug"] == "apple-iphone-15"
        assert result["carrier"] == "unlocked"
        assert result["condition"] == "mint"
        assert result["storage"] == "128gb"
        assert result["color"] == "black"
        assert result["sort"] == "price_low"
        assert result["page_type"] == "listings"

    def test_buy_page_product_only(self):
        url = "https://swappa.com/buy/apple-iphone-15"
        result = parse_swappa_url(url)
        assert result["product_slug"] == "apple-iphone-15"
        assert result["carrier"] == ""
        assert result["condition"] == ""
        assert result["page_type"] == "buy"

    def test_buy_page_with_carrier_in_path(self):
        url = "https://swappa.com/buy/apple-iphone-15/unlocked"
        result = parse_swappa_url(url)
        assert result["carrier"] == "unlocked"

    def test_listings_page_carrier_query_param(self):
        url = "https://swappa.com/listings/samsung-galaxy-s24?carrier=unlocked"
        result = parse_swappa_url(url)
        assert result["product_slug"] == "samsung-galaxy-s24"
        assert result["carrier"] == "unlocked"

    def test_listings_page_with_condition_and_sort(self):
        url = "https://swappa.com/listings/apple-iphone-14-pro?condition=mint&sort=price_low"
        result = parse_swappa_url(url)
        assert result["product_slug"] == "apple-iphone-14-pro"
        assert result["condition"] == "mint"
        assert result["sort"] == "price_low"

    def test_category_page_no_product(self):
        url = "https://swappa.com/buy/phones"
        result = parse_swappa_url(url)
        assert result["product_slug"] == "phones"
        assert result["page_type"] == "buy"

    def test_laptop_product_page(self):
        url = "https://swappa.com/listings/macbook-pro-2026-16-m5"
        result = parse_swappa_url(url)
        assert result["product_slug"] == "macbook-pro-2026-16-m5"
        assert result["page_type"] == "listings"

    def test_empty_url(self):
        result = parse_swappa_url("")
        assert result["product_slug"] == ""
        assert result["carrier"] == ""


# =============================================================================
# Normalization Helper Tests
# =============================================================================


class TestNormalizeSlug:
    """Test product slug normalization."""

    def test_basic_slug(self):
        assert _normalize_slug("apple-iphone-15") == "apple-iphone-15"

    def test_uppercase_slug(self):
        assert _normalize_slug("Apple-iPhone-15") == "apple-iphone-15"

    def test_slug_with_slashes(self):
        assert _normalize_slug("/apple-iphone-15/") == "apple-iphone-15"

    def test_double_hyphens(self):
        assert _normalize_slug("apple--iphone--15") == "apple-iphone-15"

    def test_empty_slug(self):
        assert _normalize_slug("") == ""


class TestNormalizeCarrier:
    """Test carrier normalization."""

    def test_unlocked(self):
        assert _normalize_carrier("unlocked") == "unlocked"

    def test_att(self):
        assert _normalize_carrier("att") == "att"

    def test_tmobile_hyphen(self):
        assert _normalize_carrier("t-mobile") == "tmobile"

    def test_tmobile_no_hyphen(self):
        assert _normalize_carrier("tmobile") == "tmobile"

    def test_verizon(self):
        assert _normalize_carrier("verizon") == "verizon"

    def test_case_insensitive(self):
        assert _normalize_carrier("UNLOCKED") == "unlocked"
        assert _normalize_carrier("Verizon") == "verizon"

    def test_us_cellular_variants(self):
        assert _normalize_carrier("us-cellular") == "us-cellular"
        assert _normalize_carrier("us_cellular") == "us-cellular"
        assert _normalize_carrier("uscellular") == "us-cellular"

    def test_mint_mobile_variants(self):
        assert _normalize_carrier("mint-mobile") == "mint"
        assert _normalize_carrier("mintmobile") == "mint"

    def test_google_fi(self):
        assert _normalize_carrier("google-fi") == "google-fi"
        assert _normalize_carrier("googlefi") == "google-fi"

    def test_empty(self):
        assert _normalize_carrier("") == ""

    def test_at_t_hyphenated(self):
        assert _normalize_carrier("at-t") == "att"

    def test_consumer_cellular(self):
        assert _normalize_carrier("consumer-cellular") == "consumer-cellular"
        assert _normalize_carrier("consumer_cellular") == "consumer-cellular"
        assert _normalize_carrier("consumercellular") == "consumer-cellular"

    def test_tracfone(self):
        assert _normalize_carrier("tracfone") == "tracfone"
        assert _normalize_carrier("trac-fone") == "tracfone"

    def test_red_pocket(self):
        assert _normalize_carrier("red-pocket") == "red-pocket"
        assert _normalize_carrier("red_pocket") == "red-pocket"

    def test_mint_canonical(self):
        """carrier=mint is canonical; mint-mobile is an alias for mint."""
        assert _normalize_carrier("mint") == "mint"
        assert _normalize_carrier("mint-mobile") == "mint"
        assert _normalize_carrier("mintmobile") == "mint"


class TestNormalizeCondition:
    """Test condition normalization."""

    def test_canonical_values(self):
        assert _normalize_condition("new") == "new"
        assert _normalize_condition("mint") == "mint"
        assert _normalize_condition("good") == "good"
        assert _normalize_condition("fair") == "fair"

    def test_aliases(self):
        assert _normalize_condition("like_new") == "mint"
        assert _normalize_condition("like new") == "mint"
        assert _normalize_condition("excellent") == "mint"
        assert _normalize_condition("used") == "good"
        assert _normalize_condition("acceptable") == "fair"

    def test_case_insensitive(self):
        assert _normalize_condition("MINT") == "mint"
        assert _normalize_condition("Good") == "good"

    def test_empty(self):
        assert _normalize_condition("") == ""


class TestNormalizeSort:
    """Test sort order normalization."""

    def test_canonical_values(self):
        assert _normalize_sort("price_low") == "price_low"
        assert _normalize_sort("price_high") == "price_high"
        assert _normalize_sort("listing_created_newest") == "listing_created_newest"
        assert _normalize_sort("listing_created_oldest") == "listing_created_oldest"

    def test_aliases(self):
        assert _normalize_sort("cheapest") == "price_low"
        assert _normalize_sort("cheapest first") == "price_low"
        assert _normalize_sort("price (low)") == "price_low"
        assert _normalize_sort("price (high)") == "price_high"
        assert _normalize_sort("newest") == "listing_created_newest"
        assert _normalize_sort("newest first") == "listing_created_newest"
        assert _normalize_sort("most recent") == "listing_created_newest"

    def test_case_insensitive(self):
        assert _normalize_sort("PRICE_LOW") == "price_low"

    def test_empty(self):
        assert _normalize_sort("") == ""

    def test_oldest_aliases(self):
        assert _normalize_sort("oldest") == "listing_created_oldest"
        assert _normalize_sort("oldest_first") == "listing_created_oldest"
        assert _normalize_sort("oldest first") == "listing_created_oldest"
        assert _normalize_sort("least_recent") == "listing_created_oldest"
        assert _normalize_sort("listing created (oldest)") == "listing_created_oldest"


class TestNormalizeStorage:
    """Test storage normalization."""

    def test_canonical_values(self):
        assert _normalize_storage("128gb") == "128gb"
        assert _normalize_storage("256gb") == "256gb"
        assert _normalize_storage("512gb") == "512gb"
        assert _normalize_storage("1tb") == "1tb"

    def test_with_space(self):
        assert _normalize_storage("128 gb") == "128gb"
        assert _normalize_storage("256 gb") == "256gb"
        assert _normalize_storage("1 tb") == "1tb"

    def test_number_only(self):
        assert _normalize_storage("128") == "128gb"
        assert _normalize_storage("256") == "256gb"
        assert _normalize_storage("512") == "512gb"

    def test_case_insensitive(self):
        assert _normalize_storage("128GB") == "128gb"
        assert _normalize_storage("1TB") == "1tb"

    def test_empty(self):
        assert _normalize_storage("") == ""


class TestNormalizeColor:
    """Test color normalization."""

    def test_basic(self):
        assert _normalize_color("black") == "black"
        assert _normalize_color("blue") == "blue"

    def test_uppercase(self):
        assert _normalize_color("BLACK") == "black"

    def test_space_to_hyphen(self):
        assert _normalize_color("space black") == "space-black"

    def test_empty(self):
        assert _normalize_color("") == ""

    def test_grey_alias(self):
        assert _normalize_color("grey") == "gray"
        assert _normalize_color("gray") == "gray"

    def test_titanium_colors(self):
        assert _normalize_color("natural-titanium") == "natural-titanium"
        assert _normalize_color("natural_titanium") == "natural-titanium"
        assert _normalize_color("titanium-black") == "black-titanium"
        assert _normalize_color("desert_titanium") == "desert-titanium"

    def test_rose_gold_aliases(self):
        assert _normalize_color("rose-gold") == "rose-gold"
        assert _normalize_color("rose_gold") == "rose-gold"
        assert _normalize_color("rosegold") == "rose-gold"


# =============================================================================
# Path Extraction Tests
# =============================================================================


class TestExtractProductSlug:
    """Test product slug extraction from URL paths."""

    def test_buy_page(self):
        assert _extract_product_slug("/buy/apple-iphone-15") == "apple-iphone-15"

    def test_listings_page(self):
        assert _extract_product_slug("/listings/apple-iphone-15") == "apple-iphone-15"

    def test_samsung(self):
        assert _extract_product_slug("/buy/samsung-galaxy-s24") == "samsung-galaxy-s24"

    def test_with_sub_path(self):
        slug = _extract_product_slug("/buy/apple-iphone-15/unlocked")
        assert slug == "apple-iphone-15"  # carrier stripped

    def test_with_sub_path_non_carrier(self):
        slug = _extract_product_slug("/buy/apple-iphone-15-pro-max")
        assert slug == "apple-iphone-15-pro-max"  # not a carrier, kept

    def test_category(self):
        assert _extract_product_slug("/buy/phones") == "phones"

    def test_empty(self):
        assert _extract_product_slug("") == ""


class TestExtractCarrierFromPath:
    """Test carrier extraction from URL path segments."""

    def test_carrier_in_product_path(self):
        assert _extract_carrier_from_path("/buy/apple-iphone-15/unlocked") == "unlocked"

    def test_carrier_as_category_prefix(self):
        assert _extract_carrier_from_path("/buy/unlocked/iphones") == "unlocked"

    def test_no_carrier_in_path(self):
        assert _extract_carrier_from_path("/buy/apple-iphone-15") == ""

    def test_listings_no_carrier(self):
        assert _extract_carrier_from_path("/listings/apple-iphone-15") == ""

    def test_empty(self):
        assert _extract_carrier_from_path("") == ""


# =============================================================================
# Domain Validation Tests
# =============================================================================


class TestDomainValidation:
    """Test Swappa domain validation."""

    def test_valid_swappa_com(self):
        assert SwappaUrlMatch._is_valid_swappa_domain("swappa.com") is True

    def test_valid_www(self):
        assert SwappaUrlMatch._is_valid_swappa_domain("www.swappa.com") is True

    def test_valid_subdomain(self):
        assert SwappaUrlMatch._is_valid_swappa_domain("m.swappa.com") is True

    def test_invalid_different_domain(self):
        assert SwappaUrlMatch._is_valid_swappa_domain("google.com") is False

    def test_invalid_similar_name(self):
        assert SwappaUrlMatch._is_valid_swappa_domain("fakeswappa.com") is False

    def test_invalid_mercari(self):
        assert SwappaUrlMatch._is_valid_swappa_domain("mercari.com") is False


# =============================================================================
# Full URL Match Tests — Product Slug
# =============================================================================


class TestProductSlugMatching:
    """Test product slug comparison between agent and GT."""

    @pytest.mark.asyncio
    async def test_exact_match(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/buy/apple-iphone-15")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_buy_vs_listings_equivalence(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15")
        await m.update(url="https://swappa.com/buy/apple-iphone-15")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/buy/Apple-iPhone-15")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_wrong_product(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/buy/samsung-galaxy-s24")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_missing_product(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/")
        result = await m.compute()
        assert result.score == 0.0


# =============================================================================
# Full URL Match Tests — Carrier
# =============================================================================


class TestCarrierMatching:
    """Test carrier filter matching."""

    @pytest.mark.asyncio
    async def test_carrier_match(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_carrier_mismatch(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=att")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_carrier_missing_when_required(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        await m.update(url="https://swappa.com/listings/apple-iphone-15")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_carrier_alias_tmobile(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?carrier=tmobile")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=t-mobile")
        result = await m.compute()
        assert result.score == 1.0


# =============================================================================
# Full URL Match Tests — Condition
# =============================================================================


class TestConditionMatching:
    """Test condition filter matching."""

    @pytest.mark.asyncio
    async def test_condition_match(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?condition=mint")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?condition=mint")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_condition_mismatch(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?condition=mint")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?condition=good")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_condition_missing_when_required(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?condition=mint")
        await m.update(url="https://swappa.com/listings/apple-iphone-15")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_condition_alias_like_new(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?condition=mint")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?condition=like_new")
        result = await m.compute()
        assert result.score == 1.0


# =============================================================================
# Full URL Match Tests — Storage
# =============================================================================


class TestStorageMatching:
    """Test storage filter matching."""

    @pytest.mark.asyncio
    async def test_storage_match(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?storage=128gb")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?storage=128gb")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_storage_mismatch(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?storage=128gb")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?storage=256gb")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_storage_missing_when_required(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?storage=128gb")
        await m.update(url="https://swappa.com/listings/apple-iphone-15")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_storage_alias_with_space(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?storage=128gb")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?storage=128+gb")
        result = await m.compute()
        assert result.score == 1.0


# =============================================================================
# Full URL Match Tests — Sort
# =============================================================================


class TestSortMatching:
    """Test sort order matching."""

    @pytest.mark.asyncio
    async def test_sort_match(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?sort=price_low")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?sort=price_low")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_sort_listing_created_newest(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?sort=listing_created_newest")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?sort=listing_created_newest")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_sort_alias_newest_matches_listing_created(self):
        """Agent URL using 'newest' alias should match GT 'listing_created_newest'."""
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?sort=listing_created_newest")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?sort=newest")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_sort_mismatch(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?sort=price_low")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?sort=listing_created_newest")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_sort_missing_when_required(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?sort=price_low")
        await m.update(url="https://swappa.com/listings/apple-iphone-15")
        result = await m.compute()
        assert result.score == 0.0


# =============================================================================
# Full URL Match Tests — Color
# =============================================================================


class TestColorMatching:
    """Test color filter matching."""

    @pytest.mark.asyncio
    async def test_color_match(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?color=black")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?color=black")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_color_mismatch(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?color=black")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?color=blue")
        result = await m.compute()
        assert result.score == 0.0


# =============================================================================
# Full URL Match Tests — Combination
# =============================================================================


class TestCombinationMatching:
    """Test multiple filters combined."""

    @pytest.mark.asyncio
    async def test_full_filter_match(self):
        gt = "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint&storage=128gb&sort=price_low"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_missing_one_filter(self):
        gt = "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint&storage=128gb"
        m = SwappaUrlMatch(gt)
        # Agent omits storage
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_extra_agent_params_ok(self):
        gt = "https://swappa.com/listings/apple-iphone-15?carrier=unlocked"
        m = SwappaUrlMatch(gt)
        # Agent has extra params not in GT — should still pass
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint&sort=price_low")
        result = await m.compute()
        assert result.score == 1.0


# =============================================================================
# Async Lifecycle Tests
# =============================================================================


class TestAsyncLifecycle:
    """Test the reset → update → compute lifecycle."""

    @pytest.mark.asyncio
    async def test_reset_clears_match(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/buy/apple-iphone-15")
        result = await m.compute()
        assert result.score == 1.0

        await m.reset()
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_no_update_returns_zero(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_first_match_sticky(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/buy/apple-iphone-15")
        # Second update with wrong URL should not overwrite
        await m.update(url="https://swappa.com/buy/samsung-galaxy-s24")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_compute_detailed(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/buy/apple-iphone-15")
        result = await m.compute_detailed()
        assert result.score == 1.0
        assert result.match is True

    @pytest.mark.asyncio
    async def test_repr(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        r = repr(m)
        assert "SwappaUrlMatch" in r


# =============================================================================
# Multi-GT URL Tests
# =============================================================================


class TestMultiGtUrls:
    """Test OR semantics with multiple ground truth URLs."""

    @pytest.mark.asyncio
    async def test_matches_first_gt(self):
        m = SwappaUrlMatch([
            "https://swappa.com/listings/apple-iphone-15?carrier=unlocked",
            "https://swappa.com/buy/apple-iphone-15/unlocked",
        ])
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_matches_second_gt(self):
        m = SwappaUrlMatch([
            "https://swappa.com/listings/apple-iphone-15?carrier=att",
            "https://swappa.com/listings/apple-iphone-15?carrier=unlocked",
        ])
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_matches_none(self):
        m = SwappaUrlMatch([
            "https://swappa.com/listings/apple-iphone-15?carrier=att",
            "https://swappa.com/listings/apple-iphone-15?carrier=verizon",
        ])
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        result = await m.compute()
        assert result.score == 0.0


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_non_swappa_url_ignored(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://mercari.com/search/?keyword=iphone")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_individual_listing_ignored(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://swappa.com/listing/view/LAEU99283")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_empty_url_ignored(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_tracking_params_ignored(self):
        m = SwappaUrlMatch("https://swappa.com/listings/apple-iphone-15?carrier=unlocked")
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=unlocked&srsltid=abc123&utm_source=google")
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_www_domain(self):
        m = SwappaUrlMatch("https://swappa.com/buy/apple-iphone-15")
        await m.update(url="https://www.swappa.com/buy/apple-iphone-15")
        result = await m.compute()
        assert result.score == 1.0


# =============================================================================
# New Params Tests (modeln, edition, checkboxes, memory, processor)
# =============================================================================


class TestNewParams:
    """Test new parameters added for team CSV compatibility."""

    @pytest.mark.asyncio
    async def test_modeln_match(self):
        gt = "https://swappa.com/listings/apple-iphone-15-pro?carrier=verizon&modeln=QTI4NDg"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_modeln_missing_fails(self):
        gt = "https://swappa.com/listings/apple-iphone-15-pro?carrier=verizon&modeln=QTI4NDg"
        m = SwappaUrlMatch(gt)
        await m.update(url="https://swappa.com/listings/apple-iphone-15-pro?carrier=verizon")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_edition_match(self):
        gt = "https://swappa.com/listings/google-pixel-8-pro?edition=bW1XYXZlIDVH"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_edition_missing_fails(self):
        gt = "https://swappa.com/listings/google-pixel-8-pro?edition=bW1XYXZlIDVH"
        m = SwappaUrlMatch(gt)
        await m.update(url="https://swappa.com/listings/google-pixel-8-pro")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_exclude_businesses_match(self):
        gt = "https://swappa.com/listings/apple-watch-series-8-41mm?exclude_businesses=on"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_exclude_businesses_missing_fails(self):
        gt = "https://swappa.com/listings/apple-watch-series-8-41mm?exclude_businesses=on"
        m = SwappaUrlMatch(gt)
        await m.update(url="https://swappa.com/listings/apple-watch-series-8-41mm")
        result = await m.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_phone_check_certified_match(self):
        gt = "https://swappa.com/listings/samsung-galaxy-s23-ultra?phone_check_certified=on"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_accepts_stripe_match(self):
        gt = "https://swappa.com/listings/apple-iphone-11-pro-max?accepts_stripe=on"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_international_match(self):
        gt = "https://swappa.com/listings/apple-iphone-11-pro-max?international=on"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_memory_match(self):
        gt = "https://swappa.com/listings/macbook-air-2022-13?memory=16gb"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_processor_match(self):
        gt = "https://swappa.com/listings/apple-macbook-air-2023-15?processor=apple-m2"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_full_laptop_combo(self):
        gt = "https://swappa.com/listings/apple-macbook-air-2023-15?condition=mint&memory=24gb&processor=apple-m2&sort=price_low"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_full_combo_with_checkboxes(self):
        gt = "https://swappa.com/listings/apple-iphone-15-pro?carrier=verizon&color=blue&storage=256gb&modeln=QTI4NDg&international=on"
        m = SwappaUrlMatch(gt)
        await m.update(url=gt)
        result = await m.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_carrier_mint_alias(self):
        gt = "https://swappa.com/listings/apple-iphone-15?carrier=mint"
        m = SwappaUrlMatch(gt)
        await m.update(url="https://swappa.com/listings/apple-iphone-15?carrier=mint-mobile")
        result = await m.compute()
        assert result.score == 1.0
