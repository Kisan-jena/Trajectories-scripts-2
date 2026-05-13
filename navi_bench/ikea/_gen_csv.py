"""Generate ikea_benchmark_tasks.csv with 70 hard tasks."""
import csv, json, os

HEADER = [
    "task_id","task_generation_config_json","env","domain",
    "l1_category","l2_category","suggested_difficulty",
    "suggested_hint","suggested_max_steps","suggested_split","metadata_json",
]

TARGET = "navi_bench.ikea.ikea_url_match.generate_task_config"
HINT = "On IKEA US, use the search bar or navigate to a category page, then apply sidebar filters (Color, Price, Sort). Filters encode as filters=f-type:value in the URL."
URL = "https://www.ikea.com/us/en/"
LOC = "United States"
TZ = "America/Los_Angeles"

def row(tid, cat2, task, gt_urls):
    cfg = {
        "_target_": TARGET, "task": task, "gt_url": gt_urls,
        "location": LOC, "timezone": TZ, "url": URL,
        "timestamp": None, "values": {},
    }
    return [tid, json.dumps(cfg), "real", "ikea", "e_commerce", cat2, "hard", HINT, 50, "validation", "null"]

tasks = []

# --- search_navigation (0-9): keyword search tasks ---
tasks.append(row("ikea/search_nav/0","search_navigation","Search for desks on IKEA US and report the search results URL.",["https://www.ikea.com/us/en/search/?q=desk"]))
tasks.append(row("ikea/search_nav/1","search_navigation","I need a new bookshelf. Search for bookshelves on IKEA US. Report the URL.",["https://www.ikea.com/us/en/search/?q=bookshelf"]))
tasks.append(row("ikea/search_nav/2","search_navigation","Search for sofas on IKEA US. Report the search results URL.",["https://www.ikea.com/us/en/search/?q=sofa"]))
tasks.append(row("ikea/search_nav/3","search_navigation","I'm looking for a bed frame. Search for bed frames on IKEA. Report URL.",["https://www.ikea.com/us/en/search/?q=bed+frame","https://www.ikea.com/us/en/search/?q=bed%20frame"]))
tasks.append(row("ikea/search_nav/4","search_navigation","Search for dining tables on IKEA US. Report the URL.",["https://www.ikea.com/us/en/search/?q=dining+table","https://www.ikea.com/us/en/search/?q=dining%20table"]))
tasks.append(row("ikea/search_nav/5","search_navigation","I want to find nightstands on IKEA. Search for them and report URL.",["https://www.ikea.com/us/en/search/?q=nightstand"]))
tasks.append(row("ikea/search_nav/6","search_navigation","Search for office chairs on IKEA US. Report the search URL.",["https://www.ikea.com/us/en/search/?q=office+chair","https://www.ikea.com/us/en/search/?q=office%20chair"]))
tasks.append(row("ikea/search_nav/7","search_navigation","I need a wardrobe. Search for wardrobes on IKEA US and report URL.",["https://www.ikea.com/us/en/search/?q=wardrobe"]))
tasks.append(row("ikea/search_nav/8","search_navigation","Search for kitchen cabinets on IKEA. Report URL.",["https://www.ikea.com/us/en/search/?q=kitchen+cabinet","https://www.ikea.com/us/en/search/?q=kitchen%20cabinet"]))
tasks.append(row("ikea/search_nav/9","search_navigation","I want curtains. Search for curtains on IKEA US and report the URL.",["https://www.ikea.com/us/en/search/?q=curtains"]))

# --- category_navigation (10-19): browse to category pages ---
tasks.append(row("ikea/category_nav/0","category_navigation","Navigate to the Desks category page on IKEA US. Report the URL.",["https://www.ikea.com/us/en/cat/desks-20649/"]))
tasks.append(row("ikea/category_nav/1","category_navigation","Find the Sofas category page on IKEA US and report the URL.",["https://www.ikea.com/us/en/cat/sofas-fu003/"]))
tasks.append(row("ikea/category_nav/2","category_navigation","Navigate to the Beds category on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/beds-bm003/"]))
tasks.append(row("ikea/category_nav/3","category_navigation","Find the Bookcases & Shelving Units category on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/bookcases-shelving-units-10382/"]))
tasks.append(row("ikea/category_nav/4","category_navigation","Navigate to the Wardrobes category on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/wardrobes-19053/"]))
tasks.append(row("ikea/category_nav/5","category_navigation","Find the Dining Tables category page on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/dining-tables-21825/"]))
tasks.append(row("ikea/category_nav/6","category_navigation","Navigate to the Chairs category on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/chairs-fu002/"]))
tasks.append(row("ikea/category_nav/7","category_navigation","Find the Dressers & Chests of Drawers category on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/dressers-chests-of-drawers-20656/"]))
tasks.append(row("ikea/category_nav/8","category_navigation","Navigate to the TV & Media Furniture category on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/tv-media-furniture-10475/"]))
tasks.append(row("ikea/category_nav/9","category_navigation","Find the Mattresses category on IKEA US. Report URL.",["https://www.ikea.com/us/en/cat/mattresses-bm002/"]))

# --- color_filter (20-29): search/category + color ---
tasks.append(row("ikea/color_filter/0","color_filter","Search for white desks on IKEA US. Report the URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156"]))
tasks.append(row("ikea/color_filter/1","color_filter","Find black sofas on IKEA US. Search and apply the black color filter. Report URL.",["https://www.ikea.com/us/en/search/?q=sofa&filters=f-colors:10005"]))
tasks.append(row("ikea/color_filter/2","color_filter","I want a gray bed frame. Search for bed frames on IKEA and filter by gray. Report URL.",["https://www.ikea.com/us/en/search/?q=bed+frame&filters=f-colors:10008","https://www.ikea.com/us/en/search/?q=bed%20frame&filters=f-colors:10008"]))
tasks.append(row("ikea/color_filter/3","color_filter","Navigate to the Desks category on IKEA and filter by white. Report URL.",["https://www.ikea.com/us/en/cat/desks-20649/?filters=f-colors:10156"]))
tasks.append(row("ikea/color_filter/4","color_filter","Find beige sofas in the Sofas category on IKEA. Report URL.",["https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10003"]))
tasks.append(row("ikea/color_filter/5","color_filter","Search for blue curtains on IKEA US. Report URL.",["https://www.ikea.com/us/en/search/?q=curtains&filters=f-colors:10006"]))
tasks.append(row("ikea/color_filter/6","color_filter","Find brown bookshelves on IKEA US. Search and filter by brown. Report URL.",["https://www.ikea.com/us/en/search/?q=bookshelf&filters=f-colors:10017"]))
tasks.append(row("ikea/color_filter/7","color_filter","I want green kitchen storage. Search on IKEA and filter by green. Report URL.",["https://www.ikea.com/us/en/search/?q=kitchen+storage&filters=f-colors:10011","https://www.ikea.com/us/en/search/?q=kitchen%20storage&filters=f-colors:10011"]))
tasks.append(row("ikea/color_filter/8","color_filter","Find red rugs on IKEA US. Report the search URL with the red filter.",["https://www.ikea.com/us/en/search/?q=rug&filters=f-colors:10013"]))
tasks.append(row("ikea/color_filter/9","color_filter","Search for pink cushions on IKEA US. Apply the pink color filter. Report URL.",["https://www.ikea.com/us/en/search/?q=cushion&filters=f-colors:10012"]))

# --- sort_selection (30-39): search/category + sort ---
tasks.append(row("ikea/sort/0","sort_selection","Search for desks on IKEA US and sort by lowest price. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/sort/1","sort_selection","Find sofas on IKEA sorted by highest price first. Report URL.",["https://www.ikea.com/us/en/search/?q=sofa&sort=PRICE_HIGH_TO_LOW"]))
tasks.append(row("ikea/sort/2","sort_selection","Search for bookshelves on IKEA and sort by newest. Report URL.",["https://www.ikea.com/us/en/search/?q=bookshelf&sort=NEWEST"]))
tasks.append(row("ikea/sort/3","sort_selection","Navigate to the Sofas category on IKEA and sort by lowest price. Report URL.",["https://www.ikea.com/us/en/cat/sofas-fu003/?sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/sort/4","sort_selection","Browse the Desks category on IKEA, sorted by customer rating. Report URL.",["https://www.ikea.com/us/en/cat/desks-20649/?sort=CUSTOMER_RATING"]))
tasks.append(row("ikea/sort/5","sort_selection","Search for dining tables on IKEA and sort by name. Report URL.",["https://www.ikea.com/us/en/search/?q=dining+table&sort=NAME_ASCENDING","https://www.ikea.com/us/en/search/?q=dining%20table&sort=NAME_ASCENDING"]))
tasks.append(row("ikea/sort/6","sort_selection","Find office chairs on IKEA sorted by most popular. Report URL.",["https://www.ikea.com/us/en/search/?q=office+chair&sort=MOST_POPULAR","https://www.ikea.com/us/en/search/?q=office%20chair&sort=MOST_POPULAR"]))
tasks.append(row("ikea/sort/7","sort_selection","Navigate to the Beds category on IKEA and sort by newest. Report URL.",["https://www.ikea.com/us/en/cat/beds-bm003/?sort=NEWEST"]))
tasks.append(row("ikea/sort/8","sort_selection","Search for wardrobes on IKEA, sort cheapest first. Report URL.",["https://www.ikea.com/us/en/search/?q=wardrobe&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/sort/9","sort_selection","Browse Dining Tables category on IKEA sorted by highest price. Report URL.",["https://www.ikea.com/us/en/cat/dining-tables-21825/?sort=PRICE_HIGH_TO_LOW"]))

# --- red_herring (40-49): narrative distractors ---
tasks.append(row("ikea/red_herring/0","red_herring","I just moved to a new apartment in Brooklyn — the living room is 12x15 feet and has great natural light. I need a white desk for my home office corner. Search on IKEA. The apartment dimensions don't matter for the search. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156"]))
tasks.append(row("ikea/red_herring/1","red_herring","My interior designer recommended the KALLAX series, but I actually want to see all bookshelves sorted by price, cheapest first. The series name doesn't filter in the search URL. Search IKEA for bookshelves, sort by lowest price. Report URL.",["https://www.ikea.com/us/en/search/?q=bookshelf&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/red_herring/2","red_herring","We're renovating our kitchen — new countertops, backsplash, and flooring. But right now I just need black dining chairs. The renovation details are irrelevant. Search IKEA for dining chairs, filter by black. Report URL.",["https://www.ikea.com/us/en/search/?q=dining+chair&filters=f-colors:10005","https://www.ikea.com/us/en/search/?q=dining%20chair&filters=f-colors:10005"]))
tasks.append(row("ikea/red_herring/3","red_herring","My friend bought the MALM dresser for $179 and loves it. I want to browse ALL dressers on IKEA sorted by lowest price — not just MALM. Go to the Dressers category, sort cheapest first. Report URL.",["https://www.ikea.com/us/en/cat/dressers-chests-of-drawers-20656/?sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/red_herring/4","red_herring","I've been comparing IKEA and Wayfair for weeks. IKEA has better prices overall. Just search for gray sofas on IKEA US. The Wayfair comparison doesn't affect the search. Report URL.",["https://www.ikea.com/us/en/search/?q=sofa&filters=f-colors:10008"]))
tasks.append(row("ikea/red_herring/5","red_herring","The delivery fee to my ZIP code is $49 flat rate, which is reasonable. I need a brown coffee table. Delivery fees aren't URL filters. Search IKEA for coffee tables, filter brown. Report URL.",["https://www.ikea.com/us/en/search/?q=coffee+table&filters=f-colors:10017","https://www.ikea.com/us/en/search/?q=coffee%20table&filters=f-colors:10017"]))
tasks.append(row("ikea/red_herring/6","red_herring","I have a 10% IKEA Family discount code that expires next week. Need to find a bed frame before it expires. Search for bed frames sorted by newest. The discount code is irrelevant to the search. Report URL.",["https://www.ikea.com/us/en/search/?q=bed+frame&sort=NEWEST","https://www.ikea.com/us/en/search/?q=bed%20frame&sort=NEWEST"]))
tasks.append(row("ikea/red_herring/7","red_herring","My roommate already bought the BILLY bookcase in white. I want a different one. Just show me all white bookcases in the Bookcases category — I'll pick something else. BILLY doesn't filter the URL. Report URL.",["https://www.ikea.com/us/en/cat/bookcases-shelving-units-10382/?filters=f-colors:10156"]))
tasks.append(row("ikea/red_herring/8","red_herring","The assembly time for most IKEA desks is 1-2 hours according to reviews. That's fine with me. I just need to search for desks sorted by customer rating. Assembly time isn't a filter. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&sort=CUSTOMER_RATING"]))
tasks.append(row("ikea/red_herring/9","red_herring","I measured my bedroom wall and it's 8 feet wide. I need a wardrobe that fits. The wall measurement isn't a URL filter. Just browse the Wardrobes category on IKEA sorted by cheapest. Report URL.",["https://www.ikea.com/us/en/cat/wardrobes-19053/?sort=PRICE_LOW_TO_HIGH"]))

# --- multi_filter (50-59): 3+ filters ---
tasks.append(row("ikea/multi_filter/0","multi_filter","Search for white desks on IKEA US, sorted by lowest price. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/multi_filter/1","multi_filter","Find black sofas on IKEA, sorted by newest. Report URL.",["https://www.ikea.com/us/en/search/?q=sofa&filters=f-colors:10005&sort=NEWEST"]))
tasks.append(row("ikea/multi_filter/2","multi_filter","Search for gray bed frames on IKEA, sorted by customer rating. Report URL.",["https://www.ikea.com/us/en/search/?q=bed+frame&filters=f-colors:10008&sort=CUSTOMER_RATING","https://www.ikea.com/us/en/search/?q=bed%20frame&filters=f-colors:10008&sort=CUSTOMER_RATING"]))
tasks.append(row("ikea/multi_filter/3","multi_filter","Browse white desks in the Desks category on IKEA, cheapest first. Report URL.",["https://www.ikea.com/us/en/cat/desks-20649/?filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/multi_filter/4","multi_filter","Find beige sofas in the Sofas category, sorted by most popular. Report URL.",["https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10003&sort=MOST_POPULAR"]))
tasks.append(row("ikea/multi_filter/5","multi_filter","Search for blue curtains on IKEA, sorted by lowest price. Report URL.",["https://www.ikea.com/us/en/search/?q=curtains&filters=f-colors:10006&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/multi_filter/6","multi_filter","Find brown bookshelves on IKEA sorted by highest price. Report URL.",["https://www.ikea.com/us/en/search/?q=bookshelf&filters=f-colors:10017&sort=PRICE_HIGH_TO_LOW"]))
tasks.append(row("ikea/multi_filter/7","multi_filter","Search for desks under $100 on IKEA, sorted by lowest price. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-price-buckets:PRICE_0_10000&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/multi_filter/8","multi_filter","Find white desks under $100 on IKEA US. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156,f-price-buckets:PRICE_0_10000"]))
tasks.append(row("ikea/multi_filter/9","multi_filter","Browse the Dining Tables category with gray filter, sorted by customer rating. Report URL.",["https://www.ikea.com/us/en/cat/dining-tables-21825/?filters=f-colors:10008&sort=CUSTOMER_RATING"]))

# --- ultra_hard (60-69): narrative + arithmetic + multi-filter ---
tasks.append(row("ikea/ultra_hard/0","ultra_hard","I have a $500 budget for furnishing my home office. I need a white desk — the desk alone should be under $100 so I have money left for a chair and accessories. Search IKEA for desks, filter white and under $100, sort cheapest. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156,f-price-buckets:PRICE_0_10000&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/ultra_hard/1","ultra_hard","My living room needs a sofa — I want something modern in gray. My wife prefers beige but I'm searching for gray. Sort by customer rating to find the best-reviewed one. Don't search for beige. Report URL.",["https://www.ikea.com/us/en/search/?q=sofa&filters=f-colors:10008&sort=CUSTOMER_RATING"]))
tasks.append(row("ikea/ultra_hard/2","ultra_hard","I got a $200 IKEA gift card for my birthday and another $150 from my parents — that's $350 total. I want a black dining table, sorted by cheapest to find one in budget. Search IKEA. Report URL.",["https://www.ikea.com/us/en/search/?q=dining+table&filters=f-colors:10005&sort=PRICE_LOW_TO_HIGH","https://www.ikea.com/us/en/search/?q=dining%20table&filters=f-colors:10005&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/ultra_hard/3","ultra_hard","Setting up a nursery — I need white furniture. Start with a white wardrobe. The baby's due date is in 3 months but that's not a filter. Browse the Wardrobes category, filter white, sort cheapest. Report URL.",["https://www.ikea.com/us/en/cat/wardrobes-19053/?filters=f-colors:10156&sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/ultra_hard/4","ultra_hard","Furnishing 3 dorm rooms — each needs a desk under $100. That's $300 total but the per-desk budget is what matters. Search IKEA for desks under $100, sort by most popular to find tried-and-true options. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-price-buckets:PRICE_0_10000&sort=MOST_POPULAR"]))
tasks.append(row("ikea/ultra_hard/5","ultra_hard","My apartment has Scandinavian minimalist design — everything is white and natural wood tones. I need a white bed frame. My designer said HEMNES or MALM but those aren't URL filters. Search for bed frames, filter white, newest first. Report URL.",["https://www.ikea.com/us/en/search/?q=bed+frame&filters=f-colors:10156&sort=NEWEST","https://www.ikea.com/us/en/search/?q=bed%20frame&filters=f-colors:10156&sort=NEWEST"]))
tasks.append(row("ikea/ultra_hard/6","ultra_hard","I saved $100 per month for 8 months — that's $800 for a sofa. I want a beige one from the Sofas category, sorted by highest price first so I can see the premium options in my budget. Report URL.",["https://www.ikea.com/us/en/cat/sofas-fu003/?filters=f-colors:10003&sort=PRICE_HIGH_TO_LOW"]))
tasks.append(row("ikea/ultra_hard/7","ultra_hard","Comparing bookcases for my library. I already have a dark brown one from West Elm. Now I want a brown one from IKEA to match. Browse Bookcases category, filter brown, sort by customer rating. Report URL.",["https://www.ikea.com/us/en/cat/bookcases-shelving-units-10382/?filters=f-colors:10017&sort=CUSTOMER_RATING"]))
tasks.append(row("ikea/ultra_hard/8","ultra_hard","New house, new TV room. I need a TV stand but my budget is tight after buying the TV ($1200) and sound bar ($300). I have $200 left. Browse TV & Media Furniture category sorted cheapest first. Report URL.",["https://www.ikea.com/us/en/cat/tv-media-furniture-10475/?sort=PRICE_LOW_TO_HIGH"]))
tasks.append(row("ikea/ultra_hard/9","ultra_hard","My daughter's going to college and needs a complete room setup. Start with a white desk under $100 from IKEA, sorted by customer rating — she wants one that's easy to assemble. The assembly preference doesn't filter. Report URL.",["https://www.ikea.com/us/en/search/?q=desk&filters=f-colors:10156,f-price-buckets:PRICE_0_10000&sort=CUSTOMER_RATING"]))

out = os.path.join(os.path.dirname(__file__), "ikea_benchmark_tasks.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    for t in tasks:
        w.writerow(t)

print(f"Wrote {len(tasks)} tasks to {out}")
