#!/usr/bin/env python
import asyncio
import sys
from dataclasses import dataclass, field
from playwright.async_api import async_playwright
from loguru import logger

# Import the Momondo evaluator
from momondo_info_gathering import MomondoInfoGathering

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
    queries: list
    location: str = "United States"
    timezone: str = "America/New_York"

# Demo Scenarios for US Market (momondo.com)
SCENARIOS: list[TaskScenario] = [
    TaskScenario(
        task_id="momondo/flights/jfk_lax_budget",
        name="New York to Los Angeles — Under $400",
        description="Search for a budget flight between JFK and LAX.",
        url="https://www.momondo.com/",
        task_prompt=(
            "Find a flight from New York (JFK) to Los Angeles (LAX). The ticket must cost less than $400."
        ),
        queries=[[{
            "origins": ["jfk"], 
            "destinations": ["lax"],
            "max_price": 400.0,
        }]]
    ),
    TaskScenario(
        task_id="momondo/flights/ord_mia_direct_united",
        name="Chicago to Miami — Direct United Airlines",
        description="Search specifically for a direct United Airlines flight.",
        url="https://www.momondo.com/",
        task_prompt=(
            "Search for a direct United Airlines flight from Chicago (ORD) to Miami (MIA)."
        ),
        queries=[[{
            "origins": ["ord"], 
            "destinations": ["mia"],
            "airlines": ["united"],
            "require_direct": True,
        }]]
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
    # Initialize the Momondo evaluator
    evaluator = MomondoInfoGathering(queries=scenario.queries)
    reporter = ResultReporter()
    
    print(f"\n{'='*60}\nTASK: {scenario.task_prompt}\n{'='*60}")
    input("Press ENTER to launch browser...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="en-US", timezone_id=scenario.timezone)
        
        # Critical for Momondo/Kayak evasion
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        page = await context.new_page()
        evaluator.attach_to_context(context)
        
        await page.goto(scenario.url, timeout=60000, wait_until="domcontentloaded")
            
        await asyncio.to_thread(input, "\nNavigate and press ENTER when you've completed the task... ")
        
        try:
            # Playwright keeps track of all open tabs. context.pages[-1] grabs the most recent/active one!
            active_page = context.pages[-1]
            print(f"\n[SYSTEM] Running final scrape on active tab: {active_page.url[:80]}...")
            await evaluator.update(page=active_page)
        except Exception as e:
            print(f"\n[ERROR] Failed to scrape active page: {e}")
            
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