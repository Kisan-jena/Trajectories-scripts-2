"""
Pytest unit tests for Hotels.com URL Match verifier.

Tests cover:
- Domain validation
- URL parsing (destination, dates, guests, rooms, sort, filters)
- URL matching (exact match, mismatches, partial matches)
- Async lifecycle (reset, update, compute)
- Multi-GT URL support (OR semantics)
- Task config generation
- Edge cases (non-Hotels.com URLs, empty URLs, property pages)
"""

import pytest
from navi_bench.hotels_com.hotels_com_url_match import (
    HotelsComUrlMatch,
    HotelsComVerifierResult,
    generate_task_config,
    parse_hotels_com_url,
    _normalize_date,
    _normalize_sort,
    _normalize_destination,
    _parse_star_rating,
    _parse_amenities,
)


# =============================================================================
# Helpers
# =============================================================================

BASE = "https://www.hotels.com/Hotel-Search"
BASE_URL = "https://www.hotels.com"


def _v(gt_url):
    return HotelsComUrlMatch(gt_url=gt_url)


def _match(agent, gt):
    return _v(gt)._urls_match(agent, gt)


# =============================================================================
# 1. DOMAIN VALIDATION
# =============================================================================

class TestDomainValidation:

    def test_valid_primary_domains(self):
        v = _v(BASE)
        assert v._is_valid_hotels_com_domain("hotels.com")
        assert v._is_valid_hotels_com_domain("www.hotels.com")

    def test_valid_regional_domains(self):
        v = _v(BASE)
        assert v._is_valid_hotels_com_domain("in.hotels.com")
        assert v._is_valid_hotels_com_domain("uk.hotels.com")
        assert v._is_valid_hotels_com_domain("de.hotels.com")
        assert v._is_valid_hotels_com_domain("jp.hotels.com")

    def test_valid_any_subdomain(self):
        v = _v(BASE)
        assert v._is_valid_hotels_com_domain("xyz.hotels.com")
        assert v._is_valid_hotels_com_domain("test.staging.hotels.com")

    def test_invalid_domains(self):
        v = _v(BASE)
        assert not v._is_valid_hotels_com_domain("google.com")
        assert not v._is_valid_hotels_com_domain("fakehotels.com")
        assert not v._is_valid_hotels_com_domain("booking.com")
        assert not v._is_valid_hotels_com_domain("expedia.com")
        assert not v._is_valid_hotels_com_domain("hotels.co.uk")


# =============================================================================
# 2. NORMALIZATION HELPERS
# =============================================================================

class TestNormalizationHelpers:

    def test_normalize_date_yyyy_mm_dd(self):
        assert _normalize_date("2026-07-01") == "2026-07-01"

    def test_normalize_date_yyyy_m_d(self):
        assert _normalize_date("2026-7-1") == "2026-07-01"

    def test_normalize_date_m_d_yyyy(self):
        assert _normalize_date("7/1/2026") == "2026-07-01"

    def test_normalize_date_empty(self):
        assert _normalize_date("") == ""

    def test_normalize_sort_canonical(self):
        assert _normalize_sort("PRICE_LOW_TO_HIGH") == "PRICE_LOW_TO_HIGH"

    def test_normalize_sort_alias(self):
        assert _normalize_sort("cheapest") == "PRICE_LOW_TO_HIGH"
        assert _normalize_sort("top_rated") == "GUEST_RATING"
        assert _normalize_sort("stars") == "STAR_RATING_HIGHEST_FIRST"

    def test_normalize_sort_lowercase(self):
        assert _normalize_sort("price_low_to_high") == "PRICE_LOW_TO_HIGH"
        assert _normalize_sort("recommended") == "RECOMMENDED"

    def test_normalize_sort_empty(self):
        assert _normalize_sort("") == ""

    def test_normalize_destination(self):
        assert _normalize_destination("New York, NY, US") == "new york"
        assert _normalize_destination("Paris") == "paris"
        assert _normalize_destination("") == ""

    def test_parse_star_rating(self):
        assert _parse_star_rating("4,5") == ["4", "5"]
        assert _parse_star_rating("3,4,5") == ["3", "4", "5"]
        assert _parse_star_rating("5") == ["5"]
        assert _parse_star_rating("") == []

    def test_parse_amenities(self):
        assert _parse_amenities("WIFI,POOL") == ["POOL", "WIFI"]
        assert _parse_amenities("pool,wifi") == ["POOL", "WIFI"]
        assert _parse_amenities("") == []


# =============================================================================
# 3. URL PARSING
# =============================================================================

class TestUrlParsing:

    def test_destination_parsed(self):
        url = f"{BASE}?destination=New%20York%2C%20New%20York%2C%20United%20States"
        r = parse_hotels_com_url(url)
        assert r["destination"] == "new york"

    def test_dates_parsed(self):
        url = f"{BASE}?startDate=2026-07-01&endDate=2026-07-05"
        r = parse_hotels_com_url(url)
        assert r["start_date"] == "2026-07-01"
        assert r["end_date"] == "2026-07-05"

    def test_dates_alternative_params(self):
        url = f"{BASE}?d1=2026-7-1&d2=2026-7-5"
        r = parse_hotels_com_url(url)
        assert r["start_date"] == "2026-07-01"
        assert r["end_date"] == "2026-07-05"

    def test_guests_parsed(self):
        url = f"{BASE}?adults=2&rooms=1"
        r = parse_hotels_com_url(url)
        assert r["adults"] == "2"
        assert r["rooms"] == "1"

    def test_multi_room_adults(self):
        url = f"{BASE}?adults=2,1,1&rooms=3"
        r = parse_hotels_com_url(url)
        assert r["adults"] == "4"  # 2+1+1
        assert r["rooms"] == "3"

    def test_children_room_idx_age(self):
        url = f"{BASE}?children=1_5,1_10"
        r = parse_hotels_com_url(url)
        assert r["children"] == "2"
        assert r["children_ages"] == ["10", "5"]

    def test_children_legacy_format(self):
        url = f"{BASE}?childrenAges=5,10"
        r = parse_hotels_com_url(url)
        assert r["children_ages"] == ["10", "5"]

    def test_sort_parsed(self):
        url = f"{BASE}?sort=PRICE_LOW_TO_HIGH"
        r = parse_hotels_com_url(url)
        assert r["sort"] == "PRICE_LOW_TO_HIGH"

    def test_star_rating_parsed(self):
        url = f"{BASE}?f-star-rating=4,5"
        r = parse_hotels_com_url(url)
        assert r["star_rating"] == ["4", "5"]

    def test_price_parsed(self):
        url = f"{BASE}?f-price-min=100&f-price-max=300"
        r = parse_hotels_com_url(url)
        assert r["price_min"] == 100
        assert r["price_max"] == 300

    def test_amenities_parsed(self):
        url = f"{BASE}?f-amenities=WIFI,POOL"
        r = parse_hotels_com_url(url)
        assert r["amenities"] == ["POOL", "WIFI"]

    def test_guest_rating_parsed(self):
        url = f"{BASE}?f-guest-rating=8"
        r = parse_hotels_com_url(url)
        assert r["guest_rating"] == "8"

    def test_payment_type_parsed(self):
        url = f"{BASE}?paymentType=FREE_CANCELLATION"
        r = parse_hotels_com_url(url)
        assert r["payment_type"] == "FREE_CANCELLATION"

    def test_region_id_parsed(self):
        url = f"{BASE}?regionId=2621"
        r = parse_hotels_com_url(url)
        assert r["region_id"] == "2621"


# =============================================================================
# 4. URL MATCHING — EXACT MATCHES
# =============================================================================

class TestExactMatching:

    def test_exact_match_basic(self):
        gt = f"{BASE}?destination=New%20York&startDate=2026-07-01&endDate=2026-07-05&adults=2&rooms=1"
        match, _ = _match(gt, gt)
        assert match is True

    def test_exact_match_with_sort(self):
        gt = f"{BASE}?destination=Paris&startDate=2026-08-10&endDate=2026-08-15&adults=2&rooms=1&sort=PRICE_LOW_TO_HIGH"
        match, _ = _match(gt, gt)
        assert match is True

    def test_exact_match_with_filters(self):
        gt = (
            f"{BASE}?destination=London&startDate=2026-09-01&endDate=2026-09-03"
            "&adults=2&rooms=1&sort=REVIEW&f-star-rating=4,5"
        )
        match, _ = _match(gt, gt)
        assert match is True

    def test_exact_match_full_filters(self):
        gt = (
            f"{BASE}?destination=Tokyo&startDate=2026-10-01&endDate=2026-10-05"
            "&adults=2&rooms=1&sort=PRICE_LOW_TO_HIGH"
            "&f-star-rating=4,5&f-amenities=WIFI,POOL"
            "&paymentType=FREE_CANCELLATION&f-guest-rating=8"
        )
        match, _ = _match(gt, gt)
        assert match is True


# =============================================================================
# 5. URL MATCHING — MISMATCHES
# =============================================================================

class TestMismatches:

    def test_destination_mismatch(self):
        gt = f"{BASE}?destination=Paris"
        agent = f"{BASE}?destination=London"
        match, details = _match(agent, gt)
        assert match is False
        assert any("Destination" in m for m in details["mismatches"])

    def test_destination_missing(self):
        gt = f"{BASE}?destination=Paris"
        agent = f"{BASE}?"
        match, details = _match(agent, gt)
        assert match is False

    def test_checkin_mismatch(self):
        gt = f"{BASE}?startDate=2026-07-01"
        agent = f"{BASE}?startDate=2026-07-02"
        match, _ = _match(agent, gt)
        assert match is False

    def test_checkout_mismatch(self):
        gt = f"{BASE}?endDate=2026-07-05"
        agent = f"{BASE}?endDate=2026-07-06"
        match, _ = _match(agent, gt)
        assert match is False

    def test_adults_mismatch(self):
        gt = f"{BASE}?adults=2"
        agent = f"{BASE}?adults=3"
        match, _ = _match(agent, gt)
        assert match is False

    def test_rooms_mismatch(self):
        gt = f"{BASE}?rooms=1"
        agent = f"{BASE}?rooms=2"
        match, _ = _match(agent, gt)
        assert match is False

    def test_sort_mismatch(self):
        gt = f"{BASE}?sort=PRICE_LOW_TO_HIGH"
        agent = f"{BASE}?sort=REVIEW"
        match, _ = _match(agent, gt)
        assert match is False

    def test_sort_missing(self):
        gt = f"{BASE}?sort=PRICE_LOW_TO_HIGH"
        agent = f"{BASE}?"
        match, _ = _match(agent, gt)
        assert match is False

    def test_star_rating_mismatch(self):
        gt = f"{BASE}?f-star-rating=4,5"
        agent = f"{BASE}?f-star-rating=3,4"
        match, _ = _match(agent, gt)
        assert match is False

    def test_star_rating_missing(self):
        gt = f"{BASE}?f-star-rating=4,5"
        agent = f"{BASE}?"
        match, _ = _match(agent, gt)
        assert match is False

    def test_price_min_mismatch(self):
        gt = f"{BASE}?f-price-min=100"
        agent = f"{BASE}?f-price-min=50"
        match, _ = _match(agent, gt)
        assert match is False

    def test_price_max_mismatch(self):
        gt = f"{BASE}?f-price-max=300"
        agent = f"{BASE}?f-price-max=500"
        match, _ = _match(agent, gt)
        assert match is False

    def test_amenities_mismatch(self):
        gt = f"{BASE}?f-amenities=WIFI,POOL"
        agent = f"{BASE}?f-amenities=WIFI"
        match, _ = _match(agent, gt)
        assert match is False

    def test_guest_rating_mismatch(self):
        gt = f"{BASE}?f-guest-rating=8"
        agent = f"{BASE}?f-guest-rating=7"
        match, _ = _match(agent, gt)
        assert match is False

    def test_payment_type_mismatch(self):
        gt = f"{BASE}?paymentType=FREE_CANCELLATION"
        agent = f"{BASE}?paymentType=PAY_LATER"
        match, _ = _match(agent, gt)
        assert match is False

    def test_children_count_mismatch(self):
        gt = f"{BASE}?children=1_5,1_10"
        agent = f"{BASE}?children=1_5"
        match, _ = _match(agent, gt)
        assert match is False

    def test_children_ages_mismatch(self):
        gt = f"{BASE}?children=1_5,1_10"
        agent = f"{BASE}?children=1_5,1_12"
        match, _ = _match(agent, gt)
        assert match is False


# =============================================================================
# 6. URL MATCHING — TOLERANCE
# =============================================================================

class TestMatchingTolerance:

    def test_extra_params_ignored(self):
        """Extra agent params not in GT should not cause failure."""
        gt = f"{BASE}?destination=Paris&startDate=2026-07-01&endDate=2026-07-05"
        agent = (
            f"{BASE}?destination=Paris&startDate=2026-07-01&endDate=2026-07-05"
            "&utm_source=test&gclid=abc&locale=en_US"
        )
        match, _ = _match(agent, gt)
        assert match is True

    def test_gt_omits_sort_passes(self):
        """If GT doesn't specify sort, agent's sort is ignored."""
        gt = f"{BASE}?destination=Paris"
        agent = f"{BASE}?destination=Paris&sort=PRICE_LOW_TO_HIGH"
        match, _ = _match(agent, gt)
        assert match is True

    def test_gt_omits_filters_passes(self):
        """If GT doesn't specify filters, agent's filters are ignored."""
        gt = f"{BASE}?destination=Paris"
        agent = f"{BASE}?destination=Paris&f-star-rating=5&f-amenities=WIFI"
        match, _ = _match(agent, gt)
        assert match is True

    def test_sort_alias_match(self):
        """Sort aliases should be normalized for comparison."""
        gt = f"{BASE}?sort=PRICE_LOW_TO_HIGH"
        agent = f"{BASE}?sort=cheapest"
        # "cheapest" normalizes to "PRICE_LOW_TO_HIGH"
        match, _ = _match(agent, gt)
        assert match is True

    def test_destination_case_insensitive(self):
        """Destination comparison should be case-insensitive."""
        gt = f"{BASE}?destination=New%20York"
        agent = f"{BASE}?destination=new%20york"
        match, _ = _match(agent, gt)
        assert match is True

    def test_destination_city_part_only(self):
        """Destination should match on city part only."""
        gt = f"{BASE}?destination=New%20York"
        agent = f"{BASE}?destination=New%20York%2C%20NY%2C%20United%20States"
        match, _ = _match(agent, gt)
        assert match is True

    def test_star_rating_order_independent(self):
        """Star rating comparison should be order-independent."""
        gt = f"{BASE}?f-star-rating=5,4"
        agent = f"{BASE}?f-star-rating=4,5"
        match, _ = _match(agent, gt)
        assert match is True


# =============================================================================
# 7. ASYNC LIFECYCLE
# =============================================================================

class TestAsyncLifecycle:

    @pytest.mark.asyncio
    async def test_update_compute_match(self):
        gt = f"{BASE}?destination=Paris&startDate=2026-07-01&endDate=2026-07-05&adults=2&rooms=1"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(url=gt)
        result = await v.compute()

        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_update_compute_no_match(self):
        gt = f"{BASE}?destination=Paris"
        agent = f"{BASE}?destination=London"

        v = HotelsComUrlMatch(gt_url=gt)
        await v.update(url=agent)
        result = await v.compute()

        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_reset(self):
        gt = f"{BASE}?destination=Paris"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(url=gt)
        await v.reset()

        result = await v.compute()
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_first_match_sticks(self):
        gt1 = f"{BASE}?destination=Paris"
        gt2 = f"{BASE}?destination=London"

        v = HotelsComUrlMatch(gt_url=[gt1, gt2])

        await v.update(url=gt1)
        await v.update(url=gt2)  # should be ignored

        result = await v.compute_detailed()
        assert result.match is True
        assert result.gt_url == gt1

    @pytest.mark.asyncio
    async def test_non_hotels_com_url_ignored(self):
        gt = f"{BASE}?destination=Paris"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(url="https://www.google.com")
        result = await v.compute()

        assert result.score == 0.0
        assert v._agent_url == ""

    @pytest.mark.asyncio
    async def test_property_page_ignored(self):
        """Property detail pages should be ignored."""
        gt = f"{BASE}?destination=Paris"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(url="https://www.hotels.com/ho123456/")
        result = await v.compute()

        assert result.score == 0.0
        assert v._agent_url == ""

    @pytest.mark.asyncio
    async def test_empty_url_ignored(self):
        gt = f"{BASE}?destination=Paris"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(url="")
        result = await v.compute()

        assert result.score == 0.0


# =============================================================================
# 8. MULTI-GT URL SUPPORT
# =============================================================================

class TestMultipleGTUrls:

    @pytest.mark.asyncio
    async def test_second_gt_matches(self):
        gt1 = f"{BASE}?destination=Paris"
        gt2 = f"{BASE}?destination=London"

        v = HotelsComUrlMatch(gt_url=[gt1, gt2])

        await v.update(url=gt2)
        result = await v.compute_detailed()

        assert result.match is True
        assert result.gt_url == gt2

    @pytest.mark.asyncio
    async def test_no_gt_matches(self):
        gt1 = f"{BASE}?destination=Paris"
        gt2 = f"{BASE}?destination=London"

        v = HotelsComUrlMatch(gt_url=[gt1, gt2])

        await v.update(url=f"{BASE}?destination=Tokyo")
        result = await v.compute_detailed()

        assert result.match is False


# =============================================================================
# 9. COMPUTE DETAILED
# =============================================================================

class TestComputeDetailed:

    @pytest.mark.asyncio
    async def test_detailed_fields_on_match(self):
        gt = f"{BASE}?destination=Paris"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(url=gt)
        result = await v.compute_detailed()

        assert isinstance(result, HotelsComVerifierResult)
        assert result.score == 1.0
        assert result.match is True
        assert result.agent_url == gt
        assert result.gt_url == gt
        assert isinstance(result.details, dict)

    @pytest.mark.asyncio
    async def test_detailed_fields_on_mismatch(self):
        gt = f"{BASE}?destination=Paris"
        agent = f"{BASE}?destination=London"

        v = HotelsComUrlMatch(gt_url=gt)
        await v.update(url=agent)
        result = await v.compute_detailed()

        assert result.score == 0.0
        assert result.match is False
        assert result.agent_url == agent


# =============================================================================
# 10. TASK CONFIG GENERATION
# =============================================================================

class TestTaskConfig:

    def test_generate_task_config_basic(self):
        config = generate_task_config(
            task="Find hotels in New York",
            location="San Francisco, CA",
            timezone="America/Los_Angeles",
            gt_url=[f"{BASE}?destination=New%20York"],
        )

        assert config.task == "Find hotels in New York"
        assert config.url == "https://www.hotels.com/"
        assert f"{BASE}?destination=New%20York" in config.eval_config["gt_url"]

    def test_generate_task_config_ground_truth_url(self):
        config = generate_task_config(
            task="Find hotels",
            location="London",
            timezone="Europe/London",
            ground_truth_url=f"{BASE}?destination=London",
        )

        assert f"{BASE}?destination=London" in config.eval_config["gt_url"]

    def test_generate_task_config_placeholder_substitution(self):
        gt_template = f"{BASE}?startDate={{checkinDate}}&endDate={{checkoutDate}}"

        config = generate_task_config(
            task="Hotels",
            location="Paris",
            timezone="Europe/Paris",
            gt_url=[gt_template],
            values={
                "checkinDate": "{now() + timedelta(1)}",
                "checkoutDate": "{now() + timedelta(3)}",
            },
        )

        url = config.eval_config["gt_url"][0]
        assert "startDate=" in url
        assert "endDate=" in url
        # Should not contain placeholder tokens
        assert "{checkinDate}" not in url
        assert "{checkoutDate}" not in url

    def test_generate_task_config_raises_value_error(self):
        with pytest.raises(ValueError):
            generate_task_config(
                task="Find hotels",
                location="Paris",
                timezone="Europe/Paris",
            )

    def test_generate_task_config_custom_url(self):
        config = generate_task_config(
            task="Find hotels",
            location="Tokyo",
            timezone="Asia/Tokyo",
            gt_url=[f"{BASE}?destination=Tokyo"],
            url="https://in.hotels.com/",
        )

        assert config.url == "https://in.hotels.com/"


# =============================================================================
# 11. REPR
# =============================================================================

class TestRepr:

    def test_repr_single_url(self):
        v = _v(f"{BASE}?destination=Paris")
        assert "HotelsComUrlMatch" in repr(v)
        assert "Paris" in repr(v)

    def test_repr_multiple_urls(self):
        v = HotelsComUrlMatch(gt_url=[f"{BASE}?destination=Paris", f"{BASE}?destination=London"])
        r = repr(v)
        assert "Paris" in r
        assert "London" in r


# =============================================================================
# 12. REGIONAL DOMAIN MATCHING
# =============================================================================

class TestRegionalDomains:

    @pytest.mark.asyncio
    async def test_india_domain_accepted(self):
        gt = f"{BASE}?destination=Mumbai"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(
            url="https://in.hotels.com/Hotel-Search?destination=Mumbai"
        )
        result = await v.compute()
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_uk_domain_accepted(self):
        gt = f"{BASE}?destination=London"
        v = HotelsComUrlMatch(gt_url=gt)

        await v.update(
            url="https://uk.hotels.com/Hotel-Search?destination=London"
        )
        result = await v.compute()
        assert result.score == 1.0
