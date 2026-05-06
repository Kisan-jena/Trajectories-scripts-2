"""Generate swappa_benchmark_tasks.csv with 70 hard tasks."""
import csv, json, os

HEADER = [
    "task_id","task_generation_config_json","env","domain",
    "l1_category","l2_category","suggested_difficulty",
    "suggested_hint","suggested_max_steps","suggested_split","metadata_json",
]

TARGET = "navi_bench.swappa.swappa_url_match.generate_task_config"
HINT = "On Swappa, navigate to the correct product page, then use sidebar filters (Condition, Carrier, Storage, Color, Sort). The URL uses path segments for product/carrier and query params for other filters."
URL = "https://swappa.com/"
LOC = "United States"
TZ = "America/Los_Angeles"

def row(tid, cat2, task, gt_urls):
    cfg = {
        "_target_": TARGET, "task": task, "gt_url": gt_urls,
        "location": LOC, "timezone": TZ, "url": URL,
        "timestamp": None, "values": {},
    }
    return [tid, json.dumps(cfg), "real", "swappa", "e_commerce", cat2, "hard", HINT, 50, "validation", "null"]

tasks = []

# --- product_navigation (0-9): navigate to the correct product page ---
tasks.append(row("swappa/product_nav/0","product_navigation","Find the Apple iPhone 15 Pro Max on Swappa. Navigate to its product page and report the URL.",[
    "https://swappa.com/buy/apple-iphone-15-pro-max","https://swappa.com/listings/apple-iphone-15-pro-max"]))
tasks.append(row("swappa/product_nav/1","product_navigation","I want to buy a Samsung Galaxy S24 Ultra. Find it on Swappa and report the product page URL.",[
    "https://swappa.com/buy/samsung-galaxy-s24-ultra","https://swappa.com/listings/samsung-galaxy-s24-ultra"]))
tasks.append(row("swappa/product_nav/2","product_navigation","Navigate to the Google Pixel 8 Pro page on Swappa. Report the URL.",[
    "https://swappa.com/buy/google-pixel-8-pro","https://swappa.com/listings/google-pixel-8-pro"]))
tasks.append(row("swappa/product_nav/3","product_navigation","Find the Apple iPad Pro 12.9 (6th Gen) on Swappa. Report the product page URL.",[
    "https://swappa.com/buy/apple-ipad-pro-12-9-6th-gen"]))
tasks.append(row("swappa/product_nav/4","product_navigation","I'm looking for a MacBook Air M2 on Swappa. Navigate to its page and report the URL.",[
    "https://swappa.com/buy/apple-macbook-air-m2-2022"]))
tasks.append(row("swappa/product_nav/5","product_navigation","Find the Samsung Galaxy Watch 6 on Swappa. Report the product URL.",[
    "https://swappa.com/buy/samsung-galaxy-watch-6"]))
tasks.append(row("swappa/product_nav/6","product_navigation","Navigate to the Apple iPhone 14 page on Swappa. Report the URL.",[
    "https://swappa.com/buy/apple-iphone-14","https://swappa.com/listings/apple-iphone-14"]))
tasks.append(row("swappa/product_nav/7","product_navigation","Find the Samsung Galaxy S23 on Swappa and report the product page URL.",[
    "https://swappa.com/buy/samsung-galaxy-s23","https://swappa.com/listings/samsung-galaxy-s23"]))
tasks.append(row("swappa/product_nav/8","product_navigation","I want to buy AirPods Pro (2nd Gen). Find them on Swappa and report the URL.",[
    "https://swappa.com/buy/apple-airpods-pro-2nd-gen"]))
tasks.append(row("swappa/product_nav/9","product_navigation","Navigate to the Nintendo Switch OLED page on Swappa. Report the URL.",[
    "https://swappa.com/buy/nintendo-switch-oled"]))

# --- carrier_selection (10-19): navigate and select carrier ---
tasks.append(row("swappa/carrier/0","carrier_selection","Find unlocked iPhone 15 listings on Swappa. Report the URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=unlocked","https://swappa.com/buy/apple-iphone-15/unlocked"]))
tasks.append(row("swappa/carrier/1","carrier_selection","Show me AT&T Samsung Galaxy S24 listings on Swappa. Report the URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=att"]))
tasks.append(row("swappa/carrier/2","carrier_selection","I need a Verizon iPhone 15 Pro. Find it on Swappa and report the URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro?carrier=verizon"]))
tasks.append(row("swappa/carrier/3","carrier_selection","Show T-Mobile Google Pixel 8 listings on Swappa. Report URL.",[
    "https://swappa.com/listings/google-pixel-8?carrier=tmobile"]))
tasks.append(row("swappa/carrier/4","carrier_selection","Find unlocked Samsung Galaxy S23 Ultra on Swappa. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s23-ultra?carrier=unlocked"]))
tasks.append(row("swappa/carrier/5","carrier_selection","I want an AT&T iPhone 14 Pro Max on Swappa. Navigate there and report the URL.",[
    "https://swappa.com/listings/apple-iphone-14-pro-max?carrier=att"]))
tasks.append(row("swappa/carrier/6","carrier_selection","Find Verizon Samsung Galaxy S24 listings. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=verizon"]))
tasks.append(row("swappa/carrier/7","carrier_selection","Show me Mint Mobile iPhone 15 listings on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=mint-mobile"]))
tasks.append(row("swappa/carrier/8","carrier_selection","Find unlocked Google Pixel 7a on Swappa. Report URL.",[
    "https://swappa.com/listings/google-pixel-7a?carrier=unlocked"]))
tasks.append(row("swappa/carrier/9","carrier_selection","Navigate to US Cellular iPhone 15 listings on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=us-cellular"]))

# --- condition_filter (20-29): navigate + condition ---
tasks.append(row("swappa/condition/0","condition_filter","Find mint condition unlocked iPhone 15 on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint"]))
tasks.append(row("swappa/condition/1","condition_filter","Show me good condition Samsung Galaxy S24 Ultra unlocked listings. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24-ultra?carrier=unlocked&condition=good"]))
tasks.append(row("swappa/condition/2","condition_filter","Find new condition unlocked iPhone 15 Pro Max on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro-max?carrier=unlocked&condition=new"]))
tasks.append(row("swappa/condition/3","condition_filter","I want a fair condition Verizon iPhone 14. Find it on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-14?carrier=verizon&condition=fair"]))
tasks.append(row("swappa/condition/4","condition_filter","Show mint condition AT&T Samsung Galaxy S23 listings. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s23?carrier=att&condition=mint"]))
tasks.append(row("swappa/condition/5","condition_filter","Find good condition unlocked Google Pixel 8 Pro on Swappa. Report URL.",[
    "https://swappa.com/listings/google-pixel-8-pro?carrier=unlocked&condition=good"]))
tasks.append(row("swappa/condition/6","condition_filter","Show me fair condition T-Mobile iPhone 15 listings. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=tmobile&condition=fair"]))
tasks.append(row("swappa/condition/7","condition_filter","Find new condition unlocked Samsung Galaxy S24. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=unlocked&condition=new"]))
tasks.append(row("swappa/condition/8","condition_filter","I want a mint condition unlocked iPhone 14 Pro. Report URL.",[
    "https://swappa.com/listings/apple-iphone-14-pro?carrier=unlocked&condition=mint"]))
tasks.append(row("swappa/condition/9","condition_filter","Show good condition Verizon Google Pixel 8 listings. Report URL.",[
    "https://swappa.com/listings/google-pixel-8?carrier=verizon&condition=good"]))

# --- storage_combos (30-39): carrier + storage ---
tasks.append(row("swappa/storage/0","storage_combo","Find unlocked iPhone 15 with 256GB storage on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&storage=256gb"]))
tasks.append(row("swappa/storage/1","storage_combo","Show me 512GB unlocked iPhone 15 Pro Max listings. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro-max?carrier=unlocked&storage=512gb"]))
tasks.append(row("swappa/storage/2","storage_combo","Find AT&T Samsung Galaxy S24 Ultra with 256GB storage. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24-ultra?carrier=att&storage=256gb"]))
tasks.append(row("swappa/storage/3","storage_combo","Show 128GB unlocked Google Pixel 8 on Swappa. Report URL.",[
    "https://swappa.com/listings/google-pixel-8?carrier=unlocked&storage=128gb"]))
tasks.append(row("swappa/storage/4","storage_combo","Find Verizon iPhone 15 Pro with 1TB storage. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro?carrier=verizon&storage=1tb"]))
tasks.append(row("swappa/storage/5","storage_combo","Show me unlocked Samsung Galaxy S23 with 256GB. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s23?carrier=unlocked&storage=256gb"]))
tasks.append(row("swappa/storage/6","storage_combo","Find T-Mobile iPhone 14 with 128GB storage on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-14?carrier=tmobile&storage=128gb"]))
tasks.append(row("swappa/storage/7","storage_combo","Show 512GB unlocked Samsung Galaxy S24 listings. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=unlocked&storage=512gb"]))
tasks.append(row("swappa/storage/8","storage_combo","Find unlocked iPhone 15 with 128GB storage. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&storage=128gb"]))
tasks.append(row("swappa/storage/9","storage_combo","Show Verizon Google Pixel 8 Pro with 256GB on Swappa. Report URL.",[
    "https://swappa.com/listings/google-pixel-8-pro?carrier=verizon&storage=256gb"]))

# --- red_herring (40-49): irrelevant details mixed in ---
tasks.append(row("swappa/red_herring/0","red_herring","My friend dropped his iPhone in the pool last week — now he needs a replacement. He uses Verizon and wants an iPhone 15 in mint condition. The pool was 8 feet deep but that's irrelevant. Find it on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=verizon&condition=mint"]))
tasks.append(row("swappa/red_herring/1","red_herring","I'm a photographer and need a phone with a great camera — the iPhone 15 Pro Max has a 48MP sensor and 5x optical zoom. But those aren't filters on Swappa. Just find me an unlocked one in good condition with 256GB. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro-max?carrier=unlocked&condition=good&storage=256gb"]))
tasks.append(row("swappa/red_herring/2","red_herring","My Samsung Galaxy S23 screen just cracked. The repair costs $250 but a replacement might be cheaper. I want an unlocked Galaxy S24 in mint condition instead. Don't search for screen repair. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=unlocked&condition=mint"]))
tasks.append(row("swappa/red_herring/3","red_herring","Switching from Android to iPhone. My carrier is AT&T. I want an iPhone 15 Pro with 256GB storage. My old phone was a Pixel 7 but that's not what I'm shopping for. Sort by cheapest first. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro?carrier=att&storage=256gb&sort=price_low"]))
tasks.append(row("swappa/red_herring/4","red_herring","My laptop is overheating and the fans sound like a jet engine. The Geek Squad quoted $180 for cleaning but I'd rather buy a used MacBook Air M2. Just find it on Swappa. Report URL.",[
    "https://swappa.com/buy/apple-macbook-air-m2-2022"]))
tasks.append(row("swappa/red_herring/5","red_herring","I read that the Galaxy S24 Ultra has titanium sides and a built-in S Pen. Cool features but not URL filters. Find me an unlocked one in good condition, sorted cheapest first. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24-ultra?carrier=unlocked&condition=good&sort=price_low"]))
tasks.append(row("swappa/red_herring/6","red_herring","My daughter wants an iPad for school. She needs it for note-taking and drawing — she uses Procreate. Find an Apple iPad Pro 12.9 on Swappa. Report URL.",[
    "https://swappa.com/buy/apple-ipad-pro-12-9-6th-gen"]))
tasks.append(row("swappa/red_herring/7","red_herring","I'm traveling to Japan next month and need an unlocked phone. My current phone is locked to Verizon which won't work abroad. Find an unlocked iPhone 15 in mint condition on Swappa. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint"]))
tasks.append(row("swappa/red_herring/8","red_herring","The new iPhone 17 just came out but it's $1200 — way too expensive. I want to save money and get an iPhone 15 Pro instead. Unlocked, 512GB, good condition. Sort by lowest price. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro?carrier=unlocked&storage=512gb&condition=good&sort=price_low"]))
tasks.append(row("swappa/red_herring/9","red_herring","My gym buddy keeps recommending the Apple Watch Ultra for fitness tracking. He runs ultramarathons. I just want a regular Galaxy Watch 6 from Swappa though. Report URL.",[
    "https://swappa.com/buy/samsung-galaxy-watch-6"]))

# --- multi_filter (50-59): 3+ filters combined ---
tasks.append(row("swappa/multi_filter/0","multi_filter","Find unlocked iPhone 15 on Swappa in mint condition with 128GB storage, sorted by lowest price. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint&storage=128gb&sort=price_low"]))
tasks.append(row("swappa/multi_filter/1","multi_filter","Show me unlocked Samsung Galaxy S24 in good condition, 256GB, sorted by newest. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=unlocked&condition=good&storage=256gb&sort=newest"]))
tasks.append(row("swappa/multi_filter/2","multi_filter","Find AT&T iPhone 15 Pro Max in mint condition with 512GB storage, sorted cheapest first. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro-max?carrier=att&condition=mint&storage=512gb&sort=price_low"]))
tasks.append(row("swappa/multi_filter/3","multi_filter","Show Verizon Samsung Galaxy S23 Ultra, good condition, 256GB, newest first. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s23-ultra?carrier=verizon&condition=good&storage=256gb&sort=newest"]))
tasks.append(row("swappa/multi_filter/4","multi_filter","Find unlocked Google Pixel 8 Pro, new condition, 128GB, cheapest first on Swappa. Report URL.",[
    "https://swappa.com/listings/google-pixel-8-pro?carrier=unlocked&condition=new&storage=128gb&sort=price_low"]))
tasks.append(row("swappa/multi_filter/5","multi_filter","Show unlocked iPhone 14 Pro in fair condition, 256GB, sorted by price high to low. Report URL.",[
    "https://swappa.com/listings/apple-iphone-14-pro?carrier=unlocked&condition=fair&storage=256gb&sort=price_high"]))
tasks.append(row("swappa/multi_filter/6","multi_filter","Find T-Mobile iPhone 15, mint condition, 128GB, black color, cheapest first. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=tmobile&condition=mint&storage=128gb&color=black&sort=price_low"]))
tasks.append(row("swappa/multi_filter/7","multi_filter","Show unlocked Samsung Galaxy S24 Ultra, mint condition, 512GB, newest listings. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24-ultra?carrier=unlocked&condition=mint&storage=512gb&sort=newest"]))
tasks.append(row("swappa/multi_filter/8","multi_filter","Find AT&T Samsung Galaxy S24, good condition, 128GB, sorted cheapest. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=att&condition=good&storage=128gb&sort=price_low"]))
tasks.append(row("swappa/multi_filter/9","multi_filter","Show unlocked iPhone 15 Pro, new condition, 256GB, blue color. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro?carrier=unlocked&condition=new&storage=256gb&color=blue"]))

# --- ultra_hard (60-69): narrative + arithmetic + multi-filter ---
tasks.append(row("swappa/ultra_hard/0","ultra_hard","My old iPhone 13 just sold for $350 on Swappa. I want to use that money to upgrade to an iPhone 15. Unlocked, mint condition, 128GB storage. Sort by cheapest to find one within my $350 budget. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=unlocked&condition=mint&storage=128gb&sort=price_low"]))
tasks.append(row("swappa/ultra_hard/1","ultra_hard","I saved $50/month for 6 months — that's $300 for a Samsung Galaxy S23 Ultra. I want it unlocked, good condition, 256GB. Sort by lowest price to stay in budget. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s23-ultra?carrier=unlocked&condition=good&storage=256gb&sort=price_low"]))
tasks.append(row("swappa/ultra_hard/2","ultra_hard","Birthday money from 3 relatives: grandma $100, aunt $75, uncle $50. Total $225 for an unlocked Google Pixel 8. Good condition, 128GB. Cheapest first. Report URL.",[
    "https://swappa.com/listings/google-pixel-8?carrier=unlocked&condition=good&storage=128gb&sort=price_low"]))
tasks.append(row("swappa/ultra_hard/3","ultra_hard","I need a phone for my mom. She's on AT&T and doesn't need tons of storage — 128GB is fine. She wants an iPhone 15 in at least mint condition. Sort by lowest price. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15?carrier=att&condition=mint&storage=128gb&sort=price_low"]))
tasks.append(row("swappa/ultra_hard/4","ultra_hard","Switching from Verizon to T-Mobile. Need a T-Mobile Samsung Galaxy S24 in mint condition, 256GB. My old Verizon phone doesn't matter. Sort newest first. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=tmobile&condition=mint&storage=256gb&sort=newest"]))
tasks.append(row("swappa/ultra_hard/5","ultra_hard","I want the biggest iPhone with the most storage. That's the iPhone 15 Pro Max with 1TB. Unlocked, new condition, sorted by highest price. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro-max?carrier=unlocked&condition=new&storage=1tb&sort=price_high"]))
tasks.append(row("swappa/ultra_hard/6","ultra_hard","Got a $200 trade-in credit and $150 in cash. Total $350 for a used iPhone 15 Pro. Unlocked, good condition, 256GB. My trade-in was a Pixel 6 but that doesn't affect the search. Cheapest first. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro?carrier=unlocked&condition=good&storage=256gb&sort=price_low"]))
tasks.append(row("swappa/ultra_hard/7","ultra_hard","Company is buying phones for 3 employees. Each gets a Verizon Samsung Galaxy S24 in good condition, 128GB. Sort by lowest price to find the best deal. Report URL for one phone listing page.",[
    "https://swappa.com/listings/samsung-galaxy-s24?carrier=verizon&condition=good&storage=128gb&sort=price_low"]))
tasks.append(row("swappa/ultra_hard/8","ultra_hard","I want a purple iPhone 15 Pro, unlocked, mint condition, 256GB storage. Sort by newest listings. The purple color is called 'Natural Titanium' by Apple but on Swappa it's just purple. Report URL.",[
    "https://swappa.com/listings/apple-iphone-15-pro?carrier=unlocked&condition=mint&storage=256gb&color=purple&sort=newest"]))
tasks.append(row("swappa/ultra_hard/9","ultra_hard","My partner and I each have $250 — total $500 for a Galaxy S24 Ultra. Unlocked, mint condition, 512GB, sorted by cheapest. The Ultra has the S Pen which is nice but not a filter. Report URL.",[
    "https://swappa.com/listings/samsung-galaxy-s24-ultra?carrier=unlocked&condition=mint&storage=512gb&sort=price_low"]))

out = os.path.join(os.path.dirname(__file__), "swappa_benchmark_tasks.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    for t in tasks:
        w.writerow(t)

print(f"Wrote {len(tasks)} tasks to {out}")
