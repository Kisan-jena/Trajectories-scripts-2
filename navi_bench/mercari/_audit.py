"""Audit the Mercari benchmark CSV for completeness and correctness."""
import csv
import json
import re
import sys

CSV = "navi_bench/mercari/mercari_benchmark_tasks.csv"

rows = list(csv.DictReader(open(CSV, "r", encoding="utf-8")))
print(f"Total tasks: {len(rows)}")
print(f"Columns: {list(rows[0].keys())}")

# Check config structure
cfg = json.loads(rows[0]["task_generation_config_json"])
print(f"Config keys: {sorted(cfg.keys())}")
target_ok = "_target_" in cfg
gt_ok = "gt_url" in cfg and isinstance(cfg["gt_url"], list)
url_ok = "url" in cfg
loc_ok = "location" in cfg
tz_ok = "timezone" in cfg
ts_ok = "timestamp" in cfg
val_ok = "values" in cfg
print(f"_target_: {target_ok}, gt_url(list): {gt_ok}, url: {url_ok}")
print(f"location: {loc_ok}, timezone: {tz_ok}, timestamp: {ts_ok}, values: {val_ok}")

# Category breakdown
cat_counts = {}
for r in rows:
    c = r["l2_category"]
    cat_counts[c] = cat_counts.get(c, 0) + 1
print("\nCategory breakdown:")
for c, n in sorted(cat_counts.items()):
    print(f"  {c}: {n}")

# Unique IDs
ids = [r["task_id"] for r in rows]
print(f"\nUnique IDs: {len(set(ids))}/{len(ids)}")
if len(set(ids)) != len(ids):
    print("  WARNING: Duplicate task IDs found!")

# Validate prices are in cents (>= 100)
issues = []
for i, r in enumerate(rows):
    cfg = json.loads(r["task_generation_config_json"])
    for u in cfg["gt_url"]:
        for param in ["minPrice", "maxPrice"]:
            m = re.search(rf"{param}=(\d+)", u)
            if m and int(m.group(1)) < 100:
                issues.append(f"Row {i} ({r['task_id']}): {param}={m.group(1)} looks like dollars")

if issues:
    print("\nPRICE ISSUES:")
    for x in issues:
        print(f"  {x}")
else:
    print("\nAll prices correct (cents encoding, all >= 100)")

# Check all GT URLs are valid Mercari URLs
bad_urls = []
for i, r in enumerate(rows):
    cfg = json.loads(r["task_generation_config_json"])
    for u in cfg["gt_url"]:
        if "mercari.com" not in u:
            bad_urls.append(f"Row {i}: {u[:60]}")
if bad_urls:
    print("\nBAD URLs:")
    for x in bad_urls:
        print(f"  {x}")
else:
    print("All GT URLs are mercari.com URLs")

# Check all rows have required fields
missing = []
for i, r in enumerate(rows):
    for col in ["task_id", "task_generation_config_json", "env", "domain", "l1_category"]:
        if not r.get(col):
            missing.append(f"Row {i}: missing {col}")
if missing:
    print("\nMISSING FIELDS:")
    for x in missing:
        print(f"  {x}")
else:
    print("All required fields present")

# Compare with FB Marketplace CSV columns
fb_cols = ["task_id","task_generation_config_json","env","domain","l1_category","l2_category","suggested_difficulty","suggested_hint","suggested_max_steps","suggested_split","metadata_json"]
our_cols = list(rows[0].keys())
if our_cols == fb_cols:
    print("Column order matches FB Marketplace CSV ✓")
else:
    print(f"Column mismatch! Ours: {our_cols}")
    print(f"FB:   {fb_cols}")

print("\n=== AUDIT COMPLETE ===")
