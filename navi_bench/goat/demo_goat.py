import asyncio
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger


from navi_bench.goat.goat_url_match import (
    GoatUrlMatch,
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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    locale: str = "en-US"

    launch_args: list = field(
        default_factory=lambda: [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
            "--no-sandbox",
        ]
    )


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
# SAMPLE GOAT SCENARIOS
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    # -------------------------------------------------------------------------
    # SEARCH
    # -------------------------------------------------------------------------

    TaskScenario(
        task_id="goat/search/jordan_red",
        name="Search Jordan Red Sneakers",
        task=(
            "Search for Air Jordan sneakers "
            "with red color and men gender."
        ),
        url="https://www.goat.com",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=air+jordan"
                "&colors=red"
                "&genders=men"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="goat/search/casio_gshock_mens_watches",
        name="Search Casio G-SHOCK Men's Watches",
        task=(
        "Search for mens watches and narrow the results "
        "to Casio and G-SHOCK by Casio models only for men. "
        "Filter the results to show only watches that are currently in stock."
        ),
        url="https://www.goat.com",
        gt_url=[
        (
            "https://www.goat.com/search"
            "?query=mens+watches"
            "&pageNumber=1"
            "&brands=Casio%2CG-SHOCK+by+Casio"
            "&genders=men"
            "&inStock=true"
        )
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    # -------------------------------------------------------------------------
    # BRAND
    # -------------------------------------------------------------------------

    TaskScenario(
        task_id="goat/brand/nike",
        name="Browse Nike Brand",
        task="Browse Nike brand products.",
        url="https://www.goat.com",
        gt_url=[
            "https://www.goat.com/brand/nike"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="goat/search/adidas_mens_sweatpants_monochrome",
        name="Search Adidas Men's Monochrome Sweatpants",
        task=(
            "Navigate to the adidas brand page under Featured Brands and "
            "filter for Sweatpants within the Bottoms section. "
            "Filter for mens sizing and only show items in white, grey, or black. "
            "Sort the results by price high to low."
        ),
        url="https://www.goat.com",
        gt_url=[
            (
                "https://www.goat.com/brand/adidas"
                "?slug=adidas"
                "&pageNumber=1"
                "&activities=%2CSweatpants"
                "&genders=men"
                "&colors=white%2Cgrey%2Cblack"
                "&sortType=price_high_low"
                "&categories=Apparel"
                "&types=%2CBottoms"
            ),
            (
                "https://www.goat.com/search"
                "?query=adidas+sweatpants"
                "&pageNumber=1"
                "&categories=Apparel"
                "&types=%2CBottoms"
                "&activities=%2CSweatpants"
                "&sortType=price_high_low"
                "&genders=men"
                "&colors=black%2Cgrey%2Cwhite"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    # -------------------------------------------------------------------------
    # COLLECTION
    # -------------------------------------------------------------------------

    TaskScenario(
        task_id="goat/collection/new_releases",
        name="Browse Just Dropped Collection",
        task="Browse Just Dropped collection.",
        url="https://www.goat.com",
        gt_url=[
            "https://www.goat.com/collections/just-dropped"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    # -------------------------------------------------------------------------
    # CATEGORY
    # -------------------------------------------------------------------------

    TaskScenario(
        task_id="goat/category/sneakers",
        name="Browse Sneakers Category",
        task="Browse sneakers category.",
        url="https://www.goat.com",
        gt_url=[
            "https://www.goat.com/sneakers"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="goat/category/apparel_hoodies",
        name="Browse Apparel Hoodies",
        task="Browse hoodies under apparel.",
        url="https://www.goat.com",
        gt_url=[
            "https://www.goat.com/apparel/tops/hoodies"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="goat/category/bags",
        name="Browse Bags",
        task="Browse bags category.",
        url="https://www.goat.com",
        gt_url=[
            "https://www.goat.com/bags"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    # -------------------------------------------------------------------------
    # FILTERED SEARCH
    # -------------------------------------------------------------------------

    TaskScenario(
        task_id="goat/search/filter_complex",
        name="Complex Filter Search",
        task=(
            "Search for Nike and Adidas sneakers "
            "for men with size 10, "
            "instant ship enabled, "
            "under retail only, "
            "with max price 300."
        ),
        url="https://www.goat.com",
        gt_url=[
            (
                "https://www.goat.com/search"
                "?query=sneakers"
                "&brands=nike,adidas"
                "&genders=men"
                "&instantShip=true"
                "&inStock=true"
                "&priceMax=31000"
            )
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    # -------------------------------------------------------------------------
    # CATEGORY SEARCH
    # -------------------------------------------------------------------------

    TaskScenario(
        task_id="goat/category/apparel",
        name="Search for apparels men and women",
        task=(
            "Apparel men and women"
        ),
        url="https://www.goat.com",
        gt_url=[
            (
                "https://www.goat.com/apparel/tops/hoodies?"
                "&sortType=price_high_low&"
                "genders=men%2Cwomen"
                "&sizes=universal_tops_men_M%2Cuniversal_tops_women_M%2Cuniversal_tops_women_S%2Cuniversal_bottoms_men_XL"
                "&conditions=new_no_defects"
                "&colors=black%2Cgrey"
                "&instantShip=true"
                "&underRetail=true"
                "&inStock=true"
            )
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
    def print_header(
        scenario: TaskScenario,
    ):

        print("\n" + "=" * 70)

        print(
            f"SCENARIO: {scenario.name}"
        )

        print("=" * 70)

        print(
            f"Task ID   : {scenario.task_id}"
        )

        print(
            f"Location  : {scenario.location}"
        )

        print("\nInstructions:")

        print(f"  {scenario.task}")

        print("=" * 70 + "\n")

    @staticmethod
    def print_result(
        result,
        evaluator,
        final_url: str,
    ):

        print("\n" + "=" * 70)

        print("RESULT")

        print("=" * 70)

        status = (
            "✅ PASS"
            if result.score >= 1.0
            else "❌ FAIL"
        )

        print(f"Status : {status}")

        print(f"Score  : {result.score}")

        if result.agent_url:

            print("\nAgent URL:")

            print(f"  {result.agent_url}")

        print("\nFinal URL:")

        print(f"  {final_url}")

        print("\nExpected / Matched GT URL:")

        print(f"  {result.gt_url or evaluator._matched_gt_url}")

        if not result.match:

            print("\nGT URLs checked:")

            for gt_url in getattr(evaluator, "gt_urls", []):

                print(f"  - {gt_url}")

        if not result.match:

            print("\nMismatches:")

            mismatches = result.details.get("mismatches", [])

            if not mismatches:

                print("  (none recorded)")

            for m in mismatches:

                print(f"  - {m}")

        print("=" * 70 + "\n")


# =============================================================================
# RUNNER
# =============================================================================

async def run_scenario(
    scenario: TaskScenario,
):

    task_config = generate_task_config(
        task=scenario.task,
        gt_url=scenario.gt_url,
        location=scenario.location,
        timezone=scenario.timezone,
        url=scenario.url,
    )

    resolved_gt_url = (
        task_config.eval_config["gt_url"]
    )

    evaluator = GoatUrlMatch(
        gt_url=resolved_gt_url
    )

    reporter = ResultReporter()

    reporter.print_header(scenario)

    input(
        "Press ENTER to launch browser..."
    )

    async with async_playwright() as p:

        browser_mgr = BrowserManager()

        browser, context, page = (
            await browser_mgr.launch(p)
        )

        await evaluator.reset()

        logger.info(
            f"Opening {scenario.url}"
        )

        await page.goto(
            scenario.url,
            timeout=60000,
        )

        await evaluator.update(
            url=page.url
        )

        # -------------------------------------------------------------
        # URL TRACKER
        # -------------------------------------------------------------

        async def on_navigation():

            try:

                current_url = page.url

                await evaluator.update(
                    url=current_url
                )

                if "goat.com" in current_url:

                    print(
                        f"📍 URL: "
                        f"{current_url[:140]}"
                    )

            except Exception as e:

                logger.debug(e)

        page.on(
            "framenavigated",
            lambda _:
                asyncio.create_task(
                    on_navigation()
                )
        )

        print(
            "\n🌐 Interact manually in browser.\n"
        )

        await asyncio.to_thread(
            input,
            "Press ENTER when done... ",
        )

        final_url = page.url

        await evaluator.update(
            url=final_url
        )

        result = (
            await evaluator.compute_detailed()
        )

        await browser_mgr.close()

    reporter.print_result(
        result,
        evaluator,
        final_url,
    )


# =============================================================================
# MAIN
# =============================================================================

async def main():

    logger.remove()

    logger.add(
        sys.stderr,
        level="INFO",
    )

    print("\nAvailable Scenarios:\n")

    for i, scenario in enumerate(
        SCENARIOS,
        1,
    ):

        print(
            f"[{i}] {scenario.name}"
        )

    choice = input(
        "\nSelect scenario index: "
    )

    if (
        choice.isdigit()
        and 1 <= int(choice) <= len(SCENARIOS)
    ):

        await run_scenario(
            SCENARIOS[int(choice) - 1]
        )


if __name__ == "__main__":
    asyncio.run(main())