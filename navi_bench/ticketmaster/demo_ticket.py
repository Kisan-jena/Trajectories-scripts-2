#!/usr/bin/env python
"""
Ticketmaster Ticket Availability Verification Demo

Human-in-the-loop verification system for Ticketmaster events.
Supports multi-tab browsing, real-time navigation tracking, and comprehensive
evaluation of agent navigation behavior, including anti-bot detection.

Features:
- Real-time page state tracking via navigation events
- Multi-tab/popup window support
- Stealth browser configuration (anti-detection)
- Ticketmaster-specific JS scraper (handles React classes & LD+JSON)
- Flexible query-based verification (e.g., exclude_resale)
- Debug output showing scraped events and bot-protection states

Author: NaviBench Team
"""

import asyncio
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger

# Import our new Ticketmaster evaluator
from navi_bench.ticketmaster.ticket_info_gathering import (
    TicketmasterInfoGathering,
    generate_task_config_deterministic,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class BrowserConfig:
    """Browser launch configuration for stealth operation."""
    headless: bool = False
    viewport_width: int = 1366
    viewport_height: int = 768
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    locale: str = "en-US"
    
    # Anti-detection arguments (Crucial for Ticketmaster)
    launch_args: list = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--start-maximized",
        "--no-sandbox",
        "--disable-web-security",
    ])


@dataclass
class TaskScenario:
    """Defines a verification task scenario."""
    task_id: str
    name: str
    description: str
    url: str
    task_prompt: str
    queries: list
    location: str
    timezone: str
    category: str
    values: dict | None = None
    tags: list = field(default_factory=list)

    def __post_init__(self):
        """Validate scenario configuration."""
        assert self.task_id, "task_id is required"
        assert self.queries, "queries cannot be empty"


# =============================================================================
# TASK SCENARIOS - Ticketmaster Specific
# =============================================================================

SCENARIOS: list[TaskScenario] = [
    # =========================================================================
    # NEW: Dynamic-date scenarios using {dateRange} placeholders
    # =========================================================================

    TaskScenario(
        task_id="ticketmaster/concerts/charlie_puth/hollywood_fl_row_A_fridays_next_month",
        name="Charlie Puth Row A Tickets - Hollywood FL",
        description="Find available Row A tickets for the 'Charlie Puth: Whatever's Clever! World Tour' in Hollywood, Florida on Fridays next month.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the 'Charlie Puth: Whatever's Clever! World Tour' "
            "in Hollywood, FL on {dateRange}. Look for tickets specifically "
            "located in Row A."
        ),
        queries=[[{
            "event_names": ["charlie puth: whatever's clever! world tour"],
            "cities": ["hollywood"],
            "rows": ["A"],
            "require_available": True,
        }]],
        values={"dateRange": "Fridays in next month"},
        location="United States",
        timezone="America/Chicago",
        category="concerts",
        tags=["concerts", "charlie puth", "hollywood", "florida", "row_filter", "date_filter", "availability"],
    ),

    TaskScenario(
        task_id="ticketmaster/theater/lion_king/cincinnati_aronoff_center/101",
        name="The Lion King at Aronoff Center - Cincinnati Fridays",
        description="Find available tickets for The Lion King touring event at Aronoff Center-Procter & Gamble Hall in Cincinnati, OH for Fridays in next month.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'The Lion King' touring event by Disney. Find the "
            "event happening in Cincinnati, OH at the Aronoff Center-Procter "
            "& Gamble Hall and look for available tickets on {dateRange}"
        ),
        queries=[[{
            "event_names": ["the lion king (touring)"],
            "cities": ["cincinnati"],
            "venues": ["aronoff center-procter & gamble hall"],
            "require_available": True,
        }]],
        values={"dateRange": "Fridays in next month"},
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "the_lion_king", "cincinnati", "aronoff_center", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/music/backstreet_boys/sphere_las_vegas/101",
        name="Backstreet Boys at Sphere - Las Vegas Fridays",
        description="Find available Backstreet Boys: Into The Millennium concert tickets at the Sphere in Las Vegas for Fridays in next month.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Backstreet Boys: Into The Millennium' concert "
            "at the Sphere in Las Vegas. Find tickets for {dateRange}. "
            "Look for the available options."
        ),
        queries=[[{
            "event_names": ["backstreet boys: into the millennium"],
            "cities": ["las vegas"],
            "venues": ["sphere"],
            "require_available": True,
        }]],
        values={"dateRange": "Fridays in next month"},
        location="United States",
        timezone="America/Los_Angeles",
        category="music",
        tags=["music", "backstreet_boys", "sphere", "las_vegas", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/music/ariana_grande/los_angeles_budget_900/101",
        name="Ariana Grande - Los Angeles Under $900",
        description="Find Ariana Grande tickets in Los Angeles, CA for Fridays in next month with a maximum price of $900.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Ariana Grande in Los Angeles, CA on {dateRange}. "
            "Find tickets priced for maximum $900."
        ),
        queries=[[{
            "event_names": ["ariana grande"],
            "cities": ["los angeles"],
            "max_price": 900.0,
            "require_available": True,
        }]],
        values={"dateRange": "Fridays in next month"},
        location="United States",
        timezone="America/Los_Angeles",
        category="music",
        tags=["music", "ariana_grande", "los_angeles", "budget_under_900", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/theater/wicked_ny/two_tickets_budget_range/101",
        name="Wicked (NY) - 2 Tickets Between $200 and $400",
        description="Find exactly 2 Wicked (NY) tickets for Saturdays in next month priced between $200 and $400.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Wicked (NY) on {dateRange} for exactly 2 "
            "tickets priced between minimum $200 and maximum $400."
        ),
        queries=[[{
            "event_names": ["wicked (ny)"],
            "ticket_quantities": [2],
            "min_price": 200.0,
            "max_price": 400.0,
            "require_available": True,
        }]],
        values={"dateRange": "Saturdays in next month"},
        location="United States",
        timezone="America/Los_Angeles",
        category="theater",
        tags=["theater", "wicked_ny", "two_tickets", "price_range", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/music/charlie_puth/three_tickets_price_range/101",
        name="Charlie Puth - 3 Tickets Between $80 and $180",
        description="Find exactly 3 tickets for Charlie Puth: Whatever's Clever! World Tour on Fridays in next month priced between $80 and $180.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'Charlie Puth: Whatever's Clever! World Tour' on "
            "{dateRange}. Select exactly 3 tickets priced between minimum "
            "$80 and maximum $180."
        ),
        queries=[[{
            "event_names": ["charlie puth: whatever's clever! world tour"],
            "ticket_quantities": [3],
            "min_price": 80.0,
            "max_price": 180.0,
            "require_available": True,
        }]],
        values={"dateRange": "Fridays in next month"},
        location="United States",
        timezone="America/New_York",
        category="music",
        tags=["music", "charlie_puth", "three_tickets", "price_range", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/concerts/charlie_puth/row_A_fridays_next_month",
        name="Charlie Puth Row A Tickets - Fridays Next Month",
        description="Find available Row A tickets for the 'Charlie Puth: Whatever's Clever! World Tour' on Fridays next month.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the 'Charlie Puth: Whatever's Clever! World Tour' "
            "on {dateRange}. Look for tickets specifically located in Row A."
        ),
        queries=[[{
            "event_names": ["charlie puth: whatever's clever! world tour"],
            "rows": ["A"],
            "require_available": True,
        }]],
        values={"dateRange": "Fridays in next month"},
        location="United States",
        timezone="America/Chicago",
        category="concerts",
        tags=["concerts", "charlie puth", "row_filter", "date_filter", "availability"],
    ),

    TaskScenario(
        task_id="ticketmaster/sports/monster_jam/austin",
        name="Monster Jam - Austin Saturdays",
        description="Find Monster Jam tickets in Austin for Saturdays in next month.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Monster Jam event in Austin exactly on {dateRange}."
        ),
        queries=[[{
            "event_names": ["monster jam"],
            "cities": ["austin"],
            "require_available": True,
        }]],
        values={"dateRange": "Saturdays in next month"},
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "monster_jam", "austin", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/sports/monster_jam_freestyle_mania/grand_rapids_saturdays",
        name="Monster Jam Freestyle Mania - Grand Rapids",
        description="Find Monster Jam Freestyle Mania tickets in Grand Rapids for Saturdays in next month.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'Monster Jam Freestyle Mania' in Grand Rapids scheduled for {dateRange}."
        ),
        queries=[[{
            "event_names": ["monster jam freestyle mania"],
            "cities": ["grand rapids"],
            "require_available": True,
        }]],
        values={"dateRange": "Saturdays in next month"},
        location="United States",
        timezone="America/Detroit",
        category="sports",
        tags=["sports", "monster_jam", "freestyle_mania", "grand_rapids", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/concerts/backstreet_boys_sphere/fridays_next_month",
        name="Backstreet Boys Sphere - Fridays Next Month",
        description="Find Backstreet Boys: Into The Millennium concert tickets at Sphere in Las Vegas for Fridays in next month.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Backstreet Boys: Into The Millennium' concert at the Sphere in Las Vegas. "
            "Find tickets for {dateRange}. Look for the available options."
        ),
        queries=[[{
            "event_names": ["backstreet boys: into the millennium"],
            "cities": ["las vegas"],
            "venues": ["sphere"],
            "require_available": True,
        }]],
        values={"dateRange": "Fridays in next month"},
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["concerts", "backstreet_boys", "sphere", "las_vegas", "dynamic_dates"],
    ),

    TaskScenario(
        task_id="ticketmaster/theater/hamilton/dynamic_saturdays_budget",
        name="Hamilton (NY) - Saturdays Next Month Under $350",
        description="Find Hamilton theater tickets for Saturdays in next month under $350.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Hamilton (NY) theater tickets priced under $350 for {dateRange}."
        ),
        queries=[[{
            "event_names": ["hamilton"],
            "event_categories": ["theater", "arts"],
            "max_price": 350.0,
            "require_available": True,
        }]],
        values={"dateRange": "Saturdays in next month"},
        location="United States",
        timezone="America/New_York",
        category="theater",
        tags=["theater", "hamilton", "dynamic_dates", "budget"],
    ),

    # =========================================================================
    # EXISTING: Static-date scenarios
    # =========================================================================

    # PRIMARY TASK: General Concert Check
    TaskScenario(
        task_id="ticketmaster/concerts/coldplay/001",
        name="Coldplay Concert - Any Availability",
        description="Search for Coldplay concert tickets",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Coldplay concert tickets. Find any upcoming Coldplay event and check ticket availability."
        ),
        queries=[[{
            "event_names": ["coldplay"],  
            "require_available": False,   # Sold out still counts as finding the right page
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["coldplay", "concert", "music"],
    ),
    # TASK: Ticketmaster Specific - Primary Tickets Only (No Resale)
    TaskScenario(
        task_id="ticketmaster/sports/lakers/no_resale",
        name="LA Lakers - Primary Tickets Only",
        description="Search for Lakers tickets, excluding Verified Resale",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for a Los Angeles Lakers home game and find standard tickets only (filter out Verified Resale)."
        ),
        queries=[[{
            "event_names": ["lakers"], 
            "exclude_resale": True,       # Ticketmaster specific constraint!
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["nba", "basketball", "primary_only"],
    ),
    # TASK: Budget constraint
    TaskScenario(
        task_id="ticketmaster/theater/hamilton/budget",
        name="Hamilton - Budget Tickets",
        description="Find affordable theater tickets",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Hamilton theater tickets priced under $350."
        ),
        queries=[[{
            "event_names": ["hamilton"],
            "event_categories": ["theater", "arts"],
            "max_price": 350.0,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="theater",
        tags=["theater", "broadway", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jokoy_chappelle_soundcheck",
        name="Jo Koy & Dave Chappelle - Soundcheck Series",
        description="Search for the niche Soundcheck Series comedy show in Yellow Springs.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Soundcheck Series' comedy event featuring Jo Koy and hosted by Dave Chappelle scheduled for either July 24 or July 25, 2026."
        ),
        queries=[[{
            "event_names": ["jo koy", "dave chappelle", "soundcheck series"], 
            "cities": ["yellow springs"],
            "dates": ["2026-07-24", "2026-07-25"],
            "require_available": False, 
        }]],
        location="United States",
        timezone="America/New_York",
        category="comedy",
        tags=["comedy", "standup", "specific_dates", "niche_location"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jo_koy_chappelle/yellow_springs",
        name="Jo Koy & Dave Chappelle - Yellow Springs",
        description="Find the specific Soundcheck Series comedy show in Ohio.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Soundcheck Series' comedy event featuring Jo Koy and Dave Chappelle in Yellow Springs, OH. Navigate to the event page and check ticket availability."
        ),
        queries=[[{
            "event_names": ["jo koy", "dave chappelle"], 
            "cities": ["yellow springs"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="comedy",
        tags=["comedy", "jo koy", "dave chappelle", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/festivals/bottlerock/saturday",
        name="BottleRock Napa Valley - Saturday Ticket",
        description="Find tickets for the middle day of a 3-day festival.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the BottleRock Napa Valley festival. Find the event specifically for the Saturday, May 23, 2026 date."
        ),
        queries=[[{
            "event_names": ["bottlerock napa valley"], 
            "dates": ["2026-05-23"],
            "cities": ["napa"],
            "require_available": False,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="festivals",
        tags=["festival", "music", "bottlerock", "date_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/backstreet_boys/standard_show",
        name="Backstreet Boys Sphere - Standard Concert",
        description="Navigate to the standard concert listing, avoiding the Suite Reservation page.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Backstreet Boys 'Into The Millennium' concert at the Sphere in Las Vegas. Find tickets for the Friday, July 17, 2026 show. Make sure you are looking at the actual concert tickets, not the Suite Reservations."
        ),
        queries=[[{
            "event_names": ["backstreet boys: into the millennium"],
            "dates": ["2026-07-17"],
            "cities": ["las vegas"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["concerts", "pop", "backstreet boys", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/backstreet_boys/suite_reservation",
        name="Backstreet Boys Sphere - Suite Reservation",
        description="Find the premium Suite Reservation listing for opening night.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Backstreet Boys at the Sphere in Las Vegas. Navigate specifically to the 'Suite Reservation' event page for their opening night on July 16, 2026."
        ),
        queries=[[{
            "event_names": ["suite reservation", "backstreet boys at sphere - suite reservation"],
            "dates": ["2026-07-16"],
            "cities": ["las vegas"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["concerts", "pop", "backstreet boys", "vip_suite"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/wwe/raw_seattle",
        name="WWE Monday Night Raw - Seattle",
        description="Navigate to a specific Monday Night Raw show on the tour schedule.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for WWE Monday Night Raw in Seattle. Verify ticket availability for the show on March 9, 2026."
        ),
        queries=[[{
            "event_names": ["monday night raw", "wwe"],
            "dates": ["2026-03-09"],
            "cities": ["seattle"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["sports", "wrestling", "wwe", "date_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/wwe/smackdown_pittsburgh_standard",
        name="WWE SmackDown - Primary Tickets Pittsburgh",
        description="Find standard tickets for a Friday Night SmackDown show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the WWE Friday Night Smackdown event in Pittsburgh on March 27, 2026. Look for only the standard admission tickets."
        ),
        queries=[[{
            "event_names": ["smackdown", "friday night smackdown"],
            "dates": ["2026-03-27"],
            "cities": ["pittsburgh"],
            "exclude_resale": True,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "wrestling", "wwe", "primary_only"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/discovery_dates",
        name="Monster Jam - Discovery Date Range",
        description="Test the date range filter on the discovery page.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Monster Jam on Ticketmaster and use the date filter to show events from March 15 to March 27, 2026."
        ),
        queries=[[{
            "event_names": ["monster jam"], 
            "dates": ["2026-03-15"], # The is_date_satisfied fallback will pass this
            "require_available": False,
        }]],
        location="United States",
        timezone="America/New_York",
        category="family",
        tags=["family", "motorsports", "monster jam", "date_filter", "discovery"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/grand_rapids_freestyle",
        name="Monster Jam Freestyle Mania - Grand Rapids",
        description="Find the 'Freestyle Mania' specific variant in Grand Rapids.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'Monster Jam Freestyle Mania' in Grand Rapids."
        ),
        queries=[[{
            "event_names": ["monster jam freestyle mania"],
            "cities": ["grand rapids"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Detroit",
        category="family",
        tags=["family", "motorsports", "monster jam", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/hartford_exact",
        name="Monster Jam - Hartford March 21",
        description="Navigate to the exact Saturday show in Hartford.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Monster Jam event in Hartford exactly on March 21, 2026."
        ),
        queries=[[{
            "event_names": ["monster jam"],
            "cities": ["hartford"],
            "dates": ["2026-03-21"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="family",
        tags=["family", "motorsports", "monster jam", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/tucson_budget",
        name="Monster Jam - Tucson Budget Tickets",
        description="Find affordable tickets using price filters in Tucson.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for Monster Jam tickets in Tucson on March 20, 2026. Adjust the maximum price filter to $60 or find individual tickets listed under $60."
        ),
        queries=[[{
            "event_names": ["monster jam"],
            "cities": ["tucson"],
            "dates": ["2026-03-20"],
            "max_price": 60.0,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Phoenix",
        category="family",
        tags=["family", "motorsports", "monster jam", "budget", "price_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/family/monster_jam/biloxi_standard",
        name="Monster Jam - Biloxi Standard Only",
        description="Ensure verified resale is unchecked for the Biloxi show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Monster Jam in Biloxi on March 15, 2026. Ensure you filter out verified resale tickets and verify standard ticket availability."
        ),
        queries=[[{
            "event_names": ["monster jam"],
            "cities": ["biloxi"],
            "dates": ["2026-03-15"],
            "exclude_resale": True,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="family",
        tags=["family", "motorsports", "monster jam", "primary_only"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/royals_budget",
        name="Dodgers @ Royals - Under $40",
        description="Find budget tickets for the Dodgers away game in Kansas City.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Los Angeles Dodgers away game against the Kansas City Royals on March 17, 2026. Find tickets priced less than $40."
        ),
        queries=[[{
            "event_names": ["dodgers", "royals"], 
            "dates": ["2026-03-17"],
            "max_price": 40.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "baseball", "dodgers", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/spring_training_surprise",
        name="Dodgers Spring Training - Surprise AZ",
        description="Find the specific Spring Training game in Surprise, Arizona.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Los Angeles Dodgers tickets for their Spring Training game against the Chicago White Sox happening at Surprise Stadium in Arizona on March 15, 2026."
        ),
        queries=[[{
            "event_names": ["dodgers", "white sox"],
            "dates": ["2026-03-15"],
            "cities": ["surprise"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "spring_training", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/vs_athletics",
        name="Dodgers vs. The A's - May 13",
        description="Navigate to a specific home game against The A's.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Los Angeles Dodgers home game against The A's on May 13, 2026."
        ),
        queries=[[{
            "event_names": ["dodgers", "a's", "athletics"],
            "dates": ["2026-05-13"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "dodgers", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/vs_diamondbacks_flexible",
        name="Dodgers vs. Diamondbacks - Flexible Date",
        description="Find a game against the Diamondbacks on either May 19 or May 21.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for an upcoming Los Angeles Dodgers game against the Arizona Diamondbacks. Check availability for either the May 19 or May 21, 2026 game."
        ),
        queries=[[{
            "event_names": ["dodgers", "diamondbacks"],
            "dates": ["2026-05-19", "2026-05-21"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["mlb", "dodgers", "flexible_dates"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/royals_4_tickets",
        name="Dodgers @ Royals - Exactly 4 Tickets",
        description="Ensure the agent selects exactly 4 tickets from the filter dropdown.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find exactly 4 tickets for the Los Angeles Dodgers at Kansas City Royals game on March 17, 2026."
        ),
        queries=[[{
            "event_names": ["dodgers", "royals"],
            "dates": ["2026-03-17"],
            "ticket_quantities": [4],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["mlb", "quantity_filter", "group_tickets"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/dodgers/white_sox_primary",
        name="Dodgers vs White Sox - Standard Tickets",
        description="Find standard admission tickets, excluding verified resale.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the March 15, 2026 game between the Dodgers and White Sox. Filter the results to exclude 'Verified Resale' and only show Standard tickets."
        ),
        queries=[[{
            "event_names": ["dodgers", "white sox"],
            "dates": ["2026-03-15"],
            "exclude_resale": True,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Phoenix",
        category="sports",
        tags=["mlb", "primary_only", "spring_training"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/mlb/kansas_city_discovery",
        name="MLB Discovery - Kansas City March 17",
        description="Verify location and date filters on the sports discovery page.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for any Dodgers/Royals game in Kansas City happening on 17th March 2026."
        ),
        queries=[[{
            "event_categories": ["sports"],
            "cities": ["kansas city"],
            "dates": ["2026-03-17"],
            "require_available": False, # Agent passes just by setting the UI filters correctly
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["sports", "discovery", "location_filter", "date_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/strict_budget_pair",
        name="Bruno Mars - Pair between $600 and $1000",
        description="Find exactly 2 tickets within a specific high-end price range.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Bruno Mars 'The Romantic Tour' concert on April 18, 2026 for exactly 2 tickets priced between $600 and $1000."
        ),
        queries=[[{
            "event_names": ["bruno mars", "the romantic tour"], 
            "dates": ["2026-04-18"],
            "ticket_quantities": [2],
            "min_price": 600.00,
            "max_price": 1000.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["pop", "bruno mars", "price_range", "quantity_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/premium_resale",
        name="Bruno Mars - Premium Resale Tickets",
        description="Find high-end verified resale tickets over $700.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Bruno Mars tickets for his April 18, 2026 show. Ensure the 'Verified Resale' filter is active, and find tickets priced over $700."
        ),
        queries=[[{
            "event_names": ["bruno mars"],
            "dates": ["2026-04-18"],
            "require_resale": True,
            "min_price": 700.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "bruno mars", "resale_only", "premium_price"],
    ),
    # 3. Tests row-specific matching
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/front_rows",
        name="Bruno Mars - Rows 9 or 10",
        description="Find tickets specifically in Row 9 or Row 10.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Bruno Mars concert on April 18, 2026. Find available tickets specifically located in Row 9 or Row 10."
        ),
        queries=[[{
            "event_names": ["bruno mars"],
            "dates": ["2026-04-18"],
            "rows": ["9", "10"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="concerts",
        tags=["pop", "bruno mars", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/mj/matinee",
        name="MJ The Musical - 1:00 PM Matinee",
        description="Navigate to a specific matinee performance of a Broadway show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'MJ' the musical at the Neil Simon Theatre in New York on March 18, 2026 and check availability."
        ),
        queries=[[{
            "event_names": ["mj"],
            "cities": ["new york"],
            "dates": ["2026-03-18"],
            "times": ["13:00"], # Evaluator parses 1:00 PM as 13:00
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="theater",
        tags=["theater", "broadway", "mj", "time_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/bruno_mars/cheap_ticket",
        name="Bruno Mars - Under $650",
        description="Find a budget ticket for a high-demand concert.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Bruno Mars 'The Romantic Tour' for April 18, 2026. Find any available ticket that costs less than $650."
        ),
        queries=[[{
            "event_names": ["bruno mars"],
            "dates": ["2026-04-18"],
            "max_price": 650.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["pop", "bruno mars", "budget", "max_price"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/lincoln_budget",
        name="Jonas Brothers Lincoln - Under $250",
        description="Find budget tickets for the Jonas Brothers concert in Lincoln, CA.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Jonas Brothers concert at The Venue at Thunder Valley Casino Resort in Lincoln, CA on May 29, 2026. Find tickets that cost less than $250."
        ),
        queries=[[{
            "event_names": ["jonas brothers"], 
            "dates": ["2026-05-29"],
            "cities": ["lincoln"],
            "max_price": 250.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["pop", "jonas brothers", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/festivals/boots_and_hearts/friday_pass",
        name="Boots And Hearts Festival - Friday Pass",
        description="Find a single-day festival pass featuring the Jonas Brothers.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Boots And Hearts Music Festival in Oro-Medonte, ON, Canada on Friday, August 7, 2026 and check ticket availability."
        ),
        queries=[[{
            "event_names": ["boots and hearts"],
            "dates": ["2026-08-07"],
            "cities": ["oro-medonte"],
            "require_available": True,
        }]],
        location="Canada",
        timezone="America/Toronto",
        category="festivals",
        tags=["festival", "country", "jonas brothers", "single_day"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/hometown_jacksonville",
        name="Jonas Brothers - Greetings From Your Hometown",
        description="Find the specifically named 'Hometown' variant event in Jacksonville.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Jonas Brothers 'Greetings From Your Hometown' concert happening at Daily's Place Amphitheater in Jacksonville on December 30, 2025."
        ),
        queries=[[{
            "event_names": ["jonas 20", "greetings from your hometown"],
            "dates": ["2025-12-30"],
            "cities": ["jacksonville"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "jonas brothers", "exact_match", "special_event"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/aspen_private",
        name="Jonas Brothers - Aspen Private Venue",
        description="Locate a concert happening at an undisclosed or private venue.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Jonas Brothers concert scheduled for October 4, 2025, in Aspen, CO."
        ),
        queries=[[{
            "event_names": ["jonas brothers"],
            "dates": ["2025-10-04"],
            "cities": ["aspen"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Denver",
        category="concerts",
        tags=["pop", "jonas brothers", "location_filter", "private_venue"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/jonas_brothers/ziegfeld_new_york",
        name="Jonas Brothers - Ziegfeld Ballroom NY",
        description="Find standard admission tickets for the New York ballroom show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Jonas Brothers performance at the Ziegfeld Ballroom in New York on November 15, 2025, specifically standard tickets."
        ),
        queries=[[{
            "event_names": ["jonas brothers"],
            "dates": ["2025-11-15"],
            "cities": ["new york"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "jonas brothers", "new_york", "standard_tickets"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/charlie_puth/qty3_price_range",
        name="Charlie Puth - 3 Tickets ($80-$180)",
        description="Find exactly 3 tickets within a specific price range.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Charlie Puth's 'Whatever's Clever! World Tour' on April 24, 2026. Select exactly 3 tickets priced between $80 and $180."
        ),
        queries=[[{
            "event_names": ["charlie puth", "whatever's clever"], 
            "dates": ["2026-04-24"],
            "ticket_quantities": [3],
            "min_price": 80.00,
            "max_price": 180.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "charlie puth", "quantity_filter", "price_range"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/charlie_puth/under_60",
        name="Charlie Puth - Budget Ticket Under $60",
        description="Find a budget ticket below $60.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Charlie Puth concert on April 24, 2026. Find any available standard ticket that costs less than $60."
        ),
        queries=[[{
            "event_names": ["charlie puth"],
            "dates": ["2026-04-24"],
            "max_price": 60.00, # Will correctly match the $53.45 ticket from logs
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "charlie puth", "budget", "max_price"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/charlie_puth/row_2",
        name="Charlie Puth - Row 2 Specific",
        description="Verify tickets located exactly in Row 2.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Charlie Puth 'Whatever's Clever! World Tour' on April 24, 2026. Look for tickets specifically located in Row 2."
        ),
        queries=[[{
            "event_names": ["charlie puth"],
            "dates": ["2026-04-24"],
            "rows": ["2"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="concerts",
        tags=["pop", "charlie puth", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/charlie_puth/rio_de_janeiro",
        name="Charlie Puth - Rio de Janeiro",
        description="Navigate to an international venue listing.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Charlie Puth concert taking place at Parque Olímpico in Rio de Janeiro. "
        ),
        queries=[[{
            "event_names": ["charlie puth", "parque olímpico"],
            "cities": ["rio de janeiro"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="concerts",
        tags=["pop", "charlie puth", "international", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/concerts/charlie_puth/whatevers_clever_tour",
        name="Charlie Puth - Whatever's Clever Tour",
        description="Match the exact tour naming convention.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search specifically for the 'Whatever's Clever! World Tour' happening on April 24, 2026 event and ensure tickets are available."
        ),
        queries=[[{
            "event_names": ["whatever's clever"],
            "dates": ["2026-04-24"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="concerts",
        tags=["pop", "charlie puth", "exact_match", "tour_name"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jeff_dunham/tight_budget_pair",
        name="Jeff Dunham - Pair exactly $77 to $78",
        description="Find exactly 2 tickets in a very tight price window.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Jeff Dunham 'Artificial Intelligence' comedy tour on April 11, 2026 for exactly 2 tickets priced between $77 and $78."
        ),
        queries=[[{
            "event_names": ["jeff dunham", "artificial intelligence"], 
            "dates": ["2026-04-11"],
            "ticket_quantities": [2],
            "min_price": 77.00,
            "max_price": 78.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="comedy",
        tags=["comedy", "jeff dunham", "price_range", "quantity_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jeff_dunham/row_a_front",
        name="Jeff Dunham - Front Row A",
        description="Find tickets located specifically in Row A.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Jeff Dunham concert on April 11, 2026. Look for tickets specifically located in Row A."
        ),
        queries=[[{
            "event_names": ["jeff dunham"],
            "dates": ["2026-04-11"],
            "rows": ["a"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="comedy",
        tags=["comedy", "jeff dunham", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jeff_dunham/detroit_matinee",
        name="Jeff Dunham - Detroit Matinee",
        description="Navigate to a specific matinee show at Fox Theatre.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Jeff Dunham in Detroit, MI. Find tickets for his 3:00 PM matinee show at the Fox Theatre Detroit on April 25, 2026."
        ),
        queries=[[{
            "event_names": ["jeff dunham"],
            "cities": ["detroit"],
            "venues": ["fox theatre"],
            "dates": ["2026-04-25"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Detroit",
        category="comedy",
        tags=["comedy", "jeff dunham", "location_filter", "time_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jeff_dunham/vegas_show",
        name="Jeff Dunham - Las Vegas",
        description="Find tickets for a specific Las Vegas residency/tour stop.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for Jeff Dunham's 'Artificial Intelligence' tour stop in Las Vegas, NV at PH Live at Planet Hollywood on April 26, 2026."
        ),
        queries=[[{
            "event_names": ["jeff dunham", "artificial intelligence"],
            "cities": ["las vegas"],
            "dates": ["2026-04-26"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="comedy",
        tags=["comedy", "jeff dunham", "las_vegas", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jeff_dunham/budget_under_80",
        name="Jeff Dunham - Under $80",
        description="Find a budget ticket below $80 for a comedy show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for Jeff Dunham tickets for his April 11, 2026 performance and verify if there are standard tickets available that cost less than $80."
        ),
        queries=[[{
            "event_names": ["jeff dunham"],
            "dates": ["2026-04-11"],
            "max_price": 80.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="comedy",
        tags=["comedy", "jeff dunham", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/detroit_discovery",
        name="Comedy Discovery - Detroit",
        description="Verify location filters on the Comedy discovery page.",
        url="https://www.ticketmaster.com/discover/comedy",
        task_prompt=(
            "Go to the Ticketmaster Comedy section and search for events happening in 'Detroit' on April 25, 2026. Do not need to click into any actual event."
        ),
        queries=[[{
            "event_categories": ["comedy"],
            "cities": ["detroit"],
            "dates": ["2026-04-25"],
            "require_available": False,
        }]],
        location="United States",
        timezone="America/Detroit",
        category="comedy",
        tags=["comedy", "discovery", "location_filter", "date_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/comedy/jeff_dunham/row_c",
        name="Jeff Dunham - Row C Specific",
        description="Extract and verify tickets in Row C.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for tickets to the Jeff Dunham 'Artificial Intelligence' tour on April 11, 2026. Check if there are any tickets available in Row C."
        ),
        queries=[[{
            "event_names": ["jeff dunham"],
            "dates": ["2026-04-11"],
            "rows": ["c"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="comedy",
        tags=["comedy", "jeff dunham", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/david_copperfield/late_show",
        name="David Copperfield - 9:30 PM Late Show",
        description="Navigate to a specific late-night performance of a show.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for David Copperfield tickets on March 2, 2026. Find availability specifically for the 9:30 PM late show."
        ),
        queries=[[{
            "event_names": ["david copperfield"],
            "dates": ["2026-03-02"],
            "times": ["21:30"], # Evaluator parses 9:30 PM as 21:30
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="theater",
        tags=["magic", "theater", "david copperfield", "time_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/david_copperfield/discovery_dates",
        name="David Copperfield - Discovery Date Range",
        description="Verify date filters on the discovery page for a residency.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for David Copperfield events from March 26 to April 30, 2026. Do not need to click into a specific event."
        ),
        queries=[[{
            "event_names": ["david copperfield"],
            "dates": ["2026-03-26"], # The is_date_satisfied fallback will pass this
            "require_available": False,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="theater",
        tags=["magic", "theater", "david copperfield", "date_filter", "discovery"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/david_copperfield/4_tickets",
        name="David Copperfield - Exactly 4 Tickets",
        description="Find exactly 4 tickets for a specific date.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find exactly 4 tickets for the David Copperfield magic show on March 3, 2026."
        ),
        queries=[[{
            "event_names": ["david copperfield"],
            "dates": ["2026-03-03"],
            "ticket_quantities": [4],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="theater",
        tags=["magic", "theater", "david copperfield", "quantity_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/boise_location",
        name="The Lion King - Boise Start",
        description="Find the touring production of The Lion King in Boise, ID.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'The Lion King' Broadway touring production. Find the event happening in Boise, ID at the Morrison Center."
        ),
        queries=[[{
            "event_names": ["lion king"], 
            "cities": ["boise"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "lion king", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/march_7_matinee",
        name="The Lion King - 1:00 PM Matinee",
        description="Navigate to the early matinee performance.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for 'The Lion King' in Boise on March 7, 2026 to the 1:00 PM matinee show and check availability."
        ),
        queries=[[{
            "event_names": ["lion king", "matinee show"],
            "dates": ["2026-03-07"],
            "times": ["13:00"], # 1:00 PM parsed
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "lion king", "time_constraint", "matinee"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/march_7_evening",
        name="The Lion King - 7:00 PM Evening",
        description="Navigate to the evening performance on the same day.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for 'The Lion King' in Boise on March 7, 2026. Navigate specifically to the 7:00 PM evening show and check availability."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-07"],
            "times": ["19:00"], # 7:00 PM parsed
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "lion king", "time_constraint", "evening"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/qty2_price_range",
        name="The Lion King - Pair between $100-$280",
        description="Set a specific price range for exactly 2 tickets.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'The Lion King' touring show on March 27, 2026 and look for exactly 2 tickets priced in the range of $100 and $280."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-27"],
            "ticket_quantities": [2],
            "min_price": 100.00,
            "max_price": 280.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "quantity_filter", "price_range"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/budget_under_150",
        name="The Lion King - Under $150",
        description="Find a budget-friendly ticket below $150.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for 'The Lion King' tickets on March 27, 2026. Find any available ticket that costs less than $150."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-27"],
            "max_price": 150.00, # Will hit the $115/$117 tickets
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/premium_over_350",
        name="The Lion King - Premium Over $350",
        description="Find premium/VIP priced tickets.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for premium tickets to 'The Lion King' on March 27, 2026. Find tickets that are priced over $350."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-27"],
            "min_price": 350.00, # Will hit the $355/$406 tickets
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "premium_price"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/row_g",
        name="The Lion King - Row G",
        description="Verify tickets located exactly in Row G.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for 'The Lion King' on March 27, 2026. Look for tickets specifically located in Row G."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-27"],
            "rows": ["g"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/row_l_pair",
        name="The Lion King - Pair in Row L",
        description="Verify a pair of tickets located in Row L.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find exactly 2 tickets for 'The Lion King' on March 27, 2026. Ensure the tickets are located in Row L."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-27"],
            "ticket_quantities": [2],
            "rows": ["l"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "row_constraint", "quantity_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/row_z",
        name="The Lion King - Row Z",
        description="Verify tickets located exactly in Row Z.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for tickets to 'The Lion King' on March 27, 2026. Look for tickets specifically located further back in Row Z."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-27"],
            "rows": ["z"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/theater/lion_king/primary_budget",
        name="The Lion King - Standard Under $120",
        description="Ensure verified resale is unchecked and find budget tickets.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for 'The Lion King' on March 27, 2026. Verify only the standard tickets availability priced under $120."
        ),
        queries=[[{
            "event_names": ["lion king"],
            "dates": ["2026-03-27"],
            "exclude_resale": True,
            "max_price": 120.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Boise",
        category="theater",
        tags=["theater", "broadway", "primary_only", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/banshees_season_ticket",
        name="Boston Banshees - 2026 Season Ticket",
        description="Find the season ticket package for the Boston Banshees.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 2026 Banshees Season Ticket in Quincy, MA. Navigate to the listing and check ticket availability."
        ),
        queries=[[{
            "event_names": ["banshees season ticket"], 
            "cities": ["quincy"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "rugby", "season_tickets"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/exiles_vs_breakers",
        name="NY Exiles vs Bay Breakers - Mt. Vernon",
        description="Find a specific matchup in a specific city.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the New York Exiles vs Bay Breakers match happening in Mt. Vernon on May 9, 2026."
        ),
        queries=[[{
            "event_names": ["exiles", "bay breakers"],
            "dates": ["2026-05-09"],
            "cities": ["mt. vernon"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "rugby", "exact_match", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/tempest_vs_banshees_primary",
        name="Chicago Tempest vs Banshees - Standard Only",
        description="Filter out verified resale for a specific game.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find only the standard tickets for the Chicago Tempest vs Boston Banshees game in Lisle on May 10, 2026. "
        ),
        queries=[[{
            "event_names": ["tempest", "banshees"],
            "dates": ["2026-05-10"],
            "cities": ["lisle"],
            "exclude_resale": True,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["sports", "rugby", "primary_only"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/onyx_vs_exiles",
        name="Denver Onyx vs NY Exiles",
        description="Locate a specific game in Denver.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for the Denver Onyx vs NY Exiles match taking place in Denver on June 21, 2026. Check availability of tickets."
        ),
        queries=[[{
            "event_names": ["onyx", "exiles"],
            "dates": ["2026-06-21"],
            "cities": ["denver"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Denver",
        category="sports",
        tags=["sports", "rugby", "matchup"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/gemini_flexible_dates",
        name="Twin Cities Gemini - Flexible Dates",
        description="Find any Twin Cities Gemini home game in June.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find a Twin Cities Gemini home game in Eagan. Check ticket availability for either the June 7 or June 21, 2026 game."
        ),
        queries=[[{
            "event_names": ["twin cities gemini", "tc gemini"],
            "cities": ["eagan"],
            "dates": ["2026-06-07", "2026-06-21"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["sports", "rugby", "flexible_dates"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/hounds_budget",
        name="Chicago Hounds vs Free Jacks - Under $50",
        description="Find an affordable ticket for a match in Nashville.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Chicago Hounds vs New England Free Jacks match in Nashville on April 19, 2026. Find tickets that cost less than $50."
        ),
        queries=[[{
            "event_names": ["chicago hounds", "free jacks"],
            "dates": ["2026-04-19"],
            "cities": ["nashville"],
            "max_price": 50.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["sports", "rugby", "budget"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/breakers_sacramento",
        name="Bay Breakers vs Tempest - Sacramento",
        description="Ensure the agent selects the game in Sacramento, not Lodi.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find the Bay Breakers vs Chicago Tempest match on May 31, 2026. Make sure it's the game happening specifically in Sacramento."
        ),
        queries=[[{
            "event_names": ["bay breakers", "tempest"],
            "dates": ["2026-05-31"],
            "cities": ["sacramento"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Los_Angeles",
        category="sports",
        tags=["sports", "rugby", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/banshees_breakers_4_tickets",
        name="Banshees vs Breakers - Exactly 4 Tickets",
        description="Ensure the agent selects exactly 4 tickets from the dropdown.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Boston Banshees vs Bay Breakers game on June 7, 2026 in Quincy, search for exactly 4 tickets."
        ),
        queries=[[{
            "event_names": ["boston banshees", "bay breakers"],
            "dates": ["2026-06-07"],
            "cities": ["quincy"],
            "ticket_quantities": [4],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "rugby", "quantity_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/rugby/onyx_season_ticket",
        name="Denver Onyx - 2026 Season Ticket",
        description="Locate the specific Onyx Season Ticket package.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Locate the 2026 Onyx Season Ticket package for Denver and check availability."
        ),
        queries=[[{
            "event_names": ["onyx season ticket"],
            "cities": ["denver"],
            "dates": ["2026-05-10"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Denver",
        category="sports",
        tags=["sports", "rugby", "season_tickets"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/brick_city_group_budget",
        name="Brick City Fight Night - 8 Tickets ($100-$270)",
        description="Find a large group of tickets within a specific mid-tier price range.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Brick City Fight Night Series happening on April 10, 2026 for exactly 8 tickets priced between $100 and $270."
        ),
        queries=[[{
            "event_names": ["brick city fight night series"], 
            "dates": ["2026-04-10"],
            "ticket_quantities": [8],
            "min_price": 100.00,
            "max_price": 270.00,
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "boxing", "quantity_filter", "price_range"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/brick_city_row_6",
        name="Brick City Fight Night - Row 6",
        description="Extract and verify tickets specifically located in Row 6.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Look for tickets to the Brick City Fight Night Series on April 10, 2026. Check if there are any tickets available exactly in Row 6."
        ),
        queries=[[{
            "event_names": ["brick city fight night series"],
            "dates": ["2026-04-10"],
            "rows": ["6"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "boxing", "row_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/matchroom_orlando",
        name="Matchroom Boxing - Orlando 6:00 PM",
        description="Navigate to a specific fight card at Caribe Royale.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the Matchroom Boxing event featuring Adames vs Williams. Navigate specifically to the event happening in Orlando on March 21, 2026 at 6:00 PM."
        ),
        queries=[[{
            "event_names": ["matchroom boxing", "adames v williams"],
            "dates": ["2026-03-21"],
            "cities": ["orlando"],
            "times": ["18:00"], # Evaluator parses 6:00 PM as 18:00
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "boxing", "location_filter", "time_constraint"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/thursday_night_anchorage",
        name="Thursday Night At The Fights - March 26",
        description="Navigate to the correct date for a recurring local event.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for 'Thursday Night At The Fights' in Anchorage, AK. Fiind the event happening on March 26, 2026, not earlier in the month."
        ),
        queries=[[{
            "event_names": ["thursday night at the fights"],
            "dates": ["2026-03-26"],
            "cities": ["anchorage"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Anchorage",
        category="sports",
        tags=["sports", "boxing", "date_constraint", "recurring_event"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/boxing_insider_atlantic_city",
        name="Boxing Insider - Standard Tickets (No Hotel)",
        description="Find the standard fight listing, avoiding the Ticket + Hotel Deals page.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Boxing Insider: Live Professional Boxing' event in Atlantic City on March 7, 2026. Look at the standard event tickets, not the Ticket + Hotel Deals package."
        ),
        queries=[[{
            "event_names": ["boxing insider: live professional boxing"], 
            "dates": ["2026-03-07"],
            "cities": ["atlantic city"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "boxing", "exact_match", "standard_tickets"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/down_for_the_count_san_antonio",
        name="Down For The Count - San Antonio",
        description="Navigate to a highly specific local event with complex naming.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the 'Down For The Count' boxing event happening at Sam's Burger Joint in San Antonio, TX on March 20, 2026."
        ),
        queries=[[{
            "event_names": ["down for the count"],
            "dates": ["2026-03-20"],
            "cities": ["san antonio"],
            "venues": ["sam's burger joint"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/Chicago",
        category="sports",
        tags=["sports", "boxing", "location_filter", "exact_match"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/foxwoods_bare_knuckle",
        name="Foxwoods Fight Night - Bare Knuckle",
        description="Find the Bare Knuckle Boxing event at a specific casino.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Find tickets for the Foxwoods Fight Night - Bare Knuckle Boxing 52 event in Mashantucket, CT on March 28, 2026."
        ),
        queries=[[{
            "event_names": ["foxwoods fight night", "bare knuckle boxing 52"],
            "dates": ["2026-03-28"],
            "cities": ["mashantucket"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "boxing", "location_filter"],
    ),
    TaskScenario(
        task_id="ticketmaster/sports/boxing/fdny_battle_of_badges",
        name="FDNY Bravest Boxing - New York",
        description="Find a specific charity boxing event.",
        url="https://www.ticketmaster.com/",
        task_prompt=(
            "Search for the FDNY Bravest Boxing International Battle Of The Badges event happening in New York on March 6, 2026."
        ),
        queries=[[{
            "event_names": ["fdny bravest boxing", "battle of the badges"],
            "dates": ["2026-03-06"],
            "cities": ["new york"],
            "require_available": True,
        }]],
        location="United States",
        timezone="America/New_York",
        category="sports",
        tags=["sports", "boxing", "charity_event", "location_filter"],
    )


]


# =============================================================================
# BROWSER MANAGER - Stealth browser configuration
# =============================================================================

class BrowserManager:
    """Manages browser lifecycle with stealth configuration."""
    
    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.browser = None
        self.context = None
        self.page = None
    
    async def launch(self, playwright) -> tuple:
        """Launch browser with stealth configuration."""
        self.browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=self.config.launch_args,
        )
        
        self.context = await self.browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height
            },
            user_agent=self.config.user_agent,
            locale=self.config.locale,
        )
        
        # Anti-detection scripts - highly important for PerimeterX/DataDome
        await self.context.add_init_script("""
            // Hide webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Override chrome.runtime
            window.chrome = { runtime: {} };
            
            // Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // WebGL fingerprint spoofing
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.call(this, parameter);
            };
        """)
        
        self.page = await self.context.new_page()
        
        return self.browser, self.context, self.page
    
    async def close(self) -> None:
        """Close browser and cleanup."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()


# =============================================================================
# RESULT REPORTER - Format and display results
# =============================================================================

class ResultReporter:
    """Formats and displays verification results."""
    
    @staticmethod
    def print_header(scenario: TaskScenario, rendered_task: str) -> None:
        """Print task header."""
        print("\n" + "=" * 80)
        print(f"TICKETMASTER VERIFICATION: {scenario.name}")
        print("=" * 80)
        print(f"Task ID:     {scenario.task_id}")
        print(f"Category:    {scenario.category}")
        print(f"Location:    {scenario.location}")
        print("-" * 80)
        print(f"TASK: {rendered_task}")
        print("-" * 80)
        print(f"Looking for: {scenario.queries[0][0]}")
        print("=" * 80)
    
    @staticmethod
    def print_instructions() -> None:
        """Print user instructions."""
        print("\n" + "-" * 40)
        print("INSTRUCTIONS:")
        print("-" * 40)
        print("1. Use the Ticketmaster website to complete the task")
        print("2. Search for events and navigate to listings")
        print("3. Watch out for 'Pardon the Interruption' anti-bot screens")
        print("4. Press ENTER in this terminal when ready to see verification results")
        print("-" * 40 + "\n")
    
    @staticmethod
    def print_result(result, evaluator: TicketmasterInfoGathering, scenario: TaskScenario) -> None:
        """Print verification result with debugging info."""
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)
        
        score_pct = result.score * 100
        status = "✅ PASS" if result.score >= 1.0 else "⚠️ PARTIAL" if result.score > 0 else "❌ FAIL"
        
        print(f"Status:           {status}")
        print(f"Score:            {score_pct:.1f}%")
        print(f"Queries Matched:  {result.n_covered}/{result.n_queries}")
        print(f"Pages Navigated:  {len(evaluator._navigation_stack)}")
        print("-" * 80)
        
        # Check for bot blocks in the stack
        bot_blocks = [p for p in evaluator._navigation_stack if p.get("anti_bot") == "blocked_perimeterx"]
        if bot_blocks:
            print("🚨 WARNING: PerimeterX Anti-Bot Block Detected during session! 🚨")
            print("-" * 80)

        for i, covered in enumerate(result.is_query_covered):
            status_icon = "✓" if covered else "✗"
            print(f"  Query {i+1}: [{status_icon}] {'Matched' if covered else 'Not matched'}")
        
        # Show scraped events for debugging
        print("-" * 80)
        print("EVENTS SCRAPED DURING SESSION:")
        all_events = []
        for page_infos in evaluator._all_infos:
            for event in page_infos:
                if event.get("eventName") and event.get("eventName") != "unknown" and event not in all_events:
                    all_events.append(event)
        
        if all_events:
            for i, event in enumerate(all_events, 1):  # Show first 10
                name = event.get("eventName", "unknown").title()
                city = event.get("city") or "?"
                date = event.get("date") or "?"
                price = event.get("price")
                is_resale = event.get("isResale", False)
                source = event.get("source") or "?"
                
                price_str = f"${price}" if price else "?"
                resale_str = "🔄 Resale" if is_resale else "🎫 Standard"
                print(f"  {i}. {name}")
                print(f"     📍 {city} | 📅 {date} | 💰 {price_str} | {resale_str} | 🔗 {source}")
        else:
            print("  No usable events scraped (Check if blocked by anti-bot)")
        
        print("=" * 80 + "\n")
    
    @staticmethod
    def print_summary(results: list) -> None:
        """Print summary of all results."""
        if not results:
            return
        
        print("\n" + "=" * 80)
        print("SESSION SUMMARY")
        print("=" * 80)
        total = len(results)
        passed = sum(1 for r in results if r["score"] >= 1.0)
        print(f"Total Scenarios:  {total}")
        print(f"Passed:           {passed}")
        print(f"Success Rate:     {passed/total*100:.1f}%")
        print("=" * 80 + "\n")


# =============================================================================
# MAIN RUNNER
# =============================================================================

async def run_scenario(scenario: TaskScenario) -> dict:
    """Run a single verification scenario."""

    # Use generate_task_config_deterministic to resolve {dateRange} placeholders
    # and inject resolved ISO dates into queries.
    task_config = generate_task_config_deterministic(
        mode="any",
        task=scenario.task_prompt,
        queries=scenario.queries,
        location=scenario.location,
        timezone=scenario.timezone,
        url=scenario.url,
        values=scenario.values,
    )

    eval_config = task_config.eval_config

    evaluator = TicketmasterInfoGathering(
        queries=eval_config["queries"]
    )
    reporter = ResultReporter()
    rendered_task = task_config.task
    reporter.print_header(scenario, rendered_task)
    reporter.print_instructions()

    input("Press ENTER to launch browser...")

    async with async_playwright() as p:
        browser_mgr = BrowserManager()
        browser, context, page = await browser_mgr.launch(p)

        await evaluator.reset()
        evaluator.attach_to_context(context)

        logger.info(f"Opening {scenario.url}")
        # Ticketmaster load times can be rough, handle timeouts gracefully
        try:
            await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            logger.warning(f"Initial navigation timeout/error (normal for TM): {e}")

        await evaluator.update(page=page)

        print("\n\U0001f310 Browser ready - you are now the agent!")
        print("Navigate through Ticketmaster to complete the task.\n")

        await asyncio.to_thread(
            input,
            "Press ENTER when you've completed the task... "
        )

        try:
            await evaluator.update(page=page)
        except Exception as e:
            logger.warning(f"Final update failed: {e}")

        result = await evaluator.compute()
        await browser_mgr.close()

    reporter.print_result(result, evaluator, scenario)

    return {
        "task_id": scenario.task_id,
        "score": result.score,
        "n_covered": result.n_covered,
        "n_queries": result.n_queries,
        "pages_navigated": len(evaluator._navigation_stack),
    }


async def run_interactive_menu() -> None:
    """Run interactive scenario selection menu."""
    
    print("\n" + "=" * 80)
    print("TICKETMASTER TICKET VERIFICATION SYSTEM")
    print("=" * 80)
    print("\nAvailable scenarios:\n")
    
    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"  [{i}] {scenario.name}")
        print(f"      {scenario.description}")
        print()
    
    print(f"  [A] Run all scenarios")
    print(f"  [Q] Quit")
    print()
    
    choice = input("Select scenario (1-{}, A, or Q): ".format(len(SCENARIOS))).strip().upper()
    
    results = []
    
    if choice == "Q":
        print("Goodbye!")
        return
    elif choice == "A":
        for scenario in SCENARIOS:
            result = await run_scenario(scenario)
            results.append(result)
            if scenario != SCENARIOS[-1]:
                cont = input("\nContinue to next scenario? (y/n): ").strip().lower()
                if cont != "y":
                    break
    elif choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
        idx = int(choice) - 1
        result = await run_scenario(SCENARIOS[idx])
        results.append(result)
    else:
        print("Invalid choice. Please try again.")
        return
    
    ResultReporter.print_summary(results)


async def main():
    """Main entry point."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    try:
        await run_interactive_menu()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye!")
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())