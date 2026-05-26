#!/usr/bin/env python
"""
=================================================================
  Realtor.com NaviBench Demo  --  Human-in-the-Loop Verification
=================================================================

Interactive Playwright-based demo where YOU act as the AI agent.
The system tracks your navigation on realtor.com in real time and
scores your final URL against the expected ground truth.

Features:
  - Real-time URL tracking during navigation
  - Stealth browser configuration (anti-detection)
  - Filter comparison with detailed diff output
  - Multiple search scenarios (sale, rent, sold, open houses, etc.)
  - Interactive scenario menu

Usage:
  cd "c:/Users/HP/Desktop/autonex official"
  python -m navi_bench.realtor.demo_realtor
=================================================================
"""

import asyncio
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger

from navi_bench.realtor.realtor_url_match import (
    RealtorUrlMatch,
    SEARCH_TYPE_PATHS,
    PROPERTY_TYPE_ALIASES,
    SHOW_FLAG_ALIASES,
    SHOW_ABBREV_ALIASES,
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

    # Anti-detection arguments
    launch_args: list = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--start-maximized",
        "--no-sandbox",
    ])


@dataclass
class TaskScenario:
    """Defines a Realtor.com search verification scenario."""
    task_id: str
    name: str
    description: str
    task_prompt: str
    gt_url: str
    location: str = "United States"
    timezone: str = "America/New_York"
    start_url: str = "https://www.realtor.com"
    tags: list = field(default_factory=list)

    def __post_init__(self):
        assert self.task_id, "task_id is required"
        assert self.gt_url, "gt_url is required"


# =============================================================================
# TASK SCENARIOS
# =============================================================================

SCENARIOS: list[TaskScenario] = [
    # 1. Basic for-sale search
    TaskScenario(
        task_id="realtor/for_sale_basic/0",
        name="SF Homes: 3+ Beds Under $1M",
        description="Basic for-sale search with beds and price filters",
        task_prompt=(
            "Find homes for sale in San Francisco, CA with 3+ bedrooms "
            "priced under $1,000,000."
        ),
        gt_url=(
            "https://www.realtor.com/realestateandhomes-search/"
            "San-Francisco_CA/beds-3/price-na-1000000"
        ),
        location="San Francisco, CA, United States",
        timezone="America/Los_Angeles",
        tags=["for-sale", "beds", "price", "basic"],
    ),

    # 2. Property type filter
    TaskScenario(
        task_id="realtor/for_sale_property_type/1",
        name="Denver Condos: $300K-$700K",
        description="For-sale search filtered to condos with price range",
        task_prompt=(
            "Search for condos for sale in Denver, CO priced between "
            "$300,000 and $700,000."
        ),
        gt_url=(
            "https://www.realtor.com/realestateandhomes-search/"
            "Denver_CO/type-condo/price-300000-700000"
        ),
        location="Denver, CO, United States",
        timezone="America/Denver",
        tags=["for-sale", "condo", "price-range"],
    ),

    # 3. Show flags (new construction)
    TaskScenario(
        task_id="realtor/for_sale_show_flags/1",
        name="Phoenix New Construction",
        description="New construction homes for sale",
        task_prompt=(
            "Search for new construction homes for sale in Phoenix, AZ."
        ),
        gt_url=(
            "https://www.realtor.com/realestateandhomes-search/"
            "Phoenix_AZ/shw-nc"
        ),
        location="Phoenix, AZ, United States",
        timezone="America/Phoenix",
        tags=["for-sale", "new-construction", "show-flag"],
    ),

    # 4. Advanced filters (sqft + beds)
    TaskScenario(
        task_id="realtor/for_sale_advanced/0",
        name="Seattle Homes: 3+ Beds, 2000-3000 sqft",
        description="For-sale search with square footage and bedroom filters",
        task_prompt=(
            "Find homes for sale in Seattle, WA with at least 3 bedrooms "
            "and between 2,000 and 3,000 square feet."
        ),
        gt_url=(
            "https://www.realtor.com/realestateandhomes-search/"
            "Seattle_WA/sqft-2000-3000/beds-3"
        ),
        location="Seattle, WA, United States",
        timezone="America/Los_Angeles",
        tags=["for-sale", "sqft", "beds", "advanced"],
    ),

    # 5. Complex multi-filter
    TaskScenario(
        task_id="realtor/for_sale_complex/0",
        name="Dallas Houses: 4bd/3ba, 2500-4000sqft, $500K-$1M",
        description="Complex search with beds, baths, sqft, price, and type",
        task_prompt=(
            "Find houses for sale in Dallas, TX with 4+ bedrooms, "
            "3+ bathrooms, 2,500-4,000 sqft, priced $500K-$1M."
        ),
        gt_url=(
            "https://www.realtor.com/realestateandhomes-search/"
            "Dallas_TX/beds-4/baths-3/price-500000-1000000/"
            "type-single-family-home/sqft-2500-4000"
        ),
        location="Dallas, TX, United States",
        timezone="America/Chicago",
        tags=["for-sale", "complex", "beds", "baths", "price", "type", "sqft"],
    ),

    # 6. Recently sold
    TaskScenario(
        task_id="realtor/recently_sold/0",
        name="Miami Recently Sold: 3+ Beds Under $500K",
        description="Recently sold homes search",
        task_prompt=(
            "Find recently sold homes in Miami, FL with 3+ bedrooms "
            "priced under $500,000."
        ),
        gt_url=(
            "https://www.realtor.com/realestateandhomes-search/"
            "Miami_FL/show-recently-sold/beds-3/price-na-500000"
        ),
        location="Miami, FL, United States",
        timezone="America/New_York",
        tags=["sold", "beds", "price"],
    ),

    # 7. Rentals with pets
    TaskScenario(
        task_id="realtor/for_rent_pets/0",
        name="LA Dog-Friendly Apartments: 2bd Under $3K",
        description="Rental search with pet filter",
        task_prompt=(
            "Find dog-friendly apartments for rent in Los Angeles, CA "
            "with 2+ bedrooms, 1+ bathroom, under $3,000/month."
        ),
        gt_url=(
            "https://www.realtor.com/apartments/Los-Angeles_CA/"
            "type-apartments/dog-friendly/beds-2/baths-1/price-na-3000"
        ),
        location="Los Angeles, CA, United States",
        timezone="America/Los_Angeles",
        tags=["rent", "pets", "dog-friendly", "beds", "baths", "price"],
    ),

    # 8. Zip code search
    TaskScenario(
        task_id="realtor/location_types/0",
        name="Beverly Hills 90210: Houses 3bd/2ba Under $5M",
        description="Zip code based search with type filter",
        task_prompt=(
            "Find single family houses for sale in zip code 90210 with "
            "3+ bedrooms, 2+ bathrooms, priced under $5,000,000."
        ),
        gt_url=(
            "https://www.realtor.com/realestateandhomes-search/"
            "90210/beds-3/baths-2/price-na-5000000/type-single-family-home"
        ),
        location="Beverly Hills, CA, United States",
        timezone="America/Los_Angeles",
        tags=["for-sale", "zip-code", "type", "beds", "baths", "price"],
    ),
]


# =============================================================================
# FILTER LABEL HELPERS
# =============================================================================

def _humanize_filter(key: str, value: str) -> str:
    """Convert a raw filter key + value into a human-readable label."""
    if key == "beds":
        if "-" in value:
            parts = value.split("-")
            return f"Bedrooms: {parts[0]}-{parts[1]}"
        return f"Bedrooms: {value}+"
    elif key == "baths":
        return f"Bathrooms: {value}+"
    elif key == "price":
        parts = value.split("-")
        if len(parts) == 2:
            lo = f"${int(parts[0]):,}" if parts[0] != "na" else "any"
            hi = f"${int(parts[1]):,}" if parts[1] != "na" else "any"
            return f"Price: {lo} - {hi}"
        return f"Price: {value}"
    elif key == "type":
        types = value.split(",")
        labels = [t.replace("-", " ").title() for t in types]
        return f"Property Type: {', '.join(labels)}"
    elif key == "sqft":
        parts = value.split("-")
        if len(parts) == 2:
            lo = f"{int(parts[0]):,}" if parts[0] != "na" else "any"
            hi = f"{int(parts[1]):,}" if parts[1] != "na" else "any"
            return f"Sqft: {lo} - {hi}"
        return f"Sqft: {value}+"
    elif key == "lot":
        return f"Lot Size: {value} sqft"
    elif key == "age":
        return f"Home Age: {value} years"
    elif key == "hoa":
        return f"HOA: up to ${value.replace('na-', '')}/mo"
    elif key == "garage":
        return f"Garage: {value}+ cars"
    elif key == "stories":
        return f"Stories: {value}"
    elif key.startswith("show-"):
        flag = key.replace("show-", "").replace("-", " ").title()
        return f"Flag: {flag}"
    elif key == "dog-friendly":
        return "Pet: Dog-Friendly"
    elif key == "cat-friendly":
        return "Pet: Cat-Friendly"
    elif key.startswith("with_"):
        amenity = key.replace("with_", "").replace("_", " ").title()
        return f"Amenity: {amenity}"
    elif key.startswith("features-"):
        return f"Features: {value}"
    elif key == "days-on-market":
        return f"Days on Market: {value}"
    elif key == "sold-within":
        return f"Sold Within: {value} days"
    elif key == "radius":
        return f"Search Radius: {value} miles"
    else:
        return f"{key}: {value}"


def _search_type_label(st: str) -> str:
    """Human-readable search type label."""
    return {
        "sale": "For Sale",
        "rent": "For Rent",
        "sold": "Recently Sold",
        "open_houses": "Open Houses",
    }.get(st, st)


# =============================================================================
# BROWSER MANAGER
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
                "height": self.config.viewport_height,
            },
            user_agent=self.config.user_agent,
            locale=self.config.locale,
        )

        # Anti-detection scripts
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
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
# RESULT REPORTER
# =============================================================================

class ResultReporter:
    """Formats and displays verification results."""

    @staticmethod
    def print_header(scenario: TaskScenario) -> None:
        """Print task header."""
        print("\n" + "=" * 80)
        print(f"REALTOR.COM SEARCH VERIFICATION: {scenario.name}")
        print("=" * 80)
        print(f"Task ID:     {scenario.task_id}")
        print(f"Location:    {scenario.location}")
        print(f"Timezone:    {scenario.timezone}")
        print("-" * 80)
        print(f"TASK: {scenario.task_prompt}")
        print("-" * 80)
        gt_display = scenario.gt_url[:100] + "..." if len(scenario.gt_url) > 100 else scenario.gt_url
        print(f"Ground Truth URL:")
        print(f"  {gt_display}")
        print("=" * 80)

    @staticmethod
    def print_instructions() -> None:
        """Print user instructions."""
        print("\n" + "-" * 40)
        print("INSTRUCTIONS:")
        print("-" * 40)
        print("1. Use Realtor.com to complete the search")
        print("2. Set the correct location (city or zip)")
        print("3. Apply all the required filters (beds, price, type, etc.)")
        print("4. The system tracks your URL automatically")
        print("5. Press ENTER when ready to verify")
        print("-" * 40 + "\n")

    @staticmethod
    def print_result(
        result,
        evaluator: RealtorUrlMatch,
        scenario: TaskScenario,
        final_url: str,
    ) -> None:
        """Print verification result with detailed URL comparison."""
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)

        score_pct = result.score * 100
        status = "[PASS]" if result.score >= 1.0 else "[FAIL]"

        print(f"Status:  {status}")
        print(f"Score:   {score_pct:.0f}%")
        print("-" * 80)

        if result.score >= 1.0:
            print("Your URL matches the expected search criteria!")
        else:
            # Parse both URLs for detailed comparison
            gt_parsed = evaluator._parse_realtor_url(scenario.gt_url)
            agent_parsed = evaluator._parse_realtor_url(final_url)

            print("URL COMPARISON:")
            print("-" * 80)

            # -- Search Type --
            print(f"\n  SEARCH TYPE:")
            gt_st = _search_type_label(gt_parsed["search_type"])
            agent_st = _search_type_label(agent_parsed["search_type"])
            print(f"    Expected: {gt_st}")
            print(f"    Got:      {agent_st}")
            st_ok = gt_parsed["search_type"] == agent_parsed["search_type"]
            print(f"    Status:   {'[OK]' if st_ok else '[MISMATCH]'}")

            # -- Location --
            print(f"\n  LOCATION:")
            print(f"    Expected: {gt_parsed['location']}")
            print(f"    Got:      {agent_parsed['location']}")
            loc_ok = gt_parsed["location"] == agent_parsed["location"]
            print(f"    Status:   {'[OK]' if loc_ok else '[MISMATCH]'}")

            # -- Filters --
            gt_filters = gt_parsed["filters"]
            agent_filters = agent_parsed["filters"]

            matched = {}
            missing = {}
            wrong_value = {}
            extra = {}

            for key, gt_val in gt_filters.items():
                if key in agent_filters:
                    if agent_filters[key] == gt_val:
                        matched[key] = gt_val
                    else:
                        wrong_value[key] = (gt_val, agent_filters[key])
                else:
                    missing[key] = gt_val

            for key, agent_val in agent_filters.items():
                if key not in gt_filters:
                    extra[key] = agent_val

            print(f"\n  FILTERS:")

            if matched:
                print(f"\n    [OK] Correct filters ({len(matched)}):")
                for key, val in sorted(matched.items()):
                    print(f"      + {_humanize_filter(key, val)}")

            if wrong_value:
                print(f"\n    [MISMATCH] Wrong values ({len(wrong_value)}):")
                for key, (gt_val, agent_val) in sorted(wrong_value.items()):
                    print(f"      - {key}:")
                    print(f"        Expected: {_humanize_filter(key, gt_val)}")
                    print(f"        Got:      {_humanize_filter(key, agent_val)}")

            if missing:
                print(f"\n    [MISSING] Missing filters ({len(missing)}):")
                for key, val in sorted(missing.items()):
                    print(f"      - {_humanize_filter(key, val)}")

            if extra:
                print(f"\n    [EXTRA] Extra filters ({len(extra)}):")
                for key, val in sorted(extra.items()):
                    print(f"      ~ {_humanize_filter(key, val)}")

        print("\n" + "=" * 80)
        print("URLS:")
        print("-" * 80)
        print(f"Expected: {scenario.gt_url}")
        print(f"Got:      {final_url}")
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
        print(f"Success Rate:     {passed / total * 100:.1f}%")

        print("-" * 80)
        for r in results:
            status = "[PASS]" if r["score"] >= 1.0 else "[FAIL]"
            print(f"  {status} {r['task_id']}")

        print("=" * 80 + "\n")


# =============================================================================
# RUNNER
# =============================================================================

async def run_scenario(scenario: TaskScenario) -> dict:
    """Run a single verification scenario."""

    # Create evaluator with nested gt_urls structure: list[list[str]]
    evaluator = RealtorUrlMatch(gt_urls=[[scenario.gt_url]])
    reporter = ResultReporter()

    # Display task info
    reporter.print_header(scenario)
    reporter.print_instructions()

    input("Press ENTER to launch browser...")

    async with async_playwright() as p:
        # Launch browser
        browser_mgr = BrowserManager()
        browser, context, page = await browser_mgr.launch(p)

        # Initialize evaluator
        await evaluator.reset()

        # Navigate to start URL
        logger.info(f"Opening {scenario.start_url}")
        await page.goto(scenario.start_url, timeout=60000, wait_until="domcontentloaded")

        # Track initial URL
        await evaluator.update(url=page.url)

        # Set up real-time URL tracking
        async def on_navigation():
            try:
                current_url = page.url
                await evaluator.update(url=current_url)
                if "realtor.com" in current_url:
                    display_url = current_url[:100] + "..." if len(current_url) > 100 else current_url
                    print(f"  -> URL: {display_url}")
            except Exception as e:
                logger.debug(f"Navigation tracking error: {e}")

        page.on("framenavigated", lambda frame: asyncio.create_task(on_navigation()))

        print("\n  Browser ready -- you are now the agent!")
        print("  Navigate Realtor.com and apply the required filters.\n")

        # Wait for user completion
        await asyncio.to_thread(
            input,
            "Press ENTER when you've completed the task... ",
        )

        # Get final URL
        final_url = page.url

        # Final evaluation
        await evaluator.update(url=final_url)
        result = await evaluator.compute()

        # Close browser
        await browser_mgr.close()

    # Display results
    reporter.print_result(result, evaluator, scenario, final_url)

    return {
        "task_id": scenario.task_id,
        "score": result.score,
        "final_url": final_url,
    }


# =============================================================================
# MENU
# =============================================================================

async def run_interactive_menu() -> None:
    """Run interactive scenario selection menu."""

    print("\n" + "=" * 80)
    print("REALTOR.COM SEARCH VERIFICATION SYSTEM")
    print("=" * 80)
    print("\nAvailable scenarios:\n")

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"  [{i}] {scenario.name}")
        print(f"      {scenario.description}")
        print()

    print(f"  [A] Run all scenarios")
    print(f"  [Q] Quit")
    print()

    choice = input(f"Select scenario (1-{len(SCENARIOS)}, A, or Q): ").strip().upper()

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

    # Print summary
    ResultReporter.print_summary(results)


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Main entry point."""

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
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
