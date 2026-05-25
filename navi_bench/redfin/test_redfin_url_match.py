"""Pytest unit tests for Redfin URL Match verifier.

Tests the RedfinUrlState and RedfinUrlMatch classes for property search
navigation verification.
"""

import pytest

from navi_bench.redfin.redfin_url_match import (
    RedfinUrlMatch,
    RedfinUrlState,
    generate_task_config,
)

# =============================================================================
# RedfinUrlState Tests
# =============================================================================


class TestRedfinUrlStateUrlNormalization:
    """Test URL normalization in RedfinUrlState."""

    def test_lowercase_conversion(self):
        state = RedfinUrlState("HTTPS://WWW.REDFIN.COM/CITY/1/WA/Seattle")
        assert "redfin.com" in state.url
        assert "seattle" in state.url

    def test_protocol_removal(self):
        state_https = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle")
        state_http = RedfinUrlState("http://www.redfin.com/city/1/WA/Seattle")
        assert state_https.url == state_http.url

    def test_www_removal(self):
        state_www = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle")
        state_no_www = RedfinUrlState("https://redfin.com/city/1/WA/Seattle")
        assert state_www.url == state_no_www.url

    def test_whitespace_stripping(self):
        state = RedfinUrlState("  https://www.redfin.com/city/1/WA/Seattle  ")
        assert not state.url.startswith(" ")
        assert not state.url.endswith(" ")

    def test_url_decoding(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/move-in-date=1%2F15%2F2026")
        assert "%2F" not in state.url


class TestRedfinUrlStateLocationParsing:
    """Test location parsing for various URL types."""

    def test_city_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/city/29470/IL/Chicago")
        assert state.loc_type == "city"
        assert state.loc_id == "29470"
        assert state.state == "il"
        assert state.loc_name == "chicago"
        assert "29470" in state.regions

    def test_neighborhood_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/neighborhood/219258/NY/New-York/Brooklyn")
        assert state.loc_type == "neighborhood"
        assert state.loc_id == "219258"
        assert state.state == "ny"
        assert "new-york/brooklyn" in state.loc_name

    def test_county_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/county/2362/PA/Allegheny-County")
        assert state.loc_type == "county"
        assert state.loc_id == "2362"
        assert state.state == "pa"

    def test_zipcode_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/zipcode/12345/CA/90210")
        assert state.loc_type == "zipcode"
        assert state.loc_id == "12345"

    def test_school_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/school/12345/WA/Seattle/Garfield-HS")
        assert state.loc_type == "school"
        assert state.loc_id == "12345"

    def test_school_district_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/school-district/5678/TX/Austin/Austin-ISD")
        assert state.loc_type == "school-district"
        assert state.loc_id == "5678"

    def test_real_estate_agents_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/real-estate-agents/david-tom")
        assert state.loc_type == "real-estate-agents"
        assert state.loc_id == "david-tom"

    def test_home_url_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/home/123456789")
        assert state.loc_type == "home"
        assert state.loc_id == "123456789"


class TestRedfinUrlStateRentalDetection:
    """Test rental vs sale listing detection."""

    def test_rentals_path_detected(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/rentals/filter/min-beds=2")
        assert state.is_rental is True

    def test_apartments_for_rent_detected(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/apartments-for-rent/filter/min-beds=2")
        assert state.is_rental is True

    def test_sale_listing_not_rental(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=2")
        assert state.is_rental is False


class TestRedfinUrlStateFilterParsing:
    """Test filter segment parsing."""

    def test_basic_key_value_filters(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,max-price=500000")
        assert state.filters.get("min-beds") == "3"
        assert state.filters.get("max-price") == "500000"

    def test_boolean_filters(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/is-fixer,has-elevator")
        assert state.filters.get("is-fixer") == "true"
        assert state.filters.get("has-elevator") == "true"

    def test_multi_value_filters(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house+condo")
        prop_type = state.filters.get("property-type")
        assert isinstance(prop_type, tuple)
        assert "house" in prop_type
        assert "condo" in prop_type

    def test_multi_value_filter_order_independence(self):
        state1 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house+condo")
        state2 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/property-type=condo+house")
        assert state1.filters.get("property-type") == state2.filters.get("property-type")

    def test_ignored_parameters(self):
        state = RedfinUrlState(
            "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,viewport=47:-122:48:-121,no-outline"
        )
        assert "viewport" not in state.filters
        assert "no-outline" not in state.filters
        assert state.filters.get("min-beds") == "3"


class TestRedfinUrlStateMultiRegion:
    """Test multi-region parameter parsing."""

    def test_multi_region_parsing(self):
        state = RedfinUrlState("https://www.redfin.com/city/20119/IL/West-Dundee/rentals/filter/mr=6:29470+1:30062")
        assert "20119" in state.regions
        assert "29470" in state.regions
        assert "30062" in state.regions

    def test_single_region_in_mr(self):
        state = RedfinUrlState("https://www.redfin.com/neighborhood/30062/IL/Chicago/West-Loop/filter/mr=6:29470")
        assert "30062" in state.regions
        assert "29470" in state.regions


class TestRedfinUrlStateParameterAliases:
    """Test parameter name normalization (aliases)."""

    def test_time_on_market_aliases(self):
        state1 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=7days")
        state2 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/max-days-on-market=7days")
        state3 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/days-on-market=7days")
        # All should normalize to same key
        assert "time-on-market" in state1.filters
        assert "time-on-market" in state2.filters
        assert "time-on-market" in state3.filters

    def test_waterfront_aliases(self):
        state1 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/water-front")
        state2 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/has-waterfront")
        assert "water-front" in state1.filters
        assert "water-front" in state2.filters

    def test_pool_aliases(self):
        state1 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/pool-type=private")
        state2 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/has-pool=private")
        assert state1.filters.get("pool-type") == state2.filters.get("pool-type")

    def test_basement_aliases(self):
        state1 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/basement-type=finished")
        state2 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/has-basement=finished")
        assert state1.filters.get("basement-type") == state2.filters.get("basement-type")


class TestRedfinUrlStateValueNormalization:
    """Test parameter value normalization."""

    def test_price_k_abbreviation(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/max-price=500k")
        assert state.filters.get("max-price") == "500000"

    def test_price_m_abbreviation(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/max-price=2m")
        assert state.filters.get("max-price") == "2000000"

    def test_price_decimal_m_abbreviation(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/max-price=1.5M")
        assert state.filters.get("max-price") == "1500000"

    def test_sqft_k_abbreviation(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-sqft=3k")
        assert state.filters.get("min-sqft") == "3000"

    def test_sqft_suffix_removal(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-sqft=1500-sqft")
        assert state.filters.get("min-sqft") == "1500"

    def test_time_week_normalization(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=1wk")
        assert state.filters.get("time-on-market") == "7days"

    def test_time_month_normalization(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=1mo")
        assert state.filters.get("time-on-market") == "30days"


class TestRedfinUrlStateFilterConsolidation:
    """Test filter consolidation (beds, baths, stories)."""

    def test_beds_consolidation(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/beds=3")
        assert state.filters.get("min-beds") == "3"
        assert state.filters.get("max-beds") == "3"
        assert "beds" not in state.filters

    def test_baths_consolidation(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/baths=2")
        assert state.filters.get("min-baths") == "2"
        assert state.filters.get("max-baths") == "2"
        assert "baths" not in state.filters

    def test_stories_consolidation_same_values(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-stories=2,max-stories=2")
        assert state.filters.get("stories") == "2"
        assert "num-stories-min" not in state.filters
        assert "num-stories-max" not in state.filters


class TestRedfinUrlStateMatching:
    """Test the matches() method."""

    def test_exact_match(self):
        gt = RedfinUrlState("https://www.redfin.com/city/29470/IL/Chicago/filter/property-type=condo")
        agent = RedfinUrlState("https://www.redfin.com/city/29470/IL/Chicago/filter/property-type=condo")
        result = agent.matches(gt)
        assert result["match"] is True
        assert len(result["evidence"]) == 0

    def test_region_mismatch(self):
        gt = RedfinUrlState("https://www.redfin.com/city/29470/IL/Chicago")
        agent = RedfinUrlState("https://www.redfin.com/city/99999/IL/Chicago")
        result = agent.matches(gt)
        assert result["match"] is False
        assert any("Region" in e for e in result["evidence"])

    def test_location_type_mismatch(self):
        gt = RedfinUrlState("https://www.redfin.com/city/29470/IL/Chicago")
        agent = RedfinUrlState("https://www.redfin.com/neighborhood/29470/IL/Chicago/Downtown")
        result = agent.matches(gt)
        assert result["match"] is False

    def test_rental_status_mismatch(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/rentals")
        result = agent.matches(gt)
        assert result["match"] is False
        assert any("Rental" in e for e in result["evidence"])

    def test_filter_value_mismatch(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4")
        result = agent.matches(gt)
        assert result["match"] is False
        assert any("mismatch" in e.lower() for e in result["evidence"])

    def test_missing_filter(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,max-price=500k")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3")
        result = agent.matches(gt)
        assert result["match"] is False
        assert any("Missing" in e for e in result["evidence"])

    def test_extra_filter(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,max-price=500k")
        result = agent.matches(gt)
        assert result["match"] is False
        assert any("Extra" in e for e in result["evidence"])

    def test_filter_order_independence(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,max-price=500k")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/max-price=500k,min-beds=3")
        result = agent.matches(gt)
        assert result["match"] is True

    def test_case_insensitivity(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/property-type=house")
        agent = RedfinUrlState("HTTPS://WWW.REDFIN.COM/CITY/1/WA/SEATTLE/FILTER/PROPERTY-TYPE=HOUSE")
        result = agent.matches(gt)
        assert result["match"] is True


class TestRedfinUrlStateViewport:
    """Test viewport handling.

    Note: In the current implementation, viewport is in IGNORED_PARAMS,
    so it's treated as an ignored UI parameter and doesn't affect matching.
    """

    def test_viewport_is_ignored_in_matching(self):
        """Viewport differences don't affect matching since viewport is ignored."""
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3")
        agent = RedfinUrlState(
            "https://www.redfin.com/city/1/WA/Seattle/filter/viewport=38.0:35.0:-76.0:-79.0,min-beds=3"
        )
        result = agent.matches(gt)
        assert result["match"] is True

    def test_different_viewports_still_match(self):
        """Different viewports match since viewport is ignored."""
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/viewport=38.0:35.0:-76.0:-79.0,min-beds=3")
        agent = RedfinUrlState(
            "https://www.redfin.com/city/1/WA/Seattle/filter/viewport=40.0:36.0:-77.0:-80.0,min-beds=3"
        )
        result = agent.matches(gt)
        assert result["match"] is True

    def test_viewport_not_required(self):
        """Missing viewport doesn't cause mismatch since it's ignored."""
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/viewport=38.0:35.0:-76.0:-79.0,min-beds=3")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3")
        result = agent.matches(gt)
        assert result["match"] is True

    def test_viewport_not_stored_in_filters(self):
        """Viewport is not stored in the filters dict since it's ignored."""
        state = RedfinUrlState(
            "https://www.redfin.com/city/1/WA/Seattle/filter/viewport=38.0:35.0:-76.0:-79.0,min-beds=3"
        )
        assert "viewport" not in state.filters
        assert state.filters.get("min-beds") == "3"


class TestRedfinUrlStateSortOrder:
    """Test sort order verification."""

    def test_sort_verified_when_present(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/sort=lo-price")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/sort=lo-price")
        result = agent.matches(gt)
        assert result["match"] is True

    def test_missing_sort_fails(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/sort=lo-price")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle")
        result = agent.matches(gt)
        assert result["match"] is False

    def test_extra_sort_fails(self):
        gt = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3")
        agent = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3,sort=hi-price")
        result = agent.matches(gt)
        assert result["match"] is False


# =============================================================================
# RedfinUrlMatch Async Tests
# =============================================================================


class TestRedfinUrlMatchBasic:
    """Test basic RedfinUrlMatch functionality."""

    @pytest.mark.asyncio
    async def test_exact_match_scores_1(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url=gt_url)
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_no_match_scores_0(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=4")
        result = await metric.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_empty_url_scores_0(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="")
        result = await metric.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reset_clears_match(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])

        await metric.update(url=gt_url)
        result1 = await metric.compute()
        assert result1.score == 1.0

        await metric.reset()
        result2 = await metric.compute()
        assert result2.score == 0.0


class TestRedfinUrlMatchMultipleGT:
    """Test RedfinUrlMatch with multiple ground truth URLs."""

    @pytest.mark.asyncio
    async def test_match_any_gt(self):
        gt_urls = [
            [
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-price=100k",
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-price=200k",
            ]
        ]
        metric = RedfinUrlMatch(gt_urls=gt_urls)
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/min-price=200k")
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_no_match_any_gt(self):
        gt_urls = [
            [
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-price=100k",
                "https://www.redfin.com/city/1/WA/Seattle/filter/min-price=200k",
            ]
        ]
        metric = RedfinUrlMatch(gt_urls=gt_urls)
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/min-price=300k")
        result = await metric.compute()
        assert result.score == 0.0


class TestRedfinUrlMatchPriceNormalization:
    """Test price normalization in matching."""

    @pytest.mark.asyncio
    async def test_price_500k_equals_500000(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=500000"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/max-price=500k")
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_price_2m_equals_2000000(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=2000000"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/max-price=2m")
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_price_1_5m_equals_1500000(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/max-price=1500000"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/max-price=1.5M")
        result = await metric.compute()
        assert result.score == 1.0


class TestRedfinUrlMatchTimeNormalization:
    """Test time value normalization in matching."""

    @pytest.mark.asyncio
    async def test_time_1wk_equals_7days(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=7days"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=1wk")
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_max_days_on_market_alias(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle/filter/time-on-market=7days"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/1/WA/Seattle/filter/max-days-on-market=1wk")
        result = await metric.compute()
        assert result.score == 1.0


class TestRedfinUrlMatchRealWorldScenarios:
    """Test real-world scenarios from CSV cases."""

    @pytest.mark.asyncio
    async def test_chicago_rental_with_att_fiber(self):
        gt_url = (
            "https://www.redfin.com/city/29470/IL/Chicago/rentals/filter/"
            "min-price=800,max-price=1.5k,min-beds=2,min-baths=1,air-conditioning,has-att-fiber"
        )
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(
            url=(
                "https://www.redfin.com/city/29470/IL/Chicago/rentals/filter/"
                "min-price=800,max-price=1500,min-beds=2,min-baths=1,air-conditioning,has-att-fiber"
            )
        )
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_portland_sold_listings(self):
        gt_url = "https://www.redfin.com/city/30772/OR/Portland/filter/min-baths=2,include=sold-1mo"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(url="https://www.redfin.com/city/30772/OR/Portland/filter/include=sold-1mo,min-baths=2")
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_school_rating_multi_value(self):
        gt_url = (
            "https://www.redfin.com/city/30794/TX/Dallas/rentals/filter/"
            "school-rating=4,school-types=elementary+middle+high"
        )
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(
            url=(
                "https://www.redfin.com/city/30794/TX/Dallas/rentals/filter/"
                "school-types=high+elementary+middle,school-rating=4"
            )
        )
        result = await metric.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_complex_filter_with_ignored_params(self):
        gt_url = (
            "https://www.redfin.com/city/21853/MD/California/filter/"
            "property-type=other+co-op,min-sqft=1.1k-sqft,max-sqft=1.4k-sqft,"
            "min-year-built=2020,has-elevator"
        )
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        await metric.reset()
        await metric.update(
            url=(
                "https://www.redfin.com/city/21853/MD/California/filter/"
                "has-elevator,min-sqft=1100,"
                "property-type=co-op+other,"
                "max-sqft=1400,min-year-built=2020,"
                "no-outline,redirect"
            )
        )
        result = await metric.compute()
        assert result.score == 1.0


# =============================================================================
# generate_task_config Tests
# =============================================================================


class TestGenerateTaskConfig:
    """Test task configuration generation."""

    def test_generates_valid_config(self):
        config = generate_task_config(
            task="Find houses in Seattle under $500k",
            gt_urls=[["https://www.redfin.com/city/1/WA/Seattle/filter/max-price=500k"]],
            location="Seattle, WA",
            timezone="America/Los_Angeles",
        )
        assert config.task == "Find houses in Seattle under $500k"
        assert config.url == "https://www.redfin.com"
        assert "gt_urls" in config.eval_config

    def test_accepts_custom_url(self):
        config = generate_task_config(
            task="Test task",
            gt_urls=[["https://www.redfin.com/city/1/WA/Seattle"]],
            location="Seattle, WA",
            timezone="America/Los_Angeles",
            url="https://www.redfin.com/city/1/WA/Seattle",
        )
        assert config.url == "https://www.redfin.com/city/1/WA/Seattle"

    def test_accepts_single_gt_url_string(self):
        config = generate_task_config(
            task="Test task",
            gt_urls=[["https://www.redfin.com/city/1/WA/Seattle"]],
            location="Seattle, WA",
            timezone="America/Los_Angeles",
        )
        assert config.eval_config["gt_urls"] == [["https://www.redfin.com/city/1/WA/Seattle"]]


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_url_with_trailing_slash(self):
        state1 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3/")
        state2 = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=3")
        result = state1.matches(state2)
        assert result["match"] is True

    def test_url_without_filter_segment(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle")
        assert state.filters == {}

    def test_empty_filter_values_ignored(self):
        state = RedfinUrlState("https://www.redfin.com/city/1/WA/Seattle/filter/min-beds=,max-beds=3")
        assert "min-beds" not in state.filters
        assert state.filters.get("max-beds") == "3"

    @pytest.mark.asyncio
    async def test_repr_method(self):
        gt_url = "https://www.redfin.com/city/1/WA/Seattle"
        metric = RedfinUrlMatch(gt_urls=[[gt_url]])
        repr_str = repr(metric)
        assert "RedfinUrlMatch" in repr_str
        assert "gt_urls" in repr_str
