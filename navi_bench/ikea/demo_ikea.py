#!/usr/bin/env python
import asyncio
import sys
from dataclasses import dataclass, field
from playwright.async_api import async_playwright
from loguru import logger

# Import the IKEA evaluator
from ikea_url_match import IkeaUrlMatch

@dataclass
class BrowserConfig:
    headless: bool = False
    viewport_width: int = 1366
    viewport_height: int = 768
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    locale: str = "en-US"
    launch_args: list = field(default_factory=lambda: [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--start-maximized",
        "--no-sandbox",
    ])

@dataclass
class TaskScenario:
    task_id: str
    name: str
    description: str
    url: str
    task_prompt: str
    gt_url: list  # Ground truth URL(s)
    location: str = "United States"
    timezone: str = "America/Los_Angeles"

# Demo Scenarios for IKEA US (ikea.com/us/en/)
SCENARIOS: list[TaskScenario] = [
    TaskScenario(
        task_id="ikea/search_nav/white_desks_cheap",
        name="White Desks — Sorted by Lowest Price",
        description="Search for white desks and sort by cheapest first.",
        url="https://www.ikea.com/us/en/",
        task_prompt=(
            "Search for white desks on IKEA US and sort by lowest price."
        ),
        gt_url=[
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"
        ],
    ),
    TaskScenario(
        task_id="ikea/category_nav/sofas_beige_popular",
        name="Beige Sofas Category — Most Popular",
        description="Navigate to Sofas category, filter beige, sort by popular.",
        url="https://www.ikea.com/us/en/",
        task_prompt=(
            "Find beige sofas in the Sofas category on IKEA, sorted by most popular."
        ),
        gt_url=[
            "https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10003&sort=MOST_POPULAR"
        ],
    ),
    TaskScenario(
        task_id="ikea/search_nav/black_dining_chairs",
        name="Black Dining Chairs — Color Filter",
        description="Search for dining chairs and apply the black color filter.",
        url="https://www.ikea.com/us/en/",
        task_prompt=(
            "Search for dining chairs on IKEA US and filter by black color."
        ),
        gt_url=[
            "https://www.ikea.com/us/en/search/?q=dining+chair&filters=f-colors:10005",
            "https://www.ikea.com/us/en/search/?q=dining%20chair&filters=f-colors:10005",
        ],
    ),
    TaskScenario(
        task_id="ikea/multi_filter/desks_white_under_100",
        name="White Desks Under $100 — Multi-Filter",
        description="Search for white desks under $100 with color + price filters.",
        url="https://www.ikea.com/us/en/",
        task_prompt=(
            "Find white desks under $100 on IKEA US."
        ),
        gt_url=[
            "https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156,f-price-buckets:PRICE_0_10000"
        ],
    ),
    TaskScenario(
        task_id="ikea/category_nav/wardrobes_cheapest",
        name="Wardrobes Category — Cheapest First",
        description="Navigate to Wardrobes category and sort by lowest price.",
        url="https://www.ikea.com/us/en/",
        task_prompt=(
            "Browse the Wardrobes category on IKEA US, sorted by cheapest first."
        ),
        gt_url=[
            "https://www.ikea.com/us/en/cat/wardrobes-19053/?sort=PRICE_LOW_TO_HIGH"
        ],
    ),
]

class ResultReporter:
    @staticmethod
    def print_result(result, evaluator, scenario) -> None:
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)

        score_pct = result.score * 100
        status = "✅ PASS" if result.score >= 1.0 else "❌ FAIL"

        print(f"Status:           {status}")
        print(f"Score:            {score_pct:.1f}%")
        print(f"Task:             {scenario.task_prompt}")
        print(f"Expected URL(s):  {scenario.gt_url}")
        print(f"Agent URL:        {evaluator._agent_url or '(none captured)'}")

        if hasattr(evaluator, '_match_details') and evaluator._match_details:
            mismatches = evaluator._match_details.get("mismatches", [])
            if mismatches:
                print(f"Mismatches:       {mismatches}")
        print("-" * 80)

async def run_scenario(scenario: TaskScenario) -> dict:
    # Initialize the IKEA evaluator with ground truth URL(s)
    evaluator = IkeaUrlMatch(gt_url=scenario.gt_url)
    reporter = ResultReporter()

    print(f"\n{'='*60}\nTASK: {scenario.task_prompt}\n{'='*60}")
    print(f"Expected URL(s):")
    for u in scenario.gt_url:
        print(f"  → {u}")
    input("Press ENTER to launch browser...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-US", timezone_id=scenario.timezone)

        # Anti-detection
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")

        await asyncio.to_thread(input, "\nNavigate and press ENTER when you've completed the task... ")

        try:
            # Grab the active tab's URL for verification
            active_page = context.pages[-1]
            final_url = active_page.url
            print(f"\n[SYSTEM] Verifying final URL: {final_url[:100]}...")

            # IkeaUrlMatch uses update(url=...) — pass the final browser URL
            await evaluator.update(url=final_url)
        except Exception as e:
            print(f"\n[ERROR] Failed to capture URL: {e}")

        result = await evaluator.compute()

        # Also get detailed result for debugging
        detailed = await evaluator.compute_detailed()

        await context.close()
        await browser.close()

    reporter.print_result(detailed, evaluator, scenario)
    return result

async def main():
    logger.remove()
    logger.add(sys.stderr, format="<level>{message}</level>", level="INFO")

    print("\n" + "=" * 60)
    print("  IKEA US — Demo Verifier")
    print("  Verify URL-based navigation tasks on ikea.com/us/en/")
    print("=" * 60 + "\n")

    for i, s in enumerate(SCENARIOS, 1):
        print(f"[{i}] {s.name}")
        print(f"    {s.description}\n")

    choice = input("Select scenario index: ")
    if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
        await run_scenario(SCENARIOS[int(choice) - 1])
    else:
        print("Invalid selection.")

if __name__ == "__main__":
    asyncio.run(main())
