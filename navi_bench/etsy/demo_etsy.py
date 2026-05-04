import asyncio
import os
import sys
from dataclasses import dataclass, field

from playwright.async_api import async_playwright
from loguru import logger

from navi_bench.etsy.etsy_url_match import (
    EtsyUrlMatch,
    generate_task_config,
)

# =============================================================================
# BROWSER CONFIG
# =============================================================================

@dataclass
class BrowserConfig:
    # Note: viewport/user_agent/locale/launch_args mostly don't apply when
    # connecting to a remote BrightData session over CDP — BrightData manages
    # those server-side. Kept here for compatibility / local-fallback use.
    headless: bool = True
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
# SAMPLE SCENARIOS
# =============================================================================

SCENARIOS: list[TaskScenario] = [

    TaskScenario(
        task_id="etsy/search/macrame_wall",
        name="Search macrame wall",
        task="Search for framed (framing) star seller (Etsy's best) macrame wall for living room (room) over 50 USD with free delivery (special offers), sorted by top reviews.",
        url="https://www.etsy.com",
        gt_url=[
            "https://www.etsy.com/search?"
            "q=macrame%20wall&is_star_seller=true&"
            "order=highest_reviews&min=50&"
            "attr_346=2341&attr_349=2351&"
            "free_shipping=true"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="etsy/search/handbags_women",
        name="Search Handbags for Women",
        task="Search for handbags for women on Etsy.",
        url="https://www.etsy.com",
        gt_url=[
            "https://www.etsy.com/search?q=handbags+for+women"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

    TaskScenario(
        task_id="etsy/search/dresses_women",
        name="Search Dresses for Women (Flexible Query)",
        task="Search for dresses for women.",
        url="https://www.etsy.com",
        gt_url=[
            "https://www.etsy.com/search?q=dresses+for+women"
        ],
        location="United States",
        timezone="America/Chicago",
    ),

]


# =============================================================================
# BROWSER MANAGER — connects to BrightData Scraping Browser over CDP
# =============================================================================

class BrowserManager:
    """Connects to BrightData's remote Scraping Browser over CDP and exposes
    a Chrome DevTools live-debugger URL so you can watch the session."""

    def _init_(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.browser = None
        self.context = None
        self.page = None
        self._cdp_session = None

    async def launch(self, playwright) -> tuple:
        cdp_url = os.environ.get("BROWSER_CDP_URL")
        if not cdp_url:
            raise RuntimeError(
                "BROWSER_CDP_URL environment variable is not set.\n"
                "Set it to your BrightData CDP websocket URL, e.g.:\n"
                "  export BROWSER_CDP_URL='wss://brd-customer-<ID>-zone-<ZONE>:<PASSWORD>@brd.superproxy.io:9222'"
            )

        logger.info("Connecting to BrightData Scraping Browser over CDP...")
        self.browser = await playwright.chromium.connect_over_cdp(cdp_url)
        logger.info("Connected to remote browser.")

        # BrightData sessions expose a default context; reuse it if present.
        self.context = (
            self.browser.contexts[0]
            if self.browser.contexts
            else await self.browser.new_context()
        )

        self.page = await self.context.new_page()

        # Request a live DevTools debugger URL so you can watch the session
        # from Chrome on your local machine.
        try:
            self._cdp_session = await self.context.new_cdp_session(self.page)
            inspect = await self._cdp_session.send("Page.inspect")
            debugger_url = inspect.get("url") or inspect.get("inspectUrl")
            if debugger_url:
                print("\n" + "=" * 60)
                print("🔍 LIVE BROWSER DEBUGGER")
                print("=" * 60)
                print("Open this URL in Chrome on your local machine to")
                print("watch the remote session in DevTools:")
                print()
                print(f"  {debugger_url}")
                print("=" * 60 + "\n")
            else:
                logger.warning(f"Page.inspect returned no URL. Raw response: {inspect}")
        except Exception as e:
            logger.warning(
                f"Couldn't fetch live-debugger URL via Page.inspect ({e}). "
                "You can still open the debugger from the BrightData Control Panel."
            )

        return self.browser, self.context, self.page

    async def close(self) -> None:
        # The context and pages belong to the remote session; don't close them.
        # Just disconnect the local CDP client.
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                # Older Playwright versions prefer disconnect() for CDP connections.
                try:
                    await self.browser.disconnect()
                except Exception:
                    pass
            self.browser = None


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

        evaluator = EtsyUrlMatch(gt_url=resolved_gt_url)
        reporter = ResultReporter()

        reporter.print_header(scenario)

        input("Press ENTER to connect to BrightData browser...")

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

                    if "etsy.com" in current_url:
                        print(f"📍 URL: {current_url[:100]}")

                except Exception as e:
                    logger.debug(e)

            page.on("framenavigated", lambda _: asyncio.create_task(on_navigation()))

            print("\n🌐 Use the DevTools debugger URL (printed above) to interact")
            print("   with the Etsy page, or drive it from code.\n")

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
