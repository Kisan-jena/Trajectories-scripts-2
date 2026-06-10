import asyncio
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger

from navi_bench.homedepot.homedepot_url_match import (
    HomeDepotUrlMatch,
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
# SAMPLE HOME DEPOT SCENARIOS
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    TaskScenario(
        task_id="homedepot/search/drills",
        name="Search Power Drills",
        task="Search for cordless power drills.",
        url="https://www.homedepot.com",
        gt_url=[
            "https://www.homedepot.com/s/power%20drill"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="homedepot/category/appliances",
        name="Browse Appliances Category",
        task="Browse appliances category.",
        url="https://www.homedepot.com",
        gt_url=[
            "https://www.homedepot.com/b/Appliances/N-5yc1vZbv1w"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="homedepot/category/flooring",
        name="Browse Flooring Category",
        task="Browse flooring category.",
        url="https://www.homedepot.com",
        gt_url=[
            "https://www.homedepot.com/b/Flooring/N-5yc1vZaq7r"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="homedepot/brand/lg",
        name="Browse LG Brand",
        task="Browse LG brand appliances.",
        url="https://www.homedepot.com",
        gt_url=[
            "https://www.homedepot.com/b/LG-Electronics/N-5yc1vZzvx"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="homedepot/services/flooring_installation",
        name="Flooring Installation Service",
        task="Open flooring installation services page.",
        url="https://www.homedepot.com",
        gt_url=[
            "https://www.homedepot.com/services/c/flooring-installation/8f0a0f8f9"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="homedepot/room/kitchen",
        name="Kitchen Room Ideas",
        task="Browse kitchen room ideas.",
        url="https://www.homedepot.com",
        gt_url=[
            "https://www.homedepot.com/room/kitchen"
        ],
        location="United States",
        timezone="America/Chicago",
    ),
    TaskScenario(
        task_id="homedepot/search/glassware",
        name="Search glassware",
        task=(
            "Search for glassware"
        ),
        url="https://www.homedepot.com",
        gt_url=[
            "https://www.homedepot.com/b/Best-Rated/Pratt-Retail-Specialties/The-Home-Depot/Ziploc/Pick-Up-Today/N-5yc1vZ5usZ6mbZ724Z12l0Zbwo5qZ1z0uh5xZ1z175a5/Ntk-elasticplus/Ntt-glassware?NCNI-5&sortorder=none&sortby=bestmatch"
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

        status = (
            "✅ PASS"
            if result.score >= 1.0
            else "❌ FAIL"
        )

        print(f"Status : {status}")
        print(f"Score  : {result.score}")

        print("\nFinal URL:")
        print(f"  {final_url}")

        print("\nMatched GT URL:")
        print(f"  {evaluator._matched_gt_url}")

        if not result.match:

            print("\nMismatches:")

            for m in result.details.get(
                "mismatches",
                [],
            ):
                print(f"  - {m}")

        print("=" * 60 + "\n")


# =============================================================================
# RUNNER
# =============================================================================

async def run_scenario(
    scenario: TaskScenario
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

    evaluator = HomeDepotUrlMatch(
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

        async def on_navigation():

            try:

                current_url = page.url

                await evaluator.update(
                    url=current_url
                )

                if (
                    "homedepot.com"
                    in current_url
                ):
                    print(
                        f"📍 URL: "
                        f"{current_url[:120]}"
                    )

            except Exception as e:
                logger.debug(e)

        page.on(
            "framenavigated",
            lambda _: asyncio.create_task(
                on_navigation()
            ),
        )

        print(
            "\n🌐 Interact manually "
            "in browser.\n"
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