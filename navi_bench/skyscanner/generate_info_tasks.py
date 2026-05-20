import csv
import json
import random
from navi_bench.skyscanner.skyscanner_url_match import generate_info_gathering_task_config

def main():
    rows = []
    
    # -------------------------------------------------------------
    # FLIGHTS 
    # (3 Easy, 3 Medium, 17 Hard = 23 Tasks)
    # -------------------------------------------------------------
    def add_flight(tid, diff, origin, dest, task_desc, queries, hint, values=None):
        config = generate_info_gathering_task_config(
            mode="any",
            task=task_desc,
            queries=queries,
            location=origin,
            timezone="UTC",
            values=values
        )
        rows.append({
            "task_id": tid,
            "task_generation_config_json": config.model_dump_json(exclude_none=True),
            "env": "real",
            "domain": "skyscanner",
            "l1_category": "travel",
            "l2_category": "flights",
            "suggested_difficulty": diff,
            "suggested_hint": hint,
            "suggested_split": "validation",
            "suggested_max_steps": "15",
            "metadata_json": "null"
        })

    # Easy Flights (3)
    origins_easy = ["London", "New York", "Paris"]
    dests_easy = ["Berlin", "Miami", "Rome"]
    for i in range(1, 4):
        o, d = origins_easy[i-1], dests_easy[i-1]
        add_flight(
            tid=f"skyscanner/info_gathering/flights/easy/{i}", diff="easy", origin=o, dest=d,
            task_desc=f"Find a direct flight from {o} to {d} on {{dateRange}}. Budget is under $300. Extract exact price.",
            queries=[[{"require_direct": True, "max_price": 300.0}]],
            hint="Use the Direct flights only filter.",
            values={"dateRange": f"in {i*2} days"}
        )

    # Medium Flights (3)
    origins_med = ["Tokyo", "Sydney", "Dubai"]
    dests_med = ["Seoul", "Bali", "Mumbai"]
    airlines_med = ["Japan Airlines", "Qantas", "Emirates"]
    for i in range(1, 4):
        o, d, a = origins_med[i-1], dests_med[i-1], airlines_med[i-1]
        add_flight(
            tid=f"skyscanner/info_gathering/flights/medium/{i}", diff="medium", origin=o, dest=d,
            task_desc=f"Find flights from {o} to {d} on {{dateRange}}. Must fly {a}, max 1 stop, under $950.",
            queries=[[{"max_stops": 1, "airlines": [a], "max_price": 950.0}]],
            hint="Use Airlines and Stops filters.",
            values={"dateRange": f"in {i*4} days"}
        )

    # Hard Flights (17)
    for i in range(1, 18):
        o = random.choice(["Los Angeles", "Frankfurt", "Singapore", "Toronto", "Hong Kong"])
        d = random.choice(["London", "Tokyo", "Paris", "Dubai", "New York"])
        while d == o: d = random.choice(["London", "Tokyo", "Paris", "Dubai", "New York"])
        a = random.choice(["British Airways", "Lufthansa", "Singapore Airlines", "Cathay Pacific", "Delta", "United"])
        add_flight(
            tid=f"skyscanner/info_gathering/flights/hard/{i}", diff="hard", origin=o, dest=d,
            task_desc=f"Search for business class flights from {o} to {d} on {{dateRange}}. Fly with {a}, ensure it is direct, and keep it under $4,200.",
            queries=[[{"require_direct": True, "airlines": [a], "max_price": 4200.0, "cabin_classes": ["business", "biz"]}]],
            hint="Set cabin class, direct stops, specific airline, and ensure price is within budget.",
            values={"dateRange": f"in {i*3} days"}
        )


    # -------------------------------------------------------------
    # HOTELS 
    # (3 Easy, 4 Medium, 16 Hard = 23 Tasks)
    # -------------------------------------------------------------
    def add_hotel(tid, diff, location, task_desc, queries, hint, values=None):
        config = generate_info_gathering_task_config(
            mode="any",
            task=task_desc,
            queries=queries,
            location=location,
            timezone="UTC",
            url="https://www.skyscanner.net/hotels",
            values=values
        )
        rows.append({
            "task_id": tid,
            "task_generation_config_json": config.model_dump_json(exclude_none=True),
            "env": "real",
            "domain": "skyscanner",
            "l1_category": "travel",
            "l2_category": "hotels",
            "suggested_difficulty": diff,
            "suggested_hint": hint,
            "suggested_split": "validation",
            "suggested_max_steps": "15",
            "metadata_json": "null"
        })

    # Easy Hotels (3)
    for i in range(1, 4):
        loc = ["Rome", "Madrid", "Lisbon"][i-1]
        add_hotel(
            tid=f"skyscanner/info_gathering/hotels/easy/{i}", diff="easy", location=loc,
            task_desc=f"Find a hotel in {loc} on {{dateRange}}. Minimum 4 stars, under $180/night.",
            queries=[[{"cities": [loc], "min_stars": 4, "max_price": 180.0}]],
            hint="Set min 4 stars and ensure it's under the max budget.",
            values={"dateRange": f"in {i*5} days"}
        )

    # Medium Hotels (4)
    for i in range(1, 5):
        loc = ["Dubai", "Bangkok", "Istanbul", "Amsterdam"][i-1]
        add_hotel(
            tid=f"skyscanner/info_gathering/hotels/medium/{i}", diff="medium", location=loc,
            task_desc=f"Search for a top-rated hotel in {loc} on {{dateRange}}. Must have a minimum guest rating of 4.5/5, under $350/night.",
            queries=[[{"cities": [loc], "min_score": 4.5, "max_price": 350.0}]],
            hint="Use guest rating filter >= 4.5 or sort by rating.",
            values={"dateRange": f"in {i*2} weeks"}
        )

    # Hard Hotels (16)
    for i in range(1, 17):
        loc = random.choice(["Paris", "London", "Tokyo", "New York", "Singapore", "Sydney"])
        add_hotel(
            tid=f"skyscanner/info_gathering/hotels/hard/{i}", diff="hard", location=loc,
            task_desc=f"Find a 5-star luxury hotel in {loc} checking in on {{dateRange}} for 1 night. Needs an Exceptional guest rating (4.5+/5) and keep it under $950 total.",
            queries=[[{"cities": [loc], "min_stars": 5, "min_score": 4.5, "max_price": 950.0}]],
            hint="Set 5 stars, guest score 4.5+, and enforce price constraints.",
            values={"dateRange": f"in {i+5} days"}
        )


    # -------------------------------------------------------------
    # CAR HIRE
    # (4 Easy, 3 Medium, 17 Hard = 24 Tasks)
    # -------------------------------------------------------------
    def add_car(tid, diff, location, task_desc, queries, hint, values=None):
        config = generate_info_gathering_task_config(
            mode="any",
            task=task_desc,
            queries=queries,
            location=location,
            timezone="UTC",
            url="https://www.skyscanner.net/carhire",
            values=values
        )
        rows.append({
            "task_id": tid,
            "task_generation_config_json": config.model_dump_json(exclude_none=True),
            "env": "real",
            "domain": "skyscanner",
            "l1_category": "travel",
            "l2_category": "carhire",
            "suggested_difficulty": diff,
            "suggested_hint": hint,
            "suggested_split": "validation",
            "suggested_max_steps": "15",
            "metadata_json": "null"
        })

    # Easy Car Hire (4)
    for i in range(1, 5):
        loc = ["Miami", "Los Angeles", "Las Vegas", "Denver"][i-1]
        add_car(
            tid=f"skyscanner/info_gathering/carhire/easy/{i}", diff="easy", location=loc,
            task_desc=f"Find a car hire at {loc} airport on {{dateRange}}. I need an SUV under $300 total.",
            queries=[[{"car_types": ["SUV"], "max_price": 300.0}]],
            hint="Select SUV car type and apply a price budget.",
            values={"dateRange": f"in {i*3} days"}
        )

    # Medium Car Hire (3)
    for i in range(1, 4):
        loc = ["Orlando", "Honolulu", "Cancun"][i-1]
        add_car(
            tid=f"skyscanner/info_gathering/carhire/medium/{i}", diff="medium", location=loc,
            task_desc=f"Search for a rental car in {loc} on {{dateRange}}. I need a large vehicle with at least 7 seats, under $600.",
            queries=[[{"min_passengers": 7, "max_price": 600.0}]],
            hint="Use the 7+ passenger capacity filter.",
            values={"dateRange": f"in {i*2} weeks"}
        )

    # Hard Car Hire (17)
    for i in range(1, 18):
        loc = random.choice(["London", "Paris", "Barcelona", "Rome", "Munich", "Zurich"])
        sup = random.choice(["Enterprise", "Alamo", "Hertz", "Avis", "Sixt"])
        add_car(
            tid=f"skyscanner/info_gathering/carhire/hard/{i}", diff="hard", location=loc,
            task_desc=f"Find a premium automatic car hire at {loc} airport on {{dateRange}}. Must hold at least 5 passengers. Strongly prefer {sup} as the supplier.",
            queries=[[{"car_types": ["Automatic", "Auto", "Premium"], "min_passengers": 5, "airlines": [sup]}]], # airlines key acts broadly for suppliers in JS mapping currently, but let's assume JS matches title/category
            hint="Filter by Automatic transmission, passenger capacity, and specific supplier vendor.",
            values={"dateRange": f"in {i*4} days"}
        )

    # -------------------------------------------------------------
    # Export
    # -------------------------------------------------------------
    out_file = "navi_bench/skyscanner/skyscanner_info_gathering_tasks.csv"
    with open(out_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "task_id", "task_generation_config_json", "env", "domain", 
            "l1_category", "l2_category", "suggested_difficulty", 
            "suggested_hint", "suggested_max_steps", "suggested_split", "metadata_json"
        ])
        writer.writeheader()
        writer.writerows(rows)
    
    # Calculate Mix
    easy = sum(1 for r in rows if r["suggested_difficulty"] == "easy")
    medium = sum(1 for r in rows if r["suggested_difficulty"] == "medium")
    hard = sum(1 for r in rows if r["suggested_difficulty"] == "hard")
    
    print(f"Generated {len(rows)} tasks in {out_file}")
    print(f"Mix -> Easy: {easy}, Medium: {medium}, Hard/Extreme: {hard}")

if __name__ == "__main__":
    main()
