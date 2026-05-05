import asyncio
import os
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger

from navi_bench.ebay.ebay_url_match import (
    EbayUrlMatch,
    generate_task_config,
)

# =============================================================================
# BROWSER CONFIG
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

# =============================================================================
# TASK SCENARIO
# =============================================================================

@dataclass
class TaskScenario:
    task_id: str
    name: str
    task: str
    url: str
    gt_url: list[str]
    location: str
    timezone: str

    def __post_init__(self):
        assert self.task_id
        assert self.gt_url


# =============================================================================
# SAMPLE SCENARIOS (EBAY)
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    TaskScenario(
        task_id="ebay/search/laptop_under_500",
        name="Search Laptop under $500",
        task="Search for laptops under 500 USD with free shipping, sorted by lowest price.",
        url="https://www.ebay.com",
        gt_url=[
            "https://www.ebay.com/sch/i.html?"
            "_nkw=laptop&_udhi=500&LH_FS=1&_sop=15"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="ebay/search/iphone",
        name="Search iPhone",
        task="Search for iPhone.",
        url="https://www.ebay.com",
        gt_url=[
            "https://www.ebay.com/sch/i.html?_nkw=iphone"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="ebay/search/shoes_men",
        name="Search Men's Shoes",
        task="Search for men's shoes with buy it now option only.",
        url="https://www.ebay.com",
        gt_url=[
            "https://www.ebay.com/sch/i.html?_nkw=mens+shoes&LH_BIN=1"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="ebay/category/cars_trucks",
        name="Browse Cars & Trucks Category",
        task="Go to Cars & Trucks category on eBay.",
        url="https://www.ebay.com",
        gt_url=[
            "https://www.ebay.com/b/Cars-Trucks/6001"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="ebay/category/fashion_price_range",
        name="Fashion under $100",
        task="Browse Fashion category items under 100 USD.",
        url="https://www.ebay.com",
        gt_url=[
            "https://www.ebay.com/b/Womens-Clothing-Shoes-Accessories/260010/bn_7116391826?"
            "_udlo=75"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="ebay/kids/toys_and_hobbies",
        name="Toys & Hobbies",
        task="Browse Toys and hobbies category in new condition for 1-2 year kid between $17- $35 with free local pickup",
        url="https://www.ebay.com",
        gt_url=[
            "https://www.ebay.com/b/1-2-Years-Kids-Toys-Hobbies/220/bn_108444886?_udlo=17&mag=1&LH_LPickup=1&LH_ItemCondition=1000&_udhi=35"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="ebay/brand/Lacoste_men",
        name="Lacoste_men",
        task="Browse for Lacoste brand in all brands for men between $38.99-89.99 with new condition with best offer." \
        "Show only free international shipping us location and deals and saving",
        url="https://www.ebay.com",
        gt_url=[
            "https://www.ebay.com/sch/i.html?_nkw=gaming+laptop"
            "&LH_FS=1&RAM%2520Size=64%2520GB"
            "&Most%2520Suitable%2520For=Gaming"
            "&_dcat=177&_udlo=1%2C500&_udhi=3%2C500"
            "&LH_ItemCondition=3000&LH_BIN=1&_sop=15"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
]


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
# REPORTER
# =============================================================================

class ResultReporter:

    @staticmethod
    def print_header(scenario: TaskScenario):
        print("\n" + "=" * 60)
        print(f"SCENARIO: {scenario.name}")
        print("=" * 60)

        print(f"Task ID   : {scenario.task_id}")
        print(f"Location  : {scenario.location}")

        print("\nInstructions:")
        print(f"  {scenario.task}")
        print("=" * 60 + "\n")

    @staticmethod
    def print_result(result, evaluator, final_url: str):
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)

        status = "✅ PASS" if result.score >= 1.0 else "❌ FAIL"

        print(f"Status : {status}")
        print(f"Score  : {result.score}")

        print("\nFinal URL:")
        print(f"  {final_url}")

        print("\nMatched GT URL:")
        print(f"  {evaluator._matched_gt_url}")

        if not result.match:
            print("\nMismatches:")
            for m in result.details.get("mismatches", []):
                print(f"  - {m}")

        print("=" * 60 + "\n")


# =============================================================================
# RUNNER
# =============================================================================

async def run_scenario(scenario: TaskScenario):

    task_config = generate_task_config(
        task=scenario.task,
        gt_url=scenario.gt_url,
        location=scenario.location,
        timezone=scenario.timezone,
        url=scenario.url,
    )

    resolved_gt_url = task_config.eval_config["gt_url"]

    evaluator = EbayUrlMatch(gt_url=resolved_gt_url)
    reporter = ResultReporter()

    reporter.print_header(scenario)

    input("Press ENTER to connect to browser...")

    async with async_playwright() as p:
        browser_mgr = BrowserManager()
        browser, context, page = await browser_mgr.launch(p)

        await evaluator.reset()

        logger.info(f"Opening {scenario.url}")
        await page.goto(scenario.url, timeout=60000)

        await evaluator.update(url=page.url)

        async def on_navigation():
            try:
                current_url = page.url
                await evaluator.update(url=current_url)

                if "ebay.com" in current_url:
                    print(f"📍 URL: {current_url[:120]}")

            except Exception as e:
                logger.debug(e)

        page.on("framenavigated", lambda _: asyncio.create_task(on_navigation()))

        print("\n🌐 Interact via DevTools or manually.\n")

        await asyncio.to_thread(
            input,
            "Press ENTER when done... ",
        )

        final_url = page.url

        await evaluator.update(url=final_url)
        result = await evaluator.compute_detailed()

        await browser_mgr.close()

    reporter.print_result(result, evaluator, final_url)


# =============================================================================
# MAIN
# =============================================================================

async def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"[{i}] {scenario.name}")

    choice = input("\nSelect scenario index: ")

    if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
        await run_scenario(SCENARIOS[int(choice) - 1])


if __name__ == "__main__":
    asyncio.run(main())