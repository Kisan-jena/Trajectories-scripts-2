"""
=================================================================
  Realtor.com NaviBench Demo — How to run the benchmark verifier
=================================================================

This script shows the full pipeline for Realtor.com tasks:
  1. Load tasks from the CSV
  2. Instantiate the task config (resolves task text, user metadata)
  3. Simulate agent URLs (correct, wrong location, missing filter)
  4. Run the verifier to score the agent

Usage:
  cd "c:/Users/HP/Desktop/autonex official"
  python -m navi_bench.realtor.demo_realtor_verifier
=================================================================
"""
import asyncio
import csv
import json
import os

from navi_bench.base import instantiate


def main():
    # ─────────────────────────────────────────────────
    # STEP 1: Load a task from the CSV
    # ─────────────────────────────────────────────────
    # CSV lives next to this script in the realtor folder
    csv_path = os.path.join(os.path.dirname(__file__), "realtor_updated_tasks.csv")
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    row = rows[0]  # First task: for_sale_basic/0 (SF, 3+ beds, under $1M)
    print("=" * 70)
    print("  STEP 1: Raw CSV row")
    print("=" * 70)
    print(f"  task_id:    {row['task_id']}")
    print(f"  domain:     {row['domain']}")
    print(f"  difficulty: {row['suggested_difficulty']}")
    print(f"  category:   {row['l2_category']}")
    print()

    # ─────────────────────────────────────────────────
    # STEP 2: Parse the task config JSON and instantiate
    # ─────────────────────────────────────────────────
    config = json.loads(row["task_generation_config_json"])
    print("=" * 70)
    print("  STEP 2: Raw task config")
    print("=" * 70)
    print(f"  _target_:     {config['_target_']}")
    print(f"  Task:         {config['task']}")
    print(f"  Location:     {config['location']}")
    print(f"  Timezone:     {config['timezone']}")
    print(f"  Start URL:    {config['url']}")
    print(f"  GT URLs:")
    for group in config["gt_urls"]:
        for url in group:
            print(f"    {url}")
    print()

    # instantiate() calls generate_task_config() which:
    #   - Creates UserMetadata with location/timezone
    #   - Builds eval_config pointing to RealtorUrlMatch
    task_config = instantiate(config)

    print("=" * 70)
    print("  STEP 3: Resolved task config")
    print("=" * 70)
    print(f"  Rendered task:  {task_config.task}")
    print(f"  Start URL:      {task_config.url}")
    print(f"  User location:  {task_config.user_metadata.location}")
    print(f"  User timezone:  {task_config.user_metadata.timezone}")
    print(f"  Eval target:    {task_config.eval_config['_target_']}")
    print(f"  GT URLs:")
    for group in task_config.eval_config["gt_urls"]:
        for url in group:
            print(f"    {url}")
    print()

    # ─────────────────────────────────────────────────
    # STEP 4: Simulate AI agents navigating to URLs
    # ─────────────────────────────────────────────────
    gt_url = task_config.eval_config["gt_urls"][0][0]

    test_cases = [
        ("[PASS] Exact match (agent got it right)",
         gt_url),
        ("[PASS] Filter order different (should still match)",
         "https://www.realtor.com/realestateandhomes-search/San-Francisco_CA/price-na-1000000/beds-3"),
        ("[FAIL] Wrong city (agent searched in Los Angeles)",
         gt_url.replace("San-Francisco_CA", "Los-Angeles_CA")),
        ("[FAIL] Missing filter (agent forgot beds-3)",
         gt_url.replace("/beds-3", "")),
        ("[FAIL] Wrong price range (agent used different price)",
         gt_url.replace("price-na-1000000", "price-na-2000000")),
    ]

    print("=" * 70)
    print("  STEP 4: Running the verifier against agent URLs")
    print("=" * 70)

    async def run_verifier():
        for label, agent_url in test_cases:
            print(f"\n  --- {label} ---")
            print(f"  Agent URL: {agent_url}")

            # Create the verifier from eval_config
            verifier = instantiate(task_config.eval_config)

            # Feed the agent's URL to the verifier
            await verifier.update(url=agent_url)

            # Compute the score (1.0 = match, 0.0 = no match)
            result = await verifier.compute()
            score = result.score
            print(f"  Score:     {score}  {'>> PASS' if score == 1.0 else '>> FAIL'}")

    asyncio.run(run_verifier())

    # ─────────────────────────────────────────────────
    # STEP 5: Test across multiple task categories
    # ─────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  STEP 5: Testing across different task categories")
    print("=" * 70)

    # Pick one task from each category for a broader demo
    categories_seen = set()
    sample_rows = []
    for r in rows:
        cat = r["l2_category"]
        if cat not in categories_seen:
            categories_seen.add(cat)
            sample_rows.append(r)

    async def run_category_tests():
        for r in sample_rows:
            cfg = json.loads(r["task_generation_config_json"])
            tc = instantiate(cfg)
            gt = tc.eval_config["gt_urls"][0][0]

            # Test exact match for each category
            verifier = instantiate(tc.eval_config)
            await verifier.update(url=gt)
            result = await verifier.compute()

            status = "PASS" if result.score == 1.0 else "FAIL"
            print(f"\n  [{status}] {r['l2_category']} | {r['task_id']}")
            print(f"    Task: {cfg['task'][:80]}...")
            print(f"    GT URL matched with score: {result.score}")

    asyncio.run(run_category_tests())

    print()
    print("=" * 70)
    print("  DONE! This is how the Realtor.com benchmark works end-to-end.")
    print("=" * 70)


if __name__ == "__main__":
    main()
