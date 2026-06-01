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
import sys
from dataclasses import dataclass, field

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
        "--disable-web-security",
    ])


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
    tags: list = field(default_factory=list)

    def __post_init__(self):
        """Validate scenario configuration."""
        assert self.task_id, "task_id is required"
        assert self.gt_urls, "gt_urls cannot be empty"


# =============================================================================
# TASK SCENARIOS - Swappa Specific
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    # =========================================================================
    # PRODUCT NAVIGATION — Navigate to the correct product listing page
    # =========================================================================

    TaskScenario(
        task_id="swappa/product_nav/0",
        name="iPhone 15 Pro - Mint, White, 512GB, A2848",
        description="Navigate to iPhone 15 Pro with mint condition, white color, 512GB, A2848 variant, cheapest first, accepting credit cards and PhoneCheck certified.",
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
            "https://swappa.com/listings/apple-iphone-15-pro?condition=mint&color=white&storage=512gb&modeln=QTI4NDg&sort=price_low&accepts_stripe=on&phone_check_certified=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="product_navigation",
        tags=["iphone", "multi_filter", "modeln", "checkboxes", "sort"],
    ),

    TaskScenario(
        task_id="swappa/product_nav/1",
        name="Galaxy S24 Ultra - Good, 256GB, Newest",
        description="Navigate to Samsung Galaxy S24 Ultra with good condition, 256GB, model number, newest first, PhoneCheck and international.",
        url="https://swappa.com/",
        task_prompt=(
            "One of my friends has been trying to replace his old phone so search "
            "for Samsung Galaxy S24 Ultra listings and filter for good condition "
            "with the 256GB storage option and the SM-S928U1 model variant. Sort "
            "the results by newest listings first and make sure only phone check "
            "certified and international shipping listings are shown."
        ),
        gt_urls=[
            "https://swappa.com/listings/samsung-galaxy-s24-ultra?condition=good&storage=256gb&modeln=U00tUzkyOFUx&sort=listing_created_newest&phone_check_certified=on&international=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="product_navigation",
        tags=["samsung", "multi_filter", "modeln", "checkboxes", "sort"],
    ),

    TaskScenario(
        task_id="swappa/product_nav/4",
        name="MacBook Air 2023 15\" - Mint, Space Gray, 1TB, 24GB, M2",
        description="Navigate to MacBook Air with condition, color, storage, memory, processor filters.",
        url="https://swappa.com/",
        task_prompt=(
            "I'm looking for a MacBook Air M2 on Swappa. Find the 2023 15-inch "
            "model in mint condition with the space gray color option, 1TB storage, "
            "24GB memory, and the Apple M2 processor. Sort by lowest price first."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-macbook-air-2023-15?condition=mint&color=space-gray&storage=1tb&memory=24gb&processor=apple-m2&sort=price_low"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="product_navigation",
        tags=["macbook", "laptop", "memory", "processor", "sort"],
    ),

    # =========================================================================
    # CARRIER SELECTION — Navigate + select carrier filter
    # =========================================================================

    TaskScenario(
        task_id="swappa/carrier/0",
        name="iPhone 11 Pro Max - Unlocked, Green, 64GB",
        description="Find unlocked iPhone 11 Pro Max with green color, 64GB, model number, price high, accepting credit cards and international.",
        url="https://swappa.com/",
        task_prompt=(
            "My older brother wants to keep his current phone for at least another "
            "three years, so he has been obsessing over finding a deal that actually "
            "makes sense. Search for Apple iPhone 11 Pro Max listings that are "
            "unlocked in green color with 64GB storage and the A2161 model variant. "
            "Sort results by highest price first and make sure listings accept credit "
            "card payments and offer international shipping."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-11-pro-max?carrier=unlocked&color=green&storage=64gb&modeln=QTIxNjE&sort=price_high&accepts_stripe=on&international=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="carrier_selection",
        tags=["iphone", "unlocked", "modeln", "sort", "checkboxes"],
    ),

    TaskScenario(
        task_id="swappa/carrier/1",
        name="Galaxy S24 - AT&T, Good, Black, 128GB",
        description="Find AT&T Samsung Galaxy S24 in good condition with black color, 128GB, model number, price high, credit cards and PhoneCheck.",
        url="https://swappa.com/",
        task_prompt=(
            "My friend has been trying to cut down on unnecessary spending this year, "
            "so he made a rule for himself that every major purchase has to earn its "
            "value. Find Samsung Galaxy S24 listings in good condition on AT&T carrier "
            "with black color and 128GB storage. Select the SM-S921U1 model variant. "
            "Sort by highest price first and make sure only credit card accepted and "
            "PhoneCheck certified listings show."
        ),
        gt_urls=[
            "https://swappa.com/listings/samsung-galaxy-s24?condition=good&carrier=att&color=black&storage=128gb&modeln=U00tUzkyMVUx&sort=price_high&accepts_stripe=on&phone_check_certified=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="carrier_selection",
        tags=["samsung", "att", "modeln", "sort", "checkboxes"],
    ),

    TaskScenario(
        task_id="swappa/carrier/3",
        name="Pixel 8 - T-Mobile, Good, Hazel, 256GB",
        description="Find T-Mobile Google Pixel 8 in good condition with hazel color, 256GB, model number, price high, and exclude businesses.",
        url="https://swappa.com/",
        task_prompt=(
            "Search for Google Pixel 8 listings in good condition on T-Mobile carrier "
            "with hazel color and 256GB storage. Select the G9BQD model variant. "
            "Sort by highest price first and exclude business sellers."
        ),
        gt_urls=[
            "https://swappa.com/listings/google-pixel-8?condition=good&carrier=t-mobile&color=hazel&storage=256gb&modeln=RzlCUUQ&sort=price_high&exclude_businesses=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="carrier_selection",
        tags=["pixel", "tmobile", "modeln", "sort", "checkboxes"],
    ),

    # =========================================================================
    # CONDITION FILTER — Navigate + condition filter
    # =========================================================================

    TaskScenario(
        task_id="swappa/condition/0",
        name="iPhone 15 - Mint, Unlocked, Black, 128GB",
        description="Find mint condition unlocked iPhone 15 in black, 128GB, sorted by price high, accepting credit cards.",
        url="https://swappa.com/",
        task_prompt=(
            "One of my friends has been putting off upgrading his phone because he "
            "usually keeps devices for years and hates dealing with repair headaches "
            "once the warranty ends. Find Apple iPhone 15 listings in mint condition "
            "that are unlocked with black color and 128GB storage. Sort results by "
            "highest price first and make sure listings accept credit card payments."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15?condition=mint&carrier=unlocked&color=black&storage=128gb&sort=price_high&accepts_stripe=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="condition_filter",
        tags=["iphone", "mint", "unlocked", "sort", "checkboxes"],
    ),

    TaskScenario(
        task_id="swappa/condition/2",
        name="iPhone 15 Pro Max - New, Verizon, White, 256GB",
        description="Find new condition Verizon iPhone 15 Pro Max in white, 256GB, model number, cheapest first, PhoneCheck and international.",
        url="https://swappa.com/",
        task_prompt=(
            "Find new condition Apple iPhone 15 Pro Max listings on Verizon carrier "
            "with white color and 256GB storage. Select the A2849 model variant. Sort "
            "by lowest price first and make sure only PhoneCheck certified and "
            "international shipping listings are shown."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15-pro-max?condition=new&carrier=verizon&color=white&storage=256gb&modeln=QTI4NDk&sort=price_low&phone_check_certified=on&international=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="condition_filter",
        tags=["iphone", "new", "verizon", "modeln", "checkboxes"],
    ),

    TaskScenario(
        task_id="swappa/condition/3",
        name="iPhone 14 - Fair, Verizon, Midnight, 256GB",
        description="Find fair condition Verizon iPhone 14 in midnight, 256GB, model number, cheapest first.",
        url="https://swappa.com/",
        task_prompt=(
            "I want a fair condition Verizon iPhone 14 in the midnight color with "
            "256GB storage. Select the A2649 model variant. Sort by lowest price "
            "first and report the URL."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-14?condition=fair&carrier=verizon&color=midnight&storage=256gb&modeln=QTI2NDk&sort=price_low"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="condition_filter",
        tags=["iphone", "fair", "verizon", "modeln", "sort"],
    ),

    # =========================================================================
    # STORAGE COMBO — Carrier + storage combinations
    # =========================================================================

    TaskScenario(
        task_id="swappa/storage/0",
        name="iPhone 15 - Unlocked, Green, 256GB, Full Checkboxes",
        description="Find unlocked iPhone 15 in green, 256GB, model number, cheapest first, all three checkboxes enabled.",
        url="https://swappa.com/",
        task_prompt=(
            "My friend has been trying to move away from locked carrier contracts "
            "after realizing how much flexibility he loses whenever he travels or "
            "wants to switch providers. Find Apple iPhone 15 listings that are "
            "unlocked in green color with 256GB storage and the A2846 model variant. "
            "Sort by lowest price first and make sure listings accept credit cards, "
            "are PhoneCheck certified, and offer international shipping."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&color=green&storage=256gb&modeln=QTI4NDY&sort=price_low&accepts_stripe=on&phone_check_certified=on&international=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="storage_combo",
        tags=["iphone", "unlocked", "modeln", "sort", "all_checkboxes"],
    ),

    TaskScenario(
        task_id="swappa/storage/4",
        name="iPhone 15 Pro - Verizon, Black, 1TB",
        description="Find Verizon iPhone 15 Pro in black, 1TB, model number, cheapest first, PhoneCheck certified.",
        url="https://swappa.com/",
        task_prompt=(
            "Find Verizon iPhone 15 Pro listings in black color with 1TB storage "
            "and the A2848 model variant. Sort by lowest price first and make sure "
            "only PhoneCheck certified listings are shown."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15-pro?carrier=verizon&color=black&storage=1tb&modeln=QTI4NDg&sort=price_low&phone_check_certified=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="storage_combo",
        tags=["iphone", "verizon", "1tb", "modeln", "checkboxes"],
    ),

    # =========================================================================
    # RED HERRING — Irrelevant narrative mixed with real filters
    # =========================================================================

    TaskScenario(
        task_id="swappa/red_herring/0",
        name="iPhone 15 - Pink, Verizon, Mint (Dance Class Narrative)",
        description="Red herring narrative about dance classes; real filters are iPhone 15, mint, Verizon, pink, 128GB, model number, newest first.",
        url="https://swappa.com/",
        task_prompt=(
            "My friend recently started taking dance and theater classes on weekends, "
            "and he wanted a phone that actually feels fun and expressive instead of "
            "always going with the safe neutral option. Search for Apple iPhone 15 "
            "listings in mint condition on Verizon carrier with the pink color and "
            "128GB storage. Select the A2846 model variant. Sort by newest listings "
            "first. The dance classes are irrelevant to the search."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15?condition=mint&carrier=verizon&color=pink&storage=128gb&modeln=QTI4NDY&sort=listing_created_newest"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="red_herring",
        tags=["iphone", "red_herring", "narrative", "modeln", "sort"],
    ),

    TaskScenario(
        task_id="swappa/red_herring/1",
        name="iPhone 15 Pro Max - Drone Photography Narrative",
        description="Red herring narrative about drone photography; real filters are iPhone 15 Pro Max, good, unlocked, 256GB, model number, newest, credit cards and international.",
        url="https://swappa.com/",
        task_prompt=(
            "My friend recently started taking freelance drone photography jobs on "
            "weekends, but he keeps running into storage problems because he transfers "
            "huge batch files from his drone to his phone for quick edits. None of that "
            "is relevant to Swappa filters. Find Apple iPhone 15 Pro Max in good "
            "condition, unlocked, 256GB storage, A2849 model variant. Sort by newest "
            "first and make sure listings accept credit cards and offer international "
            "shipping."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15-pro-max?condition=good&carrier=unlocked&storage=256gb&modeln=QTI4NDk&sort=listing_created_newest&accepts_stripe=on&international=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="red_herring",
        tags=["iphone", "red_herring", "narrative", "modeln", "checkboxes"],
    ),

    TaskScenario(
        task_id="swappa/red_herring/4",
        name="MacBook Air M2 - Overheating Laptop Narrative",
        description="Red herring about overheating laptop; real filters are MacBook Air 2022, mint, 256GB, 16GB memory, Apple M2 processor, cheapest first.",
        url="https://swappa.com/",
        task_prompt=(
            "My laptop is overheating and the fans sound like a jet engine. The Geek "
            "Squad quoted $180 for cleaning but I'd rather buy a used MacBook Air M2. "
            "The overheating doesn't affect the search. Find MacBook Air 2022 13-inch "
            "listings in mint condition with 256GB storage, 16GB memory, and the Apple "
            "M2 processor. Sort by cheapest first."
        ),
        gt_urls=[
            "https://swappa.com/listings/macbook-air-2022-13?condition=mint&storage=256gb&memory=16gb&processor=apple-m2&sort=price_low"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="red_herring",
        tags=["macbook", "red_herring", "laptop", "memory", "processor"],
    ),

    # =========================================================================
    # MULTI FILTER — 3+ filters combined
    # =========================================================================

    TaskScenario(
        task_id="swappa/multi_filter/0",
        name="iPhone 15 - Mint, Unlocked, Pink, 128GB, Model",
        description="Multiple filters: condition, carrier, color, storage, model number, sort by cheapest.",
        url="https://swappa.com/",
        task_prompt=(
            "I've been scouring the market for a solid upgrade and I've finally set "
            "my sights on an Apple iPhone 15. Find listings in mint condition that "
            "are unlocked with the pink color, 128GB storage, and the A2846 model "
            "variant. Sort by lowest price first."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15?condition=mint&carrier=unlocked&color=pink&storage=128gb&modeln=QTI4NDY&sort=price_low"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="multi_filter",
        tags=["iphone", "multi_filter", "modeln", "sort"],
    ),

    TaskScenario(
        task_id="swappa/multi_filter/2",
        name="iPhone 15 Pro Max - AT&T, Good, Black, 512GB",
        description="Multiple filters: condition, carrier, color, storage, cheapest first, PhoneCheck and international.",
        url="https://swappa.com/",
        task_prompt=(
            "Find AT&T iPhone 15 Pro Max in good condition with black color and "
            "512GB storage. Sort by cheapest first and make sure only PhoneCheck "
            "certified and international shipping listings are shown."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15-pro-max?condition=good&carrier=att&color=black&storage=512gb&sort=price_low&phone_check_certified=on&international=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="multi_filter",
        tags=["iphone", "att", "multi_filter", "checkboxes", "sort"],
    ),

    TaskScenario(
        task_id="swappa/multi_filter/4",
        name="Pixel 8 Pro - Unlocked, Good, Bay, 128GB, Edition",
        description="Multiple filters including edition (base64-encoded), condition, carrier, color, storage, cheapest first.",
        url="https://swappa.com/",
        task_prompt=(
            "Find Google Pixel 8 Pro listings in good condition, unlocked, bay color, "
            "128GB storage. Select the mmWave 5G edition. Sort by cheapest first and "
            "make sure only PhoneCheck certified listings are shown."
        ),
        gt_urls=[
            "https://swappa.com/listings/google-pixel-8-pro?condition=good&carrier=unlocked&color=bay&storage=128gb&edition=bW1XYXZlIDVH&sort=price_low&phone_check_certified=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="multi_filter",
        tags=["pixel", "multi_filter", "edition", "checkboxes", "sort"],
    ),

    # =========================================================================
    # ULTRA HARD — Narrative + arithmetic + multi-filter
    # =========================================================================

    TaskScenario(
        task_id="swappa/ultra_hard/0",
        name="iPhone 15 - Budget Upgrade from iPhone 13",
        description="Sold iPhone 13 for $350, upgrading to iPhone 15. Mint, unlocked, black, 128GB, model number, cheapest first.",
        url="https://swappa.com/",
        task_prompt=(
            "I just finished selling my old iPhone 13 and I'm determined to turn "
            "that cash into a newer Apple iPhone 15 without dipping into my savings. "
            "I've been agonizing over every detail because I want this phone to last. "
            "Find listings in mint condition that are unlocked with black color, "
            "128GB storage, and the A2846 model variant. Sort by cheapest first so "
            "I can stay within my $350 budget."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15?condition=mint&carrier=unlocked&color=black&storage=128gb&modeln=QTI4NDY&sort=price_low"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="ultra_hard",
        tags=["iphone", "ultra_hard", "budget", "narrative", "modeln"],
    ),

    TaskScenario(
        task_id="swappa/ultra_hard/5",
        name="iPhone 15 Pro Max - Biggest iPhone, Most Storage",
        description="Wants biggest iPhone with most storage. Unlocked, good, black, 1TB, model number, cheapest, PhoneCheck + international.",
        url="https://swappa.com/",
        task_prompt=(
            "I want the biggest iPhone with the most storage. That's the iPhone 15 "
            "Pro Max with 1TB. Find listings in good condition, unlocked, black color, "
            "with the A2849 model variant. Sort by cheapest first and make sure "
            "PhoneCheck certified and international shipping listings are shown."
        ),
        gt_urls=[
            "https://swappa.com/listings/apple-iphone-15-pro-max?condition=good&carrier=unlocked&color=black&storage=1tb&modeln=QTI4NDk&sort=price_low&phone_check_certified=on&international=on"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="ultra_hard",
        tags=["iphone", "ultra_hard", "1tb", "modeln", "checkboxes"],
    ),

    TaskScenario(
        task_id="swappa/ultra_hard/9",
        name="Galaxy S24 Ultra - Partner Budget $500",
        description="Partner and I each have $250, total $500 for Galaxy S24 Ultra. Good, unlocked, violet, 512GB, cheapest.",
        url="https://swappa.com/",
        task_prompt=(
            "My partner and I each have $250 — total $500 for a Galaxy S24 Ultra. "
            "Unlocked, good condition, violet color, 512GB storage. The Ultra has the "
            "S Pen which is nice but not a filter. Sort by cheapest first."
        ),
        gt_urls=[
            "https://swappa.com/listings/samsung-galaxy-s24-ultra?condition=good&carrier=unlocked&color=violet&storage=512gb&sort=price_low"
        ],
        location="United States",
        timezone="America/Los_Angeles",
        category="ultra_hard",
        tags=["samsung", "ultra_hard", "budget", "narrative"],
    ),

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

        # Anti-detection scripts
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
            await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")
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
