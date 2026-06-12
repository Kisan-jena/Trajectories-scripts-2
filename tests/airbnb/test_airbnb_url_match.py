"""
Covers:
- Page type detection
- Location matching
- Filters
- Experience details
- Multi GT
- Async lifecycle
- Edge cases
- URL decoding
- Parser robustness
"""

import asyncio
import pytest

from navi_bench.airbnb.airbnb_url_match import (
    AirbnbUrlMatch,
    AirbnbVerifierResult,
    generate_task_config
)

BASE = "https://www.airbnb.com"


# ============================================================
# Helpers
# ============================================================

def _v(gt):
    return AirbnbUrlMatch(gt_url=gt)


def _match(agent, gt):
    return _v(gt)._urls_match(agent, gt)


# ============================================================
# 1. PAGE TYPES
# ============================================================

class TestPageTypes:

    def test_homepage(self):
        gt = f"{BASE}/"
        assert _match(gt, gt)[0]

    def test_homes_search(self):
        gt = f"{BASE}/s/Paris--France/homes"
        assert _match(gt, gt)[0]

    def test_experiences_search(self):
        gt = f"{BASE}/s/Paris--France/experiences"
        assert _match(gt, gt)[0]

    def test_services_search(self):
        gt = f"{BASE}/s/Paris--France/services"
        assert _match(gt, gt)[0]

    def test_services_page(self):
        gt = f"{BASE}/services"

        parsed = _v(gt)._parse_url(gt)

        assert parsed["page_type"] == "services_page"

    def test_experience_detail(self):
        gt = f"{BASE}/experiences/123456"

        parsed = _v(gt)._parse_url(gt)

        assert parsed["page_type"] == "experience_detail"


# ============================================================
# 2. LOCATION MATCHING
# ============================================================

class TestLocation:

    def test_location_match(self):
        gt = f"{BASE}/s/Paris--France/homes"

        assert _match(gt, gt)[0]

    def test_location_case_insensitive(self):
        gt = f"{BASE}/s/Paris--France/homes"

        agent = f"{BASE}/s/paris--france/homes"

        assert _match(agent, gt)[0]

    def test_location_mismatch(self):
        gt = f"{BASE}/s/Paris--France/homes"

        agent = f"{BASE}/s/London--England/homes"

        assert not _match(agent, gt)[0]

    def test_double_encoded_location(self):
        gt = f"{BASE}/s/New York--NY--United States/homes"

        agent = (
            f"{BASE}/s/"
            "New%2520York--NY--United%2520States/homes"
        )

        assert _match(agent, gt)[0]


# ============================================================
# 3. MULTI VALUE FILTERS
# ============================================================

class TestMultiValueFilters:

    def test_amenities_exact(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=4"
        )

        assert _match(gt, gt)[0]

    def test_amenities_order_independent(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=4"
            "&amenities[]=8"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=8"
            "&amenities[]=4"
        )

        assert _match(agent, gt)[0]

    def test_amenities_mismatch(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=4"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=8"
        )

        assert not _match(agent, gt)[0]

    def test_room_types(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?room_types[]=Entire%20home"
        )

        assert _match(gt, gt)[0]


# ============================================================
# 4. BOOLEAN FILTERS
# ============================================================

class TestBooleanFilters:

    def test_ib_true(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?ib=true"
        )

        assert _match(gt, gt)[0]

    def test_guest_favorite_true(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?guest_favorite=true"
        )

        assert _match(gt, gt)[0]

    def test_boolean_mismatch(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?ib=true"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?ib=false"
        )

        assert not _match(agent, gt)[0]


# ============================================================
# 5. NUMERIC FILTERS
# ============================================================

class TestNumericFilters:

    def test_adults(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
        )

        assert _match(gt, gt)[0]

    def test_adults_mismatch(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=3"
        )

        assert not _match(agent, gt)[0]

    def test_price_range(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?price_min=100"
            "&price_max=300"
        )

        assert _match(gt, gt)[0]

    def test_price_range_mismatch(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?price_min=100"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?price_min=200"
        )

        assert not _match(agent, gt)[0]

    def test_bedrooms(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?min_bedrooms=2"
        )

        assert _match(gt, gt)[0]


# ============================================================
# 6. STRING FILTERS
# ============================================================

class TestStringFilters:

    def test_checkin_checkout(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?checkin=2026-07-01"
            "&checkout=2026-07-07"
        )

        assert _match(gt, gt)[0]

    def test_checkin_mismatch(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?checkin=2026-07-01"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?checkin=2026-07-02"
        )

        assert not _match(agent, gt)[0]

    def test_place_id(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?place_id=abc123"
        )

        assert _match(gt, gt)[0]


# ============================================================
# 7. EXPERIENCE DETAILS
# ============================================================

class TestExperienceDetails:

    def test_experience_id_match(self):
        gt = f"{BASE}/experiences/123456"

        assert _match(gt, gt)[0]

    def test_experience_id_mismatch(self):
        gt = f"{BASE}/experiences/123456"

        agent = f"{BASE}/experiences/999999"

        assert not _match(agent, gt)[0]


# ============================================================
# 8. IGNORED PARAMS
# ============================================================

class TestIgnoredParams:

    def test_source_ignored(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
            "&source=structured_search_input_header"
        )

        assert _match(agent, gt)[0]

    def test_modal_ignored(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
            "&modal=PHOTO_TOUR_SCROLLABLE"
        )

        assert _match(agent, gt)[0]


# ============================================================
# 9. MULTI GT
# ============================================================

class TestMultiGT:

    def test_or_logic(self):

        gt = [
            f"{BASE}/s/Paris--France/homes?adults=2",
            f"{BASE}/s/London--England/homes?adults=2",
        ]

        v = AirbnbUrlMatch(gt)

        asyncio.run(
            v.update(
                url=f"{BASE}/s/London--England/homes?adults=2"
            )
        )

        result = asyncio.run(v.compute())

        assert result.score == 1.0

    def test_first_match_sticks(self):

        gt1 = (
            f"{BASE}/s/Paris--France/homes?adults=2"
        )

        gt2 = (
            f"{BASE}/s/London--England/homes?adults=2"
        )

        v = AirbnbUrlMatch([gt1, gt2])

        asyncio.run(v.update(url=gt1))
        asyncio.run(v.update(url=gt2))

        result = asyncio.run(
            v.compute_detailed()
        )

        assert result.gt_url == gt1


# ============================================================
# 10. ASYNC LIFECYCLE
# ============================================================

class TestAsync:

    @pytest.mark.asyncio
    async def test_reset(self):

        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
        )

        v = AirbnbUrlMatch(gt)

        await v.update(url=gt)

        await v.reset()

        assert (
            await v.compute()
        ).score == 0.0

    @pytest.mark.asyncio
    async def test_no_match(self):

        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
        )

        v = AirbnbUrlMatch(gt)

        await v.update(
            url=f"{BASE}/s/London--England/homes"
        )

        assert (
            await v.compute()
        ).score == 0.0


# ============================================================
# 11. EDGE CASES
# ============================================================

class TestEdgeCases:

    def test_empty_url(self):

        v = _v(
            f"{BASE}/s/Paris--France/homes"
        )

        asyncio.run(v.update(url=""))

        assert not v._found_match

    def test_invalid_domain(self):

        v = _v(
            f"{BASE}/s/Paris--France/homes"
        )

        asyncio.run(
            v.update(
                url="https://google.com"
            )
        )

        assert not v._found_match

    def test_malformed_url(self):

        v = _v(
            f"{BASE}/s/Paris--France/homes"
        )

        asyncio.run(
            v.update(
                url="not-a-url"
            )
        )

        assert not v._found_match


# ============================================================
# 12. COMPUTE OUTPUT
# ============================================================

class TestCompute:

    @pytest.mark.asyncio
    async def test_compute_detailed(self):

        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
        )

        v = AirbnbUrlMatch(gt)

        await v.update(url=gt)

        result = (
            await v.compute_detailed()
        )

        assert isinstance(
            result,
            AirbnbVerifierResult,
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
# 13. REAL WORLD SCENARIOS
# ============================================================

class TestRealScenarios:

    def test_paris_wifi_homes(self):

        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
            "&amenities[]=4"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
            "&amenities[]=4"
        )

        match, details = _match(
            agent,
            gt,
        )

        assert match, details

    def test_complex_home_search(self):

        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
            "&children=1"
            "&amenities[]=4"
            "&price_min=100"
            "&price_max=300"
            "&guest_favorite=true"
            "&min_bedrooms=2"
        )

        agent = gt

        match, details = _match(
            agent,
            gt,
        )

        assert match, details

    def test_filter_failure(self):

        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
            "&amenities[]=4"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?adults=2"
            "&amenities[]=8"
        )

        assert not _match(
            agent,
            gt,
        )[0]
    
    def test_san_juan_wifi_two_adults(self):

        gt = (
            "https://www.airbnb.com/s/San-Juan/homes"
            "?adults=2"
            "&amenities%5B%5D=4"
        )

        agent = (
            "https://www.airbnb.com/s/San-Juan/homes"
            "?refinement_paths%5B%5D=%2Fhomes"
            "&place_id=ChIJbxlo4m9oA4wR3FqTXA9_a60"
            "&date_picker_type=calendar"
            "&checkin=2026-07-02"
            "&checkout=2026-07-03"
            "&adults=2"
            "&search_type=filter_change"
            "&query=San%20Juan"
            "&flexible_trip_lengths%5B%5D=one_week"
            "&monthly_start_date=2026-07-01"
            "&monthly_length=3"
            "&monthly_end_date=2026-10-01"
            "&search_mode=regular_search"
            "&price_filter_input_type=2"
            "&price_filter_num_nights=1"
            "&channel=EXPLORE"
            "&amenities%5B%5D=4"
        )

        match, details = _match(agent, gt)

        assert match, details

    def test_los_angeles_experience_price_cap(self):

        gt = (
            "https://www.airbnb.com/s/Los-Angeles--California/experiences"
            "?checkin=2026-07-10"
            "&checkout=2026-07-12"
            "&experience_price_max=150"
        )

        agent = (
            "https://www.airbnb.com/s/Los-Angeles--California/experiences"
            "?search_type=unknown"
            "&refinement_paths%5B%5D=%2Fexperiences"
            "&place_id=ChIJE9on3F3HwoAR9AhGJW_fL-I"
            "&date_picker_type=calendar"
            "&checkin=2026-07-10"
            "&checkout=2026-07-12"
            "&source=structured_search_input_header"
            "&query=Los%20Angeles%2C%20California%2C%20United%20States"
            "&experience_price_max=150"
            "&selected_filter_order%5B%5D=experience_price_max%3A150"
            "&update_selected_filters=false"
        )

        match, details = _match(agent, gt)

        assert match, details
    
    def test_seattle_photography_service(self):
        """
        Requirement:
        - Seattle
        - Photography service
        """

        gt = (
            "https://www.airbnb.com/s/Seattle--WA/services?"
            "service_type_tag=Tag%3A8949"
        )

        agent = (
            "https://www.airbnb.com/s/Seattle--WA/services?"
            "acp_id=db43c0a4-bdbb-4a5b-8241-00272c221004"
            "&location_bb=Qj7w7cL0cI1CPe25wvTrZw%3D%3D"
            "&place_id=ChIJVTPokywQkFQRmtVEaUZlJRA"
            "&refinement_paths%5B%5D=%2Fservices"
            "&date_picker_type=calendar"
            "&service_type_tag=Tag%3A8949"
            "&pinned_service_type_tag=Tag%3A8949"
            "&search_type=autocomplete_click"
        )

        match, details = _match(agent, gt)

        assert match, details
    

class TestDateResolution:

    def test_la_experience_date_resolution(self):

        task_config = generate_task_config(
            task=(
                "Search experiences in Los Angeles checking in on a Friday "
                "during the next month and checking out on the following Sunday."
            ),
            location="United States",
            timezone="America/Los_Angeles",
            gt_url=[
                "https://www.airbnb.com/s/Los-Angeles--California/experiences?"
                "checkin={checkIn}"
                "&checkout={checkOut}"
                "&experience_price_max=150"
            ],
            values={
                "checkIn": "Fridays in next month",
                "checkOut": "Sundays in next month",
            },
        )

        resolved_urls = task_config.eval_config["gt_url"]

        assert len(resolved_urls) > 0

        for url in resolved_urls:
            assert "{checkIn}" not in url
            assert "{checkOut}" not in url
            assert "experience_price_max=150" in url

    def test_la_experience_placeholder_resolution(self):

        task_config = generate_task_config(
            task="dummy",
            location="United States",
            timezone="America/Los_Angeles",
            gt_url=[
                "https://www.airbnb.com/s/Los-Angeles--California/experiences?"
                "checkin={checkIn}"
                "&checkout={checkOut}"
                "&experience_price_max=150"
            ],
            values={
                "checkIn": "Sundays in next month",
                "checkOut": "Fridays in next month",
            },
        )

        resolved_urls = task_config.eval_config["gt_url"]

        expected = (
            "https://www.airbnb.com/s/Los-Angeles--California/experiences?"
            "checkin=2026-07-12"
            "&checkout=2026-07-17"
            "&experience_price_max=150"
        )

        assert expected in resolved_urls

        
class TestRealflexibleScenarios:

    def test_houston_flexible_weekend_hotel_pool_ac_wifi(self):
        """
        Requirement:
        - Destination: Houston, Texas
        - Flexible weekend dates
        - 2 adults
        - 1 child
        - Instant Book
        - Property type: Hotel
        - Amenities:
            - Pool (7)
            - Wifi (4)
            - AC (5)
        """

        gt = (
            "https://www.airbnb.com/s/Houston--Texas/homes?"
            "flexible_trip_lengths%5B%5D=weekend_trip"
            "&adults=2"
            "&children=1"
            "&monthly_start_date=2026-07-01"
            "&monthly_length=3"
            "&monthly_end_date=2026-10-01"
            "&l2_property_type_ids%5B%5D=4"
            "&amenities%5B%5D=7"
            "&amenities%5B%5D=4"
            "&amenities%5B%5D=5"
            "&ib=true"
        )

        agent = (
            "https://www.airbnb.com/s/Houston--Texas/homes?"
            "refinement_paths%5B%5D=%2Fhomes"
            "&place_id=ChIJAYWNSLS4QIYROwVl894CDco"
            "&date_picker_type=flexible_dates"
            "&flexible_trip_lengths%5B%5D=weekend_trip"
            "&adults=2"
            "&children=1"
            "&search_type=filter_change"
            "&query=Houston%2C%20Texas"
            "&monthly_start_date=2026-07-01"
            "&monthly_length=3"
            "&monthly_end_date=2026-10-01"
            "&search_mode=regular_search"
            "&price_filter_input_type=2"
            "&price_filter_num_nights=2"
            "&channel=EXPLORE"
            "&ib=true"
            "&selected_filter_order%5B%5D=ib%3Atrue"
            "&selected_filter_order%5B%5D=l2_property_type_ids%3A4"
            "&selected_filter_order%5B%5D=amenities%3A7"
            "&selected_filter_order%5B%5D=amenities%3A4"
            "&selected_filter_order%5B%5D=amenities%3A5"
            "&update_selected_filters=false"
            "&l2_property_type_ids%5B%5D=4"
            "&amenities%5B%5D=7"
            "&amenities%5B%5D=4"
            "&amenities%5B%5D=5"
        )

        match, details = _match(agent, gt)

        assert match, f"Failed with {details}"
    
    def test_houston_wrong_flexible_trip_length(self):
        """
        Requirement:
        Flexible weekend dates

        Agent incorrectly selected:
        one_week
        """

        gt = (
            "https://www.airbnb.com/s/Houston--Texas/homes?"
            "flexible_trip_lengths%5B%5D=weekend_trip"
            "&adults=2"
            "&children=1"
            "&monthly_start_date=2026-07-01"
            "&monthly_length=3"
            "&monthly_end_date=2026-10-01"
            "&l2_property_type_ids%5B%5D=4"
            "&amenities%5B%5D=7"
            "&amenities%5B%5D=4"
            "&amenities%5B%5D=5"
            "&ib=true"
        )

        agent = (
            "https://www.airbnb.com/s/Houston--Texas/homes?"
            "date_picker_type=flexible_dates"
            "&flexible_trip_lengths%5B%5D=one_week"
            "&adults=2"
            "&children=1"
            "&monthly_start_date=2026-07-01"
            "&monthly_length=3"
            "&monthly_end_date=2026-10-01"
            "&l2_property_type_ids%5B%5D=4"
            "&amenities%5B%5D=7"
            "&amenities%5B%5D=4"
            "&amenities%5B%5D=5"
            "&ib=true"
        )

        match, details = _match(agent, gt)

        assert not match

        assert any(
            "flexible_trip_lengths" in mismatch
            for mismatch in details["mismatches"]
        )
    
    def test_price_only_search_should_fail_when_extra_amenities_selected(self):
        """
        Requirement:
        - Washington D.C.
        - Max price = 1700

        Agent incorrectly applied:
        - Wifi (4)
        - Free parking (9)
        """

        gt = (
            "https://www.airbnb.com/s/Washington-D.C./homes?"
            "price_max=1700"
        )

        agent = (
            "https://www.airbnb.com/s/Washington-D.C./homes?"
            "refinement_paths%5B%5D=%2Fhomes"
            "&place_id=ChIJW-T2Wt7Gt4kRmKFUAsCO4tY"
            "&date_picker_type=calendar"
            "&search_type=filter_change"
            "&query=Washington%20D.C."
            "&flexible_trip_lengths%5B%5D=one_week"
            "&monthly_start_date=2026-07-01"
            "&monthly_length=3"
            "&monthly_end_date=2026-10-01"
            "&search_mode=regular_search"
            "&price_filter_input_type=2"
            "&channel=EXPLORE"
            "&price_max=1700"
            "&price_filter_num_nights=5"
            "&selected_filter_order%5B%5D=price_max%3A1700"
            "&amenities%5B%5D=4"
            "&amenities%5B%5D=9"
        )

        match, details = _match(agent, gt)

        # This is the desired behavior.
        assert not match

class TestDomainScenarios:

    def test_invalid_domain(self):
        v = _v(
            "https://www.airbnb.com/s/Paris--France/homes"
        )

        asyncio.run(
            v.update(
                url="https://google.com"
            )
        )

        assert not v._found_match
    
    def test_fake_airbnb_domain(self):
        v = _v(
            "https://www.airbnb.com/s/Paris--France/homes"
        )

        asyncio.run(
            v.update(
                url="https://airbnb.com.evil.com/s/Paris--France/homes"
            )
        )

        assert not v._found_match
    
    def test_typo_squatting_domain(self):
        v = _v(
            "https://www.airbnb.com/s/Paris--France/homes"
        )

        asyncio.run(
            v.update(
                url="https://airbnb.co/s/Paris--France/homes"
            )
        )

        assert not v._found_match
    
    def test_myairbnb_domain_rejected(self):
        v = _v(
            "https://www.airbnb.com/s/Paris--France/homes"
        )

        asyncio.run(
            v.update(
                url="https://myairbnb.com/s/Paris--France/homes"
            )
        )

        assert not v._found_match

class TestPrefixHandling:

    def test_locale_prefix_homes(self):
        gt = "https://www.airbnb.com/s/Paris--France/homes"
        agent = "https://www.airbnb.com/en/s/Paris--France/homes"

        assert _match(agent, gt)[0]

    def test_locale_prefix_experience(self):
        gt = "https://www.airbnb.com/experiences/123456"
        agent = "https://www.airbnb.com/fr/experiences/123456"

        assert _match(agent, gt)[0]

class TestBooleanParsing:

    def test_ib_numeric_true(self):
        gt = f"{BASE}/s/Paris--France/homes?ib=1"
        assert _match(gt, gt)[0]

    def test_boolean_true_vs_one(self):
        gt = f"{BASE}/s/Paris--France/homes?ib=true"
        agent = f"{BASE}/s/Paris--France/homes?ib=1"

        assert _match(agent, gt)[0]

class TestMUltiValueFilters:

    def test_comma_separated_amenities(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=4&amenities[]=8"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=4,8"
        )

        assert _match(agent, gt)[0]
    
    def test_pipe_separated_amenities(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=4&amenities[]=8"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?amenities[]=4|8"
        )

        assert _match(agent, gt)[0]
    
    def test_double_encoded_room_type(self):
        gt = (
            f"{BASE}/s/Paris--France/homes"
            "?room_types[]=Entire Home"
        )

        agent = (
            f"{BASE}/s/Paris--France/homes"
            "?room_types[]=Entire%2520Home"
        )

        assert _match(agent, gt)[0]
    
    def test_pune_vs_pune_maharashtra(self):
        gt = (
            "https://www.airbnb.com/s/Pune--Maharashtra/homes"
        )

        agent = (
            "https://www.airbnb.com/s/pune/homes"
        )

        assert _match(agent, gt)[0]


    def test_pune_maharashtra_vs_pune(self):
        gt = (
            "https://www.airbnb.com/s/pune/homes"
        )

        agent = (
            "https://www.airbnb.com/s/Pune--Maharashtra/homes"
        )

        assert _match(agent, gt)[0]
    

    def test_different_cities_do_not_match(self):
        gt = (
            "https://www.airbnb.com/s/Pune--Maharashtra/homes"
        )

        agent = (
            "https://www.airbnb.com/s/Mumbai--Maharashtra/homes"
        )

        assert not _match(agent, gt)[0]
    
    def test_different_cities_do_not_match(self):
        gt = (
            "https://www.airbnb.com/s/Pune--Maharashtra/homes"
        )

        agent = (
            "https://www.airbnb.com/s/Mumbai--Maharashtra/homes"
        )

        match, details = _match(agent, gt)

        assert not match

        assert any(
            "location" in mismatch.lower()
            for mismatch in details["mismatches"]
        )
    
    def test_pune_vs_bengaluru(self):
        gt = "https://www.airbnb.com/s/Pune/homes"
        agent = "https://www.airbnb.com/s/Bengaluru--Karnataka/homes"

        assert not _match(agent, gt)[0]