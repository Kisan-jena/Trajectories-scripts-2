#!/usr/bin/env python
import asyncio
import sys
from dataclasses import dataclass, field
from playwright.async_api import async_playwright
from loguru import logger

from kayak_info_gathering import KayakInfoGathering

@dataclass
class BrowserConfig:
    headless: bool = False
    viewport_width: int = 1366
    viewport_height: int = 768
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    locale: str = "en-IN"
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
    queries: list
    location: str = "India"
    timezone: str = "Asia/Kolkata"

SCENARIOS: list[TaskScenario] = [
    TaskScenario(
        task_id="kayak/flights/del_bom_budget",
        name="Delhi to Mumbai - Under ₹5000",
        description="Search for a budget flight between DEL and BOM.",
        url="https://www.kayak.co.in/",
        task_prompt=(
            "Find a flight from New Delhi (DEL) to Mumbai (BOM). The ticket must cost less than ₹5000."
        ),
        queries=[[{
            "origins": ["del"], 
            "destinations": ["bom"],
            "max_price": 5000.0,
        }]]
    ),
    TaskScenario(
        task_id="kayak/flights/blr_del_direct_indigo",
        name="Bangalore to Delhi - Direct IndiGo",
        description="Search specifically for a direct IndiGo flight.",
        url="https://www.kayak.co.in/",
        task_prompt=(
            "Search for a direct IndiGo flight from Bangalore (BLR) to New Delhi (DEL)."
        ),
        queries=[[{
            "origins": ["blr"], 
            "destinations": ["del"],
            "airlines": ["indigo"],
            "require_direct": True,
        }]]
    ),
    TaskScenario(
        task_id="kayak/hotels/seattle_premium_score_price",
        name="Seattle Premium Hotels - Score 8.3+ Over $224",
        description=(
            "Search for premium hotel options in Seattle with "
            "at least 3 stars, a review score of 8.3 or higher, "
            "and prices above $224."
        ),
        url="https://www.kayak.com/",
        task_prompt=(
            "Look for 3-star or higher hotels in Seattle for "
            "upcoming Monday with a score of at least 8.3 "
            "that cost over $224. "
            "If hotel options are found, respond with "
            "'Yes, there is at least one option' and the price. "
            "If no options are found, respond with exactly: "
            "'No options found'."
        ),
        queries=[
            [
                {
                    "cities": ["seattle"],
                    "min_stars": 3,
                    "min_score": 8.3,
                    "min_price": 224.0,
                }
            ]
        ]
    )
]

class ResultReporter:
    @staticmethod
    def print_result(result, evaluator, scenario) -> None:
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)
        
        score_pct = result.score * 100
        status = "✅ PASS" if result.score >= 1.0 else "⚠️ PARTIAL" if result.score > 0 else "❌ FAIL"
        
        print(f"Status:           {status}")
        print(f"Score:            {score_pct:.1f}%")
        print(f"Queries Matched:  {result.n_covered}/{result.n_queries}")
        print("-" * 80)

async def run_scenario(scenario: TaskScenario) -> dict:
    evaluator = KayakInfoGathering(queries=scenario.queries)
    reporter = ResultReporter()
    
    print(f"\n{'='*60}\nTASK: {scenario.task_prompt}\n{'='*60}")
    input("Press ENTER to launch browser...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-IN", timezone_id=scenario.timezone)
        
        # Critical for Kayak evasion
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        page = await context.new_page()
        evaluator.attach_to_context(context)
        
        await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")
            
        await asyncio.to_thread(input, "\nNavigate and press ENTER when you've completed the task... ")
        
        # --- THE FIX IS HERE ---
        try:
            # Playwright keeps track of all open tabs. context.pages[-1] grabs the most recent/active one!
            active_page = context.pages[-1]
            print(f"\n[SYSTEM] Running final scrape on active tab: {active_page.url[:80]}...")
            await evaluator.update(page=active_page)
        except Exception as e:
            print(f"\n[ERROR] Failed to scrape active page: {e}")
        # ------------------------
            
        result = await evaluator.compute()
        await context.close()
        await browser.close()
    
    reporter.print_result(result, evaluator, scenario) 
    return result

async def main():
    logger.remove()
    logger.add(sys.stderr, format="<level>{message}</level>", level="INFO")
    for i, s in enumerate(SCENARIOS, 1): print(f"[{i}] {s.name}")
    choice = input("\nSelect scenario index: ")
    if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
        await run_scenario(SCENARIOS[int(choice) - 1])

if __name__ == "__main__":
    asyncio.run(main())