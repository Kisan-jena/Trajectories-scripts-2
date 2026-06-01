4#!/usr/bin/env python
import asyncio
import sys
from dataclasses import dataclass
from playwright.async_api import async_playwright
from loguru import logger

from navi_bench.rome2rio.rome2rio_info_gathering import Rome2RioInfoGathering

# ---------------- CONFIG ----------------


@dataclass
class TaskScenario:
    """Configuration for a single Rome2Rio demo task."""

    task_id: str
    name: str
    url: str
    task_prompt: str
    queries: list
    mode: str = "any"
    timezone: str = "Asia/Kolkata"


SCENARIOS = [
    # TaskScenario(
    #     task_id="fast",
    #     name="Rome to Florence - Under 2h",
    #     description="",
    #     url="https://www.rome2rio.com/",
    #     task_prompt="Find transport options from Rome to Florence under 2 hours.",
    #     queries=[[{"max_duration": 120}]]
    # ),
    # TaskScenario(
    #     task_id="cheap",
    #     name="Cheapest route under ₹3000",
    #     description="",
    #     url="https://www.rome2rio.com/",
    #     task_prompt="Find the cheapest route under ₹3000.",
    #     queries=[[{"max_price": 3000}]]
    # ),
    #     TaskScenario(
    #     task_id="del_nyc_flight_duration_bracket",
    #     name="New Delhi to New York - Flight (18-32h)",
    #     description="",
    #     url="https://www.rome2rio.com/",
    #     task_prompt="I'm looking for flight routes from New Delhi to New York. Tell me info about the top listing where the travel time is strictly between 18 hours (1080 mins) and 32 hours (1920 mins).",
    #     queries=[[{"origins": ["new delhi"], "destinations": ["new york"], "min_duration": 1080, "max_duration": 1920}]]
    # )
    TaskScenario(
        task_id="del_london_stansted_under_18h",
        name="New Delhi to London Stansted - Under 18 Hours",
        url="https://www.rome2rio.com/",
        task_prompt=(
            "Find routes from New Delhi to London arriving at "
            "London Stansted Airport where the total travel "
            "time is under 18 hours (1080 mins)."
        ),
        queries=[
            [
                {
                    "origins": ["new delhi"],
                    "destinations": ["london"],
                    "modes": ["london stansted airport"],
                    "max_duration": 1080,
                }
            ]
        ],
    ),
    # 6
    TaskScenario(
        task_id="par_budget_5star",
        name="Paris 5-Star Hotel Under USD 1000",
        url="https://www.rome2rio.com/",
        task_prompt=("Find a 5-star hotel in Paris for next weekend " "that costs less than USD 1000 per night."),
        queries=[
            [
                {
                    "cities": ["paris"],
                    "min_stars": 5,
                    "max_price": 00.0,
                }
            ]
        ],
        mode="any",
        timezone="Europe/Paris",
    ),
    TaskScenario(
        task_id="ams_market_centre_budget",
        name="Amsterdam Market/Centre Hotel Under USD 200",
        url="https://www.rome2rio.com/",
        task_prompt=(
            "Find a 3- or 4-star hotel in Amsterdam for next Sunday "
            "with 'Market' or 'Centre' in the name, a review score of at least 8.0, "
            "and costing less than USD 600 per night."
        ),
        queries=[
            [
                {
                    "cities": ["amsterdam"],
                    "min_stars": 3,
                    "max_stars": 4,
                    "modes": ["market", "centre"],
                    "min_score": 8.0,
                    "max_price": 600.0,
                }
            ]
        ],
        mode="any",
        timezone="Europe/Amsterdam",
    ),
    TaskScenario(
        task_id="hin_fra_indigo_emirates_exact",
        name="Hindon to Frankfurt - IndiGo + Emirates",
        url="https://www.rome2rio.com/",
        task_prompt=(
            "Tell me info about the top listing for a flight schedule from Hindon "
            "to Frankfurt that combines IndiGo Airlines and Emirates. I need the "
            "duration to be exactly 33.5 hours (2010 minutes) and the price to be "
            "strictly between USD 500 and USD 1000."
        ),
        queries=[
            [
                {
                    "origins": ["delhi"],
                    "destinations": ["frankfurt"],
                    "modes": ["indigo airlines", "aegean airlines"],
                    "min_duration": 2010,
                    "max_duration": 2010,
                    "min_price": 500.0,
                    "max_price": 2000.0,
                }
            ]
        ],
        mode="all",
        timezone="Asia/Kolkata",
    ),
    TaskScenario(
        task_id="hindon_frankfurt_indigo_emirates",
        name="Hindon to Frankfurt - IndiGo and Emirates",
        url="https://www.rome2rio.com/",
        task_prompt=(
            "Tell me info about the top listing for a flight schedule from "
            "Delhi (departing from Hindon) to Frankfurt on next Friday that "
            "combines IndiGo Airlines and Scandinavian Airlines."
        ),
        queries=[
            [
                {
                    "origins": ["delhi"],
                    "destinations": ["frankfurt am main"],
                    "modes": ["indigo airlines", "air india limited"],
                    # "min_duration": 5,
                    # "max_duration": 15,
                    # "min_price": 1.0,
                    # "max_price": 2.0,
                }
            ]
        ],
        mode="all",
        timezone="Asia/Kolkata",
    ),
    TaskScenario(
        task_id="hindon_frankfurt_long_expensive",
        name="Hindon to Frankfurt - Long and Expensive",
        url="https://www.rome2rio.com/",
        task_prompt=(
            "Are there any routes from New Delhi to Frankfurt am Main departing "
            "from Hindon? Tell me info about the top listing that takes longer "
            "than 20 hours (1200 mins) and costs more than USD 1000."
        ),
        queries=[
            [
                {
                    "origins": ["new delhi"],
                    "destinations": ["frankfurt am main"],
                    "modes": ["hindon"],
                    "min_duration": 200,
                    "min_price": 500.0,
                }
            ]
        ],
        mode="any",
        timezone="Asia/Kolkata",
    ),
    TaskScenario(
        task_id="ams_keukenhof_shuttle",
        name="Amsterdam Keukenhof Shuttle",
        url="https://www.rome2rio.com/",
        task_prompt=(
            "Find the Keukenhof Shuttle Bus experience from Amsterdam Schiphol "
            "Airport. It must have a rating of at least 4.6, a duration of exactly "
            "240 minutes, and a price strictly capped at USD 700."
        ),
        queries=[
            [
                {
                    "cities": ["amsterdam"],
                    "modes": ["keukenhof", "shuttle"],
                    "min_rating": 4,
                    "max_price": 700.0,
                }
            ]
        ],
        mode="all",
        timezone="Europe/Amsterdam",
    ),
    TaskScenario(
        task_id="berlin_hemingway_boutiquestyle_tour",
        name="Berlin Hemingway Boutiquestyle Tour",
        url="https://www.rome2rio.com/",
        task_prompt=(
            "Find any 'Hemingway' or 'Boutiquestyle' tours in Berlin for "
            "upcoming Monday. The tour must last exactly 60 minutes, "
            "have a rating above 4.5, and cost strictly under USD 300. "
            "Summarize the top matching option."
        ),
        queries=[
            [
                {
                    "cities": ["berlin"],
                    "modes": ["hemingway", "boutiquestyle"],
                    "min_duration": 60,
                    "max_duration": 60,
                    "min_rating": 4.5,
                    "max_price": 300.0,
                }
            ]
        ],
        mode="any",
        timezone="Europe/Berlin",
    ),
]


# ---------------- RESULT REPORT ----------------


class ResultReporter:
    @staticmethod
    def print_result(result, evaluator=None, queries=None):
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)

        score_pct = result.score * 100
        status = "✅ PASS" if result.score >= 1.0 else "⚠️ PARTIAL" if result.score > 0 else "❌ FAIL"

        print(f"Status:           {status}")
        print(f"Score:            {score_pct:.1f}%")
        print(f"Queries Matched:  {result.n_covered}/{result.n_queries}")
        print("-" * 80)

        # Show all scraped routes and why they matched / didn't
        if evaluator and evaluator._infos:
            print("\nSCRAPED ROUTES:")
            for i, info in enumerate(evaluator._infos, 1):
                mode = info.get("mode") or info.get("name") or "?"
                price = f"{info.get('min_price')}" if info.get("min_price") is not None else "N/A"
                duration = f"{info.get('duration')} min" if info.get("duration") is not None else "N/A"

                # Check which queries this route satisfies
                matched_qs = []
                if queries:
                    for qi, qgroup in enumerate(queries):
                        for q in qgroup:
                            if evaluator._match(q, info):
                                matched_qs.append(qi + 1)
                                break

                match_tag = f"✓ matches query {matched_qs}" if matched_qs else "✗ no match"
                line = f"  {i}. {mode} | {price} | {duration}  [{match_tag}]"

                # If no match, show concise reasons for the first query group
                if not matched_qs and queries:
                    # Use the first query in the first group as representative
                    representative_q = queries[0][0]
                    reasons = evaluator.why_not_match(representative_q, info)
                    if reasons:
                        line += f" -- reasons: {', '.join(reasons)}"

                print(line)

        print("=" * 80)


# ---------------- CORE ----------------


async def run_scenario(scenario):
    logger.info(f"[DEMO] Starting scenario: {scenario.name}")
    logger.info(f"[DEMO] Task ID: {scenario.task_id}")
    logger.info(f"[DEMO] Mode: {scenario.mode}")
    logger.info(f"[DEMO] Queries: {scenario.queries}")

    evaluator = Rome2RioInfoGathering(scenario.queries, mode=scenario.mode)
    reporter = ResultReporter()

    print(f"\n{'='*60}\nTASK: {scenario.task_prompt}\n{'='*60}")
    input("Press ENTER to launch browser...")
    logger.info("[DEMO] Browser launching...")

    async with async_playwright() as p:

        # Dont usee channel = chrome , by using the it will try to launch system chrome, instead of playwright.
        context = await p.chromium.launch_persistent_context(
            user_data_dir="rome2rio_user_data",  # saves cookies/session
            headless=False,
            # channel="chrome",
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id=scenario.timezone,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()

        def handle_console(msg):
            try:
                text = msg.text
            except Exception:
                text = msg.text()
            if "[DEBUG JS]" in text:
                print(text)

        page.on("console", handle_console)

        # ✅ Go to site
        await page.goto(scenario.url, wait_until="domcontentloaded")

        print("[SYSTEM] Waiting for page load...")
        await page.wait_for_timeout(5000)

        # ✅ Human-like interaction
        await page.mouse.move(200, 300)
        await page.wait_for_timeout(1000)
        await page.mouse.move(400, 500)
        await page.wait_for_timeout(1000)

        print("\n👉 If Cloudflare appears, solve it once manually.")
        await asyncio.to_thread(
            input, "\nNavigate to the page you want, then press ENTER to begin continuous scraping... "
        )

        # ---------------- CONTINUOUS SCRAPING ----------------
        print("\n[SYSTEM] Scraping live. Press ENTER at any time to stop and see the result.\n")

        stop_event = asyncio.Event()

        async def scrape_loop():
            iteration = 0
            while not stop_event.is_set():
                iteration += 1
                try:
                    active_page = context.pages[-1]
                    page_url = active_page.url
                    is_trip_details = "/trips?" in page_url

                    # Count elements with detailed logging
                    count_results = await active_page.locator('[data-testid^="trip-search-result"]').count()
                    count_schedules = await active_page.locator('[aria-labelledby^="schedule-cell-times-"]').count()
                    count_hotels = await active_page.locator('[data-testid="hotel-list-item"]').count()
                    count_booking_hotels = await active_page.locator('[data-testid="property-card"]').count()
                    count_booking_titles = await active_page.locator('[data-testid="title"]').count()
                    count_experiences = await active_page.locator("article").count()

                    if iteration == 1:
                        print(f"\n[DEBUG] Page URL: {page_url}")

                        if is_trip_details:
                            print(f"[DEBUG]  On TRIP DETAILS page (trying to extract itinerary)")
                        else:
                            print(f"[DEBUG] On ROUTES LIST page")

                        print(f"[DEBUG] Looking for elements with these selectors:")
                        print(f'  - [data-testid^="trip-search-result"]: {count_results} found')
                        print(f'  - [aria-labelledby^="schedule-cell-times-"]: {count_schedules} found')
                        print(f'  - [data-testid="hotel-list-item"]: {count_hotels} found')
                        print(f'  - [data-testid="property-card"]: {count_booking_hotels} found')
                        print(f'  - [data-testid="title"]: {count_booking_titles} found')
                        print(f"  - article (experiences): {count_experiences} found\n")

                    if iteration % 5 == 1:  # Log every 5 iterations
                        print(
                            f"[ITER {iteration}] Results={count_results}, Schedules={count_schedules}, Hotels={count_hotels}, Booking={count_booking_hotels}, Exp={count_experiences}"
                        )

                    should_evaluate = (
                        count_results > 0
                        or count_schedules > 0
                        or count_hotels > 0
                        or count_booking_hotels > 0
                        or count_booking_titles > 0
                        or count_experiences > 0
                        or is_trip_details
                    )

                    if should_evaluate:
                        if (
                            is_trip_details
                            and count_results == 0
                            and count_schedules == 0
                            and count_hotels == 0
                            and count_booking_hotels == 0
                            and count_booking_titles == 0
                            and count_experiences == 0
                        ):
                            print("  ✓ Trip details page detected. Running evaluator...")
                        else:
                            print(f"  ✓ Found elements! Running evaluator...")
                        await evaluator.update(page=active_page)
                        result = await evaluator.compute()
                        print(f"  ✓ Result: {result.n_covered}/{result.n_queries} queries matched\n")
                        if result.score >= 1.0:
                            print("\n✅ All target queries covered!")
                            stop_event.set()
                            return
                    else:
                        if iteration == 1:
                            print("[⚠️  WARNING] No route elements found on page!")
                            print("    Possible causes:")
                            if is_trip_details:
                                print("    1. Trip details page is still loading")
                                print("    2. Trip overview layout changed")
                            else:
                                print("    1. DOM selectors are outdated (Rome2Rio redesigned page)")
                                print("    2. Page hasn't loaded yet")
                                print("    3. Wrong page (not the search results page)")

                except Exception as e:
                    print(f"[ERROR] {e}")
                    import traceback

                    traceback.print_exc()
                await asyncio.sleep(3)

        async def wait_for_enter():
            await asyncio.to_thread(input, "")
            stop_event.set()

        await asyncio.gather(scrape_loop(), wait_for_enter())

        # Always print final result
        final_result = await evaluator.compute()
        reporter.print_result(final_result, evaluator, scenario.queries)

    return final_result


# ---------------- MAIN ----------------


async def main():
    logger.remove()
    logger.add(sys.stderr, format="<level>{message}</level>", level="DEBUG")
    logger.info("=" * 80)
    logger.info("ROME2RIO DEMO STARTED")
    logger.info("=" * 80)

    for i, s in enumerate(SCENARIOS, 1):
        print(f"[{i}] {s.name}")

    choice = input("\nSelect scenario index: ")

    if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
        logger.info(f"Selected scenario: {SCENARIOS[int(choice) - 1].name}")
        await run_scenario(SCENARIOS[int(choice) - 1])

    logger.info("=" * 80)
    logger.info("ROME2RIO DEMO ENDED")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
