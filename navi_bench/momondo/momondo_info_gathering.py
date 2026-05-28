"""Momondo info gathering verifier for flight, hotel, and car searches."""

import functools
import asyncio
import re
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import BaseModel
from typing_extensions import TypedDict

# Assuming these are from your internal benchmark framework
from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import initialize_user_metadata, initialize_placeholder_map, render_task_statement

class MultiCandidateQuery(TypedDict, total=False):
    # Flight fields
    origins: list[str] | None
    destinations: list[str] | None
    depart_dates: list[str] | None
    return_dates: list[str] | None
    airlines: list[str] | None
    require_direct: bool | None
    max_stops: int | None
    cabin_classes: list[str] | None
    
    # Universal / Shared fields
    max_price: float | None
    min_price: float | None
    
    # Hotel fields
    cities: list[str] | None
    check_in_dates: list[str] | None
    check_out_dates: list[str] | None
    min_stars: int | None
    min_score: float | None
    require_freebies: list[str] | None

    # Car fields
    pickup_locations: list[str] | None
    pickup_dates: list[str] | None
    car_types: list[str] | None
    min_passengers: int | None

class InfoDict(TypedDict, total=False):
    url: str
    source: str
    pageType: str
    antiBotStatus: str
    price: float
    
    # Flight
    origin: str
    destination: str
    departDate: str
    departTime: str
    arrivalTime: str
    airline: str
    stops: int
    filterMaxStops: int
    filterAirlines: list[str]

    # Hotel
    city: str
    checkIn: str
    checkOut: str
    title: str
    score: float | None
    stars: int
    freebies: list[str]
    location: str

    # Car
    pickUpLocation: str
    dropOffLocation: str
    pickUpDate: str
    category: str
    provider: str
    agency: str
    passengers: int | None
    
    filterMaxPrice: float

class FinalResult(BaseModel):
    score: float
    n_queries: int
    n_covered: int
    queries: list[list[MultiCandidateQuery]]
    is_query_covered: list[bool]


class MomondoInfoGathering(BaseMetric):
    def __init__(self, queries: list[list[MultiCandidateQuery]]) -> None:
        super().__init__()
        self.queries = queries
        self._all_infos: list[list[InfoDict]] = []
        self._is_query_covered: list[bool] = [False] * len(queries)
        self._navigation_stack: list[dict] = [] 
        self._tracked_pages: set = set()

    @functools.cached_property
    def js_script(self) -> str:
        # POINTING TO THE NEW JS FILE
        with open(Path(__file__).parent / "momondo_info_gathering.js", "r") as f:
            return f.read()

    async def reset(self) -> None:
        self._all_infos = []
        self._is_query_covered = [False] * len(self.queries)
        self._navigation_stack = []
        self._tracked_pages = set()
    
    def attach_to_context(self, context) -> None:
        async def track_page(page) -> None:
            page_id = id(page)
            if page_id in self._tracked_pages: return
            self._tracked_pages.add(page_id)
            
            async def on_frame_navigated(frame):
                if frame != page.main_frame: return
                
                # UPDATED: We only want to evaluate Momondo URLs, blocking out external OTAs
                # Using "momondo." to catch .com, .in, .co.uk, etc.
                if "momondo." not in frame.url:
                    return
                
                try:
                    logger.info(f"[NAV] Momondo: {frame.url[:80]}...")
                    await self.update(page=page)
                except Exception:
                    pass
            
            page.on("framenavigated", lambda f: asyncio.create_task(on_frame_navigated(f)))
        
        for page in context.pages:
            asyncio.create_task(track_page(page))
        context.on("page", lambda p: asyncio.create_task(track_page(p)))

    async def update(self, **kwargs) -> None:
        page = kwargs["page"]
        content = await page.content()
        
        if "px-captcha" in content or "challenge-running" in content or "verify you are human" in content.lower():
            logger.error("Agent blocked by Momondo Anti-Bot.")

        all_frame_infos: list[InfoDict] = []
        for frame in page.frames:
            try:
                frame_infos = await asyncio.wait_for(frame.evaluate(self.js_script), timeout=3.0)
                if frame_infos and isinstance(frame_infos, list):
                    all_frame_infos.extend(frame_infos)
            except Exception: pass
        
        # Deduplication
        unique_infos = []
        seen = set()
        for info in all_frame_infos:
            ptype = info.get("pageType")
            if ptype == "flight_results":
                key = f"flight-{info.get('airline')}-{info.get('departTime')}-{info.get('price')}"
            elif ptype == "hotel_results":
                key = f"hotel-{info.get('title')}-{info.get('price')}"
            elif ptype == "car_results":
                key = f"car-{info.get('title')}-{info.get('provider')}-{info.get('price')}"
            else:
                key = str(info)
                
            if key not in seen:
                seen.add(key)
                unique_infos.append(info)
        
        infos = unique_infos

        if infos:
            print(f"\n[SCRAPED DATA FROM: {page.url[:60]}...]", flush=True)
            
            first_info = infos[0]
            ptype = first_info.get("pageType")
            if first_info.get('filterMaxPrice') or first_info.get('filterAirlines') or first_info.get('filterStops'):
                print("-" * 50)
                print(">> ACTIVE GLOBALS FILTERS DETECTED:")
                if max_p := first_info.get('filterMaxPrice'):
                    print(f"   Max Price Slider: ${max_p}")
                if airlines := first_info.get('filterAirlines'):
                    print(f"   Airlines Checked: {', '.join(airlines)}")
                if stops := first_info.get('filterStops'):
                    print(f"   Stops Checked:    {', '.join(stops)}")
                print("-" * 50)

            for i, item in enumerate(infos[:10], 1):
                price = item.get("price", "N/A")
                
                if ptype == "flight_results":
                    airline = item.get("airline", "Unknown").title()
                    stops = "Direct" if item.get("stops") == 0 else f"{item.get('stops')} Stops"
                    depart = item.get("departTime", "XX:XX")
                    arrive = item.get("arrivalTime", "XX:XX")
                    print(f"  {i}. {depart}-{arrive} | {airline} | {stops} | ${price}", flush=True)
                    
                elif ptype == "hotel_results":
                    name = item.get("title", "Unknown")
                    score = item.get("score", "N/A")
                    stars = item.get("stars", 0)
                    print(f"  {i}. {name} | {stars}★ | Rating: {score} | ${price}", flush=True)
                    
                elif ptype == "car_results":
                    name = item.get("title", "Unknown")
                    provider = item.get("provider", "Unknown")
                    print(f"  {i}. {name} | {provider} | ${price}", flush=True)

        page_type = infos[0].get("pageType", "unknown") if infos else "unknown"
        anti_bot = infos[0].get("antiBotStatus", "unknown") if infos else "unknown"

        self._all_infos.append(infos)
        
        base_url = page.url.split("?")[0]
        page_entry = {"url": page.url, "base_url": base_url, "page_type": page_type, "anti_bot": anti_bot, "infos": infos}
        
        existing_idx = next((i for i, e in enumerate(self._navigation_stack) if e["base_url"] == base_url and e["page_type"] == page_type), None)
        if existing_idx is not None:
            self._navigation_stack[existing_idx] = page_entry
        else:
            self._navigation_stack.append(page_entry)

    async def compute(self) -> FinalResult:
        for page_visit in reversed(self._navigation_stack):
            if page_visit["anti_bot"] != "clear":
                continue
                
            if page_visit["page_type"] in ["flight_results", "hotel_results", "car_results"]:
                for i, alternative_conditions in enumerate(self.queries):
                    if self._is_query_covered[i]: continue
                    for info in page_visit["infos"]:
                        if self._check_alternative_conditions(i, alternative_conditions, info):
                            self._is_query_covered[i] = True
                            break
        
        n_queries = len(self.queries)
        n_covered = sum(self._is_query_covered)
        return FinalResult(score=n_covered / max(n_queries, 1), n_queries=n_queries, n_covered=n_covered, queries=self.queries, is_query_covered=self._is_query_covered)

    def _check_alternative_conditions(self, i: int, alternative_conditions: list[MultiCandidateQuery], info: InfoDict) -> bool:
        for alternative_condition in alternative_conditions:
            if self._check_multi_candidate_query(alternative_condition, info):
                return True
        return False

    @classmethod
    def _check_multi_candidate_query(cls, query: MultiCandidateQuery, info: InfoDict) -> bool:
        
        if q_origins := query.get("origins"):
            info_origin = (info.get("origin") or "").lower()
            if not any(o.lower() == info_origin for o in q_origins): return False

        if q_destinations := query.get("destinations"):
            info_dest = (info.get("destination") or "").lower()
            if not any(d.lower() == info_dest for d in q_destinations): return False

        # if q_depart_dates := query.get("depart_dates"):
        #     if info.get("departDate") not in q_depart_dates: return False

        if q_airlines := query.get("airlines"):
            ticket_airline = (info.get("airline") or "").lower()
            info_airlines = info.get("filterAirlines") or []
            
            ticket_matched = any(a.lower() in ticket_airline for a in q_airlines)
            filter_matched = any(a.lower() in ia.lower() for a in q_airlines for ia in info_airlines)
            
            if not (ticket_matched or filter_matched): 
                return False

        if "max_price" in query and query["max_price"] is not None:
            max_price = query["max_price"]
            eval_max_price = info.get("price") or info.get("filterMaxPrice")
            if eval_max_price is None or eval_max_price > max_price: return False
        
        if "min_price" in query and query["min_price"] is not None:
            min_price = query["min_price"]
            eval_price = info.get("price")
            if eval_price is None or eval_price < min_price: return False

        if q_cabin_classes := query.get("cabin_classes"):
            card_info = (info.get("cabinClass") or info.get("info") or "").lower()
            if not any(c.lower() in card_info for c in q_cabin_classes):
                return False

        if query.get("require_direct") is True:
            card_direct = info.get("stops") == 0
            filter_direct = any("direct" in s.lower() for s in info.get("filterStops", []))
            
            if not (card_direct or filter_direct): 
                return False
            
        if "max_stops" in query and query["max_stops"] is not None:
            max_stops = query["max_stops"]
            card_stops = info.get("stops")
            
            card_passes = card_stops is not None and card_stops <= max_stops
            
            filter_stops = info.get("filterStops", [])
            filter_passes = False
            if max_stops >= 0 and any("direct" in s.lower() for s in filter_stops):
                filter_passes = True
            if max_stops >= 1 and any("1 stop" in s.lower() for s in filter_stops):
                filter_passes = True
                
            if not (card_passes or filter_passes): 
                return False
        
        if q_cities := query.get("cities"):
            info_city = (info.get("city") or "").lower()
            if not any(c.lower() in info_city for c in q_cities): return False
            
        if "min_stars" in query and query["min_stars"] is not None:
            stars = info.get("stars")
            # If stars is None or less than required, it fails the query
            if stars is None or stars < query["min_stars"]: 
                return False
            
        if "min_score" in query and query["min_score"] is not None:
            score = info.get("score")
            if score is None or score < query["min_score"]: return False
            
        if q_freebies := query.get("require_freebies"):
            info_freebies = [f.lower() for f in info.get("freebies", [])]
            if not all(any(qf.lower() in inf for inf in info_freebies) for qf in q_freebies): return False

        if q_pickup := query.get("pickup_locations"):
            info_pickup = (info.get("pickUpLocation") or "").lower()
            if not any(p.lower() in info_pickup for p in q_pickup): return False
            
        if "min_passengers" in query and query["min_passengers"] is not None:
            passengers = info.get("passengers")
            if passengers is None or passengers < query["min_passengers"]: return False
            
            
        # BUG FIX: Ensure car types are actually evaluated against the DOM data
        if q_car_types := query.get("car_types"):
            info_title = (info.get("title") or "").lower()
            info_category = (info.get("category") or "").lower()
            
            type_matched = False
            for car_type in q_car_types:
                ct_lower = car_type.lower()
                if ct_lower in info_title or ct_lower in info_category:
                    type_matched = True
                    break
            
            if not type_matched:
                return False
        
        # if q_check_in := query.get("check_in_dates"):
        #     if info.get("checkIn") not in q_check_in: return False
            
        # if q_pickup_dates := query.get("pickup_dates"):
        #     if info.get("pickUpDate") not in q_pickup_dates: return False
        
        # Flight Date Check
        if q_depart_dates := query.get("depart_dates"):
            info_val = info.get("departDate")
            # Only fail if the info HAS a departDate and it doesn't match
            if info_val and info_val not in q_depart_dates: 
                return False

        # Hotel Date Check
        if q_check_in := query.get("check_in_dates"):
            info_val = info.get("checkIn")
            if info_val and info_val not in q_check_in: 
                return False

        # Car Date Check
        if q_pickup_dates := query.get("pickup_dates"):
            info_val = info.get("pickUpDate")
            if info_val and info_val not in q_pickup_dates: 
                return False

        return True


def generate_task_config_deterministic(
    mode: Literal["any", "all"],
    task: str,
    queries: list[list[MultiCandidateQuery]],
    location: str,
    timezone: str,
    timestamp: int | None = None,
    url: str = "https://www.momondo.com/", 
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    
    if values:
        placeholder_map, current_date = initialize_placeholder_map(user_metadata, values)
        task = render_task_statement(task, placeholder_map)
        date_tuple = placeholder_map.get("dateRange")
        
        if date_tuple and isinstance(date_tuple, tuple) and len(date_tuple) == 2:
            _, resolved_iso_dates = date_tuple 
            
            if resolved_iso_dates:
                for alternative_conditions in queries:
                    for query in alternative_conditions:
                        query["depart_dates"] = resolved_iso_dates
                        query["check_in_dates"] = resolved_iso_dates
                        query["pickup_dates"] = resolved_iso_dates

                        if "origins" in query or "destinations" in query:
                            query["depart_dates"] = resolved_iso_dates
                            
                        elif "cities" in query or "min_stars" in query:
                            query["check_in_dates"] = resolved_iso_dates
                            
                        elif "pickup_locations" in query or "car_types" in query:
                            query["pickup_dates"] = resolved_iso_dates
                        
                        else:
                            # Fallback: If it's a generic price query, 
                            # we may still need to be careful not to break it
                            pass
                        
    eval_config = {
        "_target_": get_import_path(MomondoInfoGathering),
        "queries": queries
    }
    
    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)