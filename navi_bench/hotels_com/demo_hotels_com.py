#!/usr/bin/env python
import asyncio
import sys
from dataclasses import dataclass, field
from playwright.async_api import async_playwright
from loguru import logger

# Import the Hotels.com evaluator
from hotels_com_url_match import HotelsComUrlMatch

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
    timezone: str = "America/New_York"

# Demo Scenarios for Hotels.com US
SCENARIOS: list[TaskScenario] = [
    TaskScenario(
        task_id="hotels_com/search/ny_cheap",
        name="New York Hotels — Lowest Price",
        description="Search for New York hotels and sort by lowest price.",
        url="https://www.hotels.com/",
        task_prompt=(
            "Search for hotels in New York on Hotels.com and sort by lowest price."
        ),
        gt_url=[
            "https://www.hotels.com/Hotel-Search?destination=New%20York&sort=PRICE_LOW_TO_HIGH"
        ],
    ),
    TaskScenario(
        task_id="hotels_com/search/miami_5star_pool",
        name="Miami 5-Star with Pool",
        description="Search for 5-star hotels in Miami with a pool.",
        url="https://www.hotels.com/",
        task_prompt=(
            "Find 5-star hotels in Miami with a pool on Hotels.com."
        ),
        gt_url=[
            "https://www.hotels.com/Hotel-Search?destination=Miami&f-star-rating=5&f-amenities=POOL"
        ],
    ),
    TaskScenario(
        task_id="hotels_com/search/chicago_family",
        name="Chicago Family Trip (2 Adults, 2 Kids)",
        description="Search for a room in Chicago for 2 adults and 2 kids (ages 5 and 10).",
        url="https://www.hotels.com/",
        task_prompt=(
            "Search for a hotel in Chicago for 2 adults and 2 children (ages 5 and 10) on Hotels.com."
        ),
        gt_url=[
            "https://www.hotels.com/Hotel-Search?destination=Chicago&adults=2&rooms=1&children=1_5,1_10"
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
    evaluator = HotelsComUrlMatch(gt_url=scenario.gt_url)
    reporter = ResultReporter()
    
    print(f"\n{'='*60}\nTASK: {scenario.task_prompt}\n{'='*60}")
    print(f"Expected URL(s):")
    for u in scenario.gt_url:
        print(f"  → {u}")
    input("Press ENTER to launch browser...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-US", timezone_id=scenario.timezone)
        
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        page = await context.new_page()
        
        await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")
            
        await asyncio.to_thread(input, "\nNavigate and press ENTER when you've completed the task... ")
        
        try:
            active_page = context.pages[-1]
            final_url = active_page.url
            print(f"\n[SYSTEM] Verifying final URL: {final_url[:100]}...")
            
            await evaluator.update(url=final_url)
        except Exception as e:
            print(f"\n[ERROR] Failed to capture URL: {e}")
            
        result = await evaluator.compute()
        
        detailed = await evaluator.compute_detailed()
        
        await context.close()
        await browser.close()
    
    reporter.print_result(detailed, evaluator, scenario)
    return result

async def main():
    logger.remove()
    logger.add(sys.stderr, format="<level>{message}</level>", level="INFO")
    
    print("\n" + "=" * 60)
    print("  Hotels.com US — Demo Verifier")
    print("  Verify URL-based navigation tasks on hotels.com")
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
