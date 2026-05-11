import asyncio
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger

from navi_bench.stockx.stockx_url_match import (
    StockxUrlMatch,
    generate_task_config,
)

# =============================================================================
# BROWSER CONFIG
# =============================================================================

@dataclass
class BrowserConfig:
    headless: bool = False
    viewport_width: int = 1366
    viewport_height: int = 768
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    locale: str = "en-US"

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
# SAMPLE STOCKX SCENARIOS
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    TaskScenario(
        task_id="stockx/search/nike_dunks",
        name="Search Nike Dunks",
        task="Search for handbag select brand gucci with color pink gender women and min price as 1783",
        url="https://www.stockx.com",
        gt_url=[
            "https://stockx.com/search?available-now=true&brand=gucci&color=pink&gender=women&lowest-ask-range=1783-2424&s=handbags"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="stockx/search/yeezy_black",
        name="Search Yeezy Black",
        task="Search for adidas in brands those are available now with xpress shipping under category sneakers, product line adidas coupa with men shoe size US M 9",
        url="https://www.stockx.com",
        gt_url=[
            "https://stockx.com/brands/adidas?available-now=true&category=sneakers&mens-shoe-size=US+M+9&product-line=adidas-copa&xpress-ship=true"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="stockx/category/sneakers",
        name="Browse Sneakers Category",
        task="Browse sneakers category.",
        url="https://www.stockx.com",
        gt_url=[
            "https://www.stockx.com/category/sneakers"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="stockx/brand/nike",
        name="Browse Nike Brand",
        task="Browse Nike brand.",
        url="https://www.stockx.com",
        gt_url=[
            "https://www.stockx.com/brands/nike"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="stockx/browse/popular",
        name="Browse Popular Items",
        task="Browse popular items.",
        url="https://www.stockx.com",
        gt_url=[
            "https://www.stockx.com/browse/popular"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="stockx/category/sneakers_adidas_jordan/1",
        name="Adidas Sneakers",
        task="I’ve been browsing lifestyle sneakers for men through category section lately, especially retro-inspired mid-top and high-top shoe height from Adidas and Jordan because they work well for casual streetwear fits without looking too performance-focused. I want pairs that are already available in men’s size 7.5 instead of hard-to-find sold-out releases. I’m not necessarily searching for the cheapest or newest listings — I’m more interested in sneakers that currentlytop selling.",
        url="https://www.stockx.com",
        gt_url=[
            "https://stockx.com/category/sneakers/lifestyle?available-now=true&brand=adidas%2Cjordan&gender=men&mens-shoe-size=US+M+7.5&shoe-height=high%2Cmid&sort=most-active"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
]


# =============================================================================
# BROWSER MANAGER
# =============================================================================

class BrowserManager:

    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.browser = None
        self.context = None
        self.page = None

    async def launch(self, playwright):

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

    async def close(self):
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

    evaluator = StockxUrlMatch(gt_url=resolved_gt_url)
    reporter = ResultReporter()

    reporter.print_header(scenario)

    input("Press ENTER to launch browser...")

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

                if "stockx.com" in current_url:
                    print(f"📍 URL: {current_url[:120]}")

            except Exception as e:
                logger.debug(e)

        page.on("framenavigated", lambda _: asyncio.create_task(on_navigation()))

        print("\n🌐 Interact manually in browser.\n")

        await asyncio.to_thread(input, "Press ENTER when done... ")

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