#!/usr/bin/env python
import asyncio
import sys
from dataclasses import dataclass
from playwright.async_api import async_playwright
from loguru import logger

from navi_bench.rome2rio.rome2rio_info_gathering import Rome2RioInfoGathering


# ---------------- CONFIG ----------------

@dataclass
class TaskScenario:
    task_id: str
    name: str
    description: str
    url: str
    task_prompt: str
    queries: list
    timezone: str = "Asia/Kolkata"


SCENARIOS = [
    TaskScenario(
        task_id="fast",
        name="Rome to Florence - Under 2h",
        description="",
        url="https://www.rome2rio.com/",
        task_prompt="Find transport options from Rome to Florence under 2 hours.",
        queries=[[{"max_duration": 120}]]
    ),
    TaskScenario(
        task_id="cheap",
        name="Cheapest route under ₹3000",
        description="",
        url="https://www.rome2rio.com/",
        task_prompt="Find the cheapest route under ₹3000.",
        queries=[[{"max_price": 3000}]]
    )
]


# ---------------- RESULT REPORT ----------------

class ResultReporter:
    @staticmethod
    def print_result(result, evaluator=None, queries=None):
        print("\n" + "=" * 80)
        print("VERIFICATION RESULT")
        print("=" * 80)

        score_pct = result.score * 100
        status = "✅ PASS" if result.score >= 1.0 else "⚠️ PARTIAL" if result.score > 0 else "❌ FAIL"

        print(f"Status:           {status}")
        print(f"Score:            {score_pct:.1f}%")
        print(f"Queries Matched:  {result.n_covered}/{result.n_queries}")
        print("-" * 80)

        # Show all scraped routes and why they matched / didn't
        if evaluator and evaluator._infos:
            print("\nSCRAPED ROUTES:")
            for i, info in enumerate(evaluator._infos, 1):
                mode     = info.get("mode") or info.get("name") or "?"
                price    = f"₹{info.get('min_price')}" if info.get("min_price") is not None else "N/A"
                duration = f"{info.get('duration')} min" if info.get("duration") is not None else "N/A"

                # Check which queries this route satisfies
                matched_qs = []
                if queries:
                    for qi, qgroup in enumerate(queries):
                        for q in qgroup:
                            if evaluator._match(q, info):
                                matched_qs.append(qi + 1)
                                break

                match_tag = f"✓ matches query {matched_qs}" if matched_qs else "✗ no match"
                print(f"  {i}. {mode} | {price} | {duration}  [{match_tag}]")

            # If nothing matched, show what the query required
            if result.n_covered == 0 and queries:
                print("\nWHY DID IT FAIL? Query requirements:")
                for qi, qgroup in enumerate(queries, 1):
                    for q in qgroup:
                        reqs = []
                        if "max_duration" in q: reqs.append(f"duration ≤ {q['max_duration']} min")
                        if "min_duration" in q: reqs.append(f"duration ≥ {q['min_duration']} min")
                        if "max_price"    in q: reqs.append(f"price ≤ ₹{q['max_price']}")
                        if "min_price"   in q: reqs.append(f"price ≥ ₹{q['min_price']}")
                        if "modes"       in q: reqs.append(f"mode in {q['modes']}")
                        print(f"  Query {qi}: {', '.join(reqs) or 'no constraints'}")
        print("=" * 80)


# ---------------- CORE ----------------

async def run_scenario(scenario):
    evaluator = Rome2RioInfoGathering(scenario.queries)
    reporter = ResultReporter()

    print(f"\n{'='*60}\nTASK: {scenario.task_prompt}\n{'='*60}")
    input("Press ENTER to launch browser...")

    async with async_playwright() as p:

        # ✅ Persistent context (KEY FIX)
        context = await p.chromium.launch_persistent_context(
            user_data_dir="rome2rio_user_data",  # saves cookies/session
            headless=False,
            channel="chrome",
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id=scenario.timezone,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        page = context.pages[0] if context.pages else await context.new_page()

        # ✅ Go to site
        await page.goto(scenario.url, wait_until="domcontentloaded")

        print("[SYSTEM] Waiting for page load...")
        await page.wait_for_timeout(5000)

        # ✅ Human-like interaction
        await page.mouse.move(200, 300)
        await page.wait_for_timeout(1000)
        await page.mouse.move(400, 500)
        await page.wait_for_timeout(1000)

        print("\n👉 If Cloudflare appears, solve it once manually.")
        await asyncio.to_thread(
            input,
            "\nNavigate to the page you want, then press ENTER to begin continuous scraping... "
        )

        # ---------------- CONTINUOUS SCRAPING ----------------
        print("\n[SYSTEM] Scraping live. Press ENTER at any time to stop and see the result.\n")

        stop_event = asyncio.Event()

        async def scrape_loop():
            while not stop_event.is_set():
                try:
                    active_page = context.pages[-1]
                    count_results     = await active_page.locator('[data-testid^="trip-search-result"]').count()
                    count_schedules   = await active_page.locator('[aria-labelledby^="schedule-cell-times-"]').count()
                    count_hotels      = await active_page.locator('[data-testid="hotel-list-item"]').count()
                    count_experiences = await active_page.locator('article').count()

                    if count_results > 0 or count_schedules > 0 or count_hotels > 0 or count_experiences > 0:
                        await evaluator.update(page=active_page)
                        result = await evaluator.compute()
                        if result.score >= 1.0:
                            print("\n✅ All target queries covered!")
                            stop_event.set()
                            return
                except Exception as e:
                    print(f"[ERROR] {e}")
                await asyncio.sleep(3)

        async def wait_for_enter():
            await asyncio.to_thread(input, "")
            stop_event.set()

        await asyncio.gather(scrape_loop(), wait_for_enter())

        # Always print final result
        final_result = await evaluator.compute()
        reporter.print_result(final_result, evaluator, scenario.queries)

    return final_result


# ---------------- MAIN ----------------

async def main():
    logger.remove()
    logger.add(sys.stderr, format="<level>{message}</level>", level="INFO")

    for i, s in enumerate(SCENARIOS, 1):
        print(f"[{i}] {s.name}")

    choice = input("\nSelect scenario index: ")

    if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
        await run_scenario(SCENARIOS[int(choice) - 1])


if __name__ == "__main__":
    asyncio.run(main())