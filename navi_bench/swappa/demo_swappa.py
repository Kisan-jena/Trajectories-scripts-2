#!/usr/bin/env python
"""
Swappa URL Match Verification Demo

Human-in-the-loop verification system for Swappa product navigation.
Supports real-time browser navigation, stealth configuration, and
comprehensive evaluation of agent URL matching behavior.

Features:
- Real-time page navigation tracking
- Stealth browser configuration (anti-detection)
- Swappa-specific URL parsing and filter verification
- Interactive scenario selection with rich output
- Debug output showing parsed URL components and match details

Author: NaviBench Team
"""

import asyncio
import csv
import json
import os
import random
import sys
from dataclasses import dataclass

from playwright.async_api import async_playwright

from loguru import logger

# Import Swappa evaluator
from navi_bench.swappa.swappa_url_match import (
    SwappaUrlMatch,
    generate_task_config,
    parse_swappa_url,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class TaskScenario:
    """Defines a Swappa verification task scenario."""
    task_id: str
    name: str
    description: str
    url: str
    task_prompt: str
    gt_urls: list[str]
    location: str
    timezone: str
    category: str
    tags: list = None

    def __post_init__(self):
        """Validate scenario configuration."""
        if self.tags is None:
            self.tags = []
        assert self.task_id, "task_id is required"
        assert self.gt_urls, "gt_urls cannot be empty"


# =============================================================================
# TASK SCENARIOS - Swappa Specific
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    TaskScenario(
        task_id="swappa/product_nav/0",
        name="iPhone 15 Pro - Mint, White, 512GB, A2848",
        description=(
            "Navigate to iPhone 15 Pro listings with mint condition, "
            "white color, 512GB storage, A2848 variant, sorted from "
            "lowest price first, with PhoneCheck certified listings "
            "that accept credit card payments."
        ),
        url="https://swappa.com/",
        task_prompt=(
            "My cousin has been saving up for months to finally upgrade his phone and "
            "has been looking forward to it. Search for iPhone 15 Pro listings and "
            "filter for mint condition only since he wants the phone looking as close "
            "to brand new as possible. Select the white color option, the 512GB "
            "storage model, and the A2848 variant because he spent a lot of time "
            "researching the exact version he wanted before finally deciding to "
            "upgrade. Keep the results limited to phonecheck certified listings that "
            "accept credit card payments so the purchase feels a little safer, and "
            "sort the listings from lowest price to highest first."
        ),
        gt_urls=[
            (
                "https://swappa.com/listings/apple-iphone-15-pro"
                "?condition=mint"
                "&color=white"
                "&storage=512gb"
                "&modeln=QTI4NDg"
                "&sort=price_low"
                "&accepts_stripe=on"
                "&phone_check_certified=on"
            )
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="product_navigation",
        tags=[
            "iphone",
            "multi_filter",
            "modeln",
            "checkboxes",
            "sort",
        ],
    ),
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def human_delay(a: float = 1.0, b: float = 3.0) -> None:
    """Random human-like delay between interactions."""
    await asyncio.sleep(random.uniform(a, b))


# =============================================================================
# BROWSER MANAGER - Stealth browser configuration
# =============================================================================

class BrowserManager:
    """Manages browser lifecycle with stealth configuration using REAL Chrome."""

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    async def launch(self, playwright):
        """
        Launch REAL Chrome with persistent profile.
        Much harder for Swappa/Cloudflare to detect.
        """
        # Create persistent Chrome profile directory
        profile_path = os.path.abspath("./chrome_profile")

        self.context = await playwright.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            channel="chrome",
            headless=False,
            viewport=None,
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        # Use existing tab or create new one
        pages = self.context.pages

        if pages:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()

        # Additional anti-detection JS
        await self.page.add_init_script("""
            // Remove webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Fake chrome runtime
            window.chrome = {
                runtime: {}
            };

            // Fake plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // Fake languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });

            // Permissions fix
            const originalQuery = window.navigator.permissions.query;

            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
        """)

        # Small human-like delay
        await asyncio.sleep(2)

        return None, self.context, self.page

    async def close(self) -> None:
        """Close browser context."""
        if self.context:
            await self.context.close()


# =============================================================================
# RESULT REPORTER - Format and display results
# =============================================================================

class ResultReporter:
    """Formats and displays Swappa verification results."""

    @staticmethod
    def print_header(scenario: TaskScenario) -> None:
        """Print task header."""
        print("\n" + "=" * 80)
        print(f"SWAPPA VERIFICATION: {scenario.name}")
        print("=" * 80)
        print(f"Task ID:     {scenario.task_id}")
        print(f"Category:    {scenario.category}")
        print(f"Location:    {scenario.location}")
        print("-" * 80)
        print(f"TASK: {scenario.task_prompt}")
        print("-" * 80)
        print(f"Expected GT URL(s):")
        for gt in scenario.gt_urls:
            parsed = parse_swappa_url(gt)
            print(f"  {gt}")
            # Show parsed components for visibility
            active_filters = {k: v for k, v in parsed.items()
                             if v and k not in ("page_type",)}
            print(f"  Parsed filters: {active_filters}")
        print("=" * 80)

    @staticmethod
    def print_instructions() -> None:
        """Print user instructions."""
        print("\n" + "-" * 40)
        print("INSTRUCTIONS:")
        print("-" * 40)
        print("1. Use the Swappa website to complete the task")
        print("2. Navigate to the correct product listing page")
        print("3. Apply the requested filters (carrier, condition, storage, color, sort)")
        print("4. Use sidebar checkboxes if required (exclude businesses, credit cards, etc.)")
        print("5. Press ENTER in this terminal when ready to see verification results")
        print("-" * 40 + "\n")

    @staticmethod
    def print_result(result, evaluator: SwappaUrlMatch, scenario: TaskScenario,
                     final_url: str) -> None:
        """Print verification result with debugging info."""
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)

        score_pct = result.score * 100
        status = "PASS" if result.score >= 1.0 else "FAIL"

        print(f"Status:           {status}")
        print(f"Score:            {score_pct:.1f}%")
        print("-" * 80)

        # Show the agent's final URL and parsed components
        print(f"Agent URL:  {final_url}")
        if final_url:
            agent_parsed = parse_swappa_url(final_url)
            active = {k: v for k, v in agent_parsed.items()
                     if v and k not in ("page_type",)}
            print(f"Agent Parsed: {active}")

        print("-" * 80)
        print("GROUND TRUTH URL(s):")
        for gt in scenario.gt_urls:
            gt_parsed = parse_swappa_url(gt)
            active = {k: v for k, v in gt_parsed.items()
                     if v and k not in ("page_type",)}
            print(f"  GT:     {gt}")
            print(f"  Parsed: {active}")

        # If there was a match, show details
        if evaluator._found_match:
            print("-" * 80)
            print("MATCH DETAILS:")
            print(f"  Matched GT: {evaluator._matched_gt_url}")
            if evaluator._match_details.get("extra_params"):
                print(f"  Extra agent params (OK): {evaluator._match_details['extra_params']}")
        else:
            # Show mismatch details from last comparison attempt
            print("-" * 80)
            print("MISMATCH ANALYSIS:")
            if final_url:
                for gt in scenario.gt_urls:
                    match, details = evaluator._urls_match(final_url, gt)
                    if details.get("mismatches"):
                        print(f"  vs {gt[:80]}...")
                        for m in details["mismatches"]:
                            print(f"    X {m}")
            else:
                print("  No URL was captured from the browser.")

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
        print(f"Failed:           {total - passed}")
        print(f"Success Rate:     {passed/total*100:.1f}%")
        print("-" * 80)
        for r in results:
            icon = "PASS" if r["score"] >= 1.0 else "FAIL"
            print(f"  [{icon}] {r['task_id']}")
        print("=" * 80 + "\n")


# =============================================================================
# MAIN RUNNER
# =============================================================================

async def run_scenario(scenario: TaskScenario) -> dict:
    """Run a single Swappa verification scenario."""

    # Create the evaluator with the ground truth URLs
    evaluator = SwappaUrlMatch(scenario.gt_urls)

    reporter = ResultReporter()
    reporter.print_header(scenario)
    reporter.print_instructions()

    input("Press ENTER to launch browser...")

    async with async_playwright() as p:
        browser_mgr = BrowserManager()
        browser, context, page = await browser_mgr.launch(p)

        await evaluator.reset()

        logger.info(f"Opening {scenario.url}")
        try:
            await page.goto(
                scenario.url,
                timeout=60000,
                wait_until="networkidle"
            )
            # Wait like a human
            await human_delay(3, 5)
            # Extra wait for Cloudflare verification to complete
            await asyncio.sleep(10)
        except Exception as e:
            logger.warning(f"Initial navigation timeout/error: {e}")

        print("\nBrowser ready - you are now the agent!")
        print("Navigate through Swappa to complete the task.\n")

        await asyncio.to_thread(
            input,
            "Press ENTER when you've completed the task... "
        )

        # Capture the final URL from the browser
        final_url = page.url
        logger.info(f"Final URL captured: {final_url}")

        # Update the evaluator with the final URL
        await evaluator.update(url=final_url)

        # Also check all open pages in the context
        for ctx_page in context.pages:
            page_url = ctx_page.url
            if page_url != final_url:
                logger.info(f"Also checking tab URL: {page_url}")
                await evaluator.update(url=page_url)

        result = await evaluator.compute()
        await browser_mgr.close()

    reporter.print_result(result, evaluator, scenario, final_url)

    return {
        "task_id": scenario.task_id,
        "score": result.score,
    }


async def run_interactive_menu() -> None:
    """Run interactive scenario selection menu."""

    print("\n" + "=" * 80)
    print("SWAPPA URL MATCH VERIFICATION SYSTEM")
    print("=" * 80)
    print("\nAvailable scenarios:\n")

    # Group by category
    categories = {}
    for scenario in SCENARIOS:
        categories.setdefault(scenario.category, []).append(scenario)

    idx = 0
    scenario_map = {}
    for cat, items in categories.items():
        print(f"  --- {cat.upper().replace('_', ' ')} ---")
        for scenario in items:
            idx += 1
            scenario_map[idx] = scenario
            print(f"  [{idx:2d}] {scenario.name}")
            print(f"       {scenario.description[:75]}...")
            print()

    print(f"  [A] Run all scenarios")
    print(f"  [Q] Quit")
    print()

    choice = input(f"Select scenario (1-{idx}, A, or Q): ").strip().upper()

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
        selected = scenario_map[int(choice)]
        result = await run_scenario(selected)
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
