"""Ticketmaster info gathering verifier for event ticket searches.

This module provides functionality to verify AI agent ticket search results on Ticketmaster
by gathering event information through JavaScript scraping and matching against expected queries.
"""

import functools
import itertools
import re
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from loguru import logger
from playwright.async_api import Page
from pydantic import BaseModel
from typing_extensions import TypedDict

from navi_bench.base import BaseMetric, BaseTaskConfig, UserMetadata, get_import_path
from navi_bench.dates import (
    initialize_placeholder_map,
    initialize_user_metadata,
    render_task_statement,
)


class SingleCandidateQuery(TypedDict, total=False):
    """Single event query with specific criteria."""
    event_name: str | None
    event_category: str | None
    date: str | None
    time: str | None
    venue: str | None
    city: str | None
    
    min_tickets: int | None
    max_price: float | None
    min_price: float | None
    section: str | None
    row: str | None
    
    ticket_type: str | None
    require_available: bool | None


class MultiCandidateQuery(TypedDict, total=False):
    """Multi-option event query allowing alternatives."""
    event_names: list[str] | None
    event_categories: list[str] | None
    dates: list[str] | None
    times: list[str] | None
    venues: list[str] | None
    cities: list[str] | None
    
    min_tickets: int | None
    max_tickets: int | None
    ticket_quantities: list[int] | None
    max_price: float | None
    min_price: float | None
    currency: str | None
    sections: list[str] | None
    rows: list[str] | None
    
    ticket_types: list[str] | None
    require_resale: bool | None  # Ticketmaster specific
    exclude_resale: bool | None  # Ticketmaster specific
    
    require_available: bool | None
    require_page_type: str | list[str] | None
    availability_statuses: list[str] | None


class InputDict(TypedDict, total=False):
    """Input for update method."""
    page: Page


class InfoDict(TypedDict, total=False):
    """Scraped event information from JavaScript - Ticketmaster specific."""
    url: str
    source: str
    eventName: str
    eventCategory: str
    
    date: str
    time: str
    venue: str
    city: str
    
    section: str
    row: str
    seat: str
    
    price: float
    currency: str
    ticketCount: int
    
    isResale: bool
    obstructedView: bool
    
    availabilityStatus: str
    info: str
    
    pageType: str
    antiBotStatus: str
    globalStatus: str

    # New Filter Fields
    filterQuantity: int
    filterMinPrice: float
    filterMaxPrice: float

    filterTicketTypes: list[str]  # NEW
    filterADA: bool               # NEW

    # New Discovery Filters
    filterLocation: str
    filterDateRange: str
    filterGameType: str


class FinalResult(BaseModel):
    """Final verification result."""
    score: float
    n_queries: int
    n_covered: int
    queries: list[list[MultiCandidateQuery]]
    is_query_covered: list[bool]


class TicketmasterInfoGathering(BaseMetric):
    """Gather event ticket information from Ticketmaster to evaluate query coverage."""

    def __init__(self, queries: list[list[MultiCandidateQuery]]) -> None:
        super().__init__()
        self.queries = queries
        self._all_infos: list[list[InfoDict]] = []
        self._is_query_covered: list[bool] = [False] * len(queries)
        self._unavailable_evidences: list[list[list[InfoDict]]] = [
            [[] for _ in alternative_conditions] for alternative_conditions in queries
        ]
        self._navigation_stack: list[dict] = [] 
        self._tracked_pages: set = set()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(queries={self.queries})"

    @functools.cached_property
    def js_script(self) -> str:
        """Load the JavaScript scraper."""
        with open(Path(__file__).parent / "ticket_info_gathering.js", "r") as f:
            return f.read()

    async def reset(self) -> None:
        self._all_infos = []
        self._is_query_covered = [False] * len(self.queries)
        self._unavailable_evidences = [[[] for _ in alternative_conditions] for alternative_conditions in self.queries]
        self._navigation_stack = []
        self._tracked_pages = set()
    
    def attach_to_context(self, context) -> None:
        """Attach automatic navigation tracking to a browser context."""
        
        async def track_page(page) -> None:
            page_id = id(page)
            if page_id in self._tracked_pages:
                return
            self._tracked_pages.add(page_id)
            
            async def on_frame_navigated(frame):
                if frame != page.main_frame:
                    return
                try:
                    logger.info(f"[NAV] TM: {page.url[:80]}...")
                    await self.update(page=page)
                except Exception as e:
                    logger.warning(f"Update failed: {e}")
            
            page.on("framenavigated", lambda f: asyncio.create_task(on_frame_navigated(f)))
            logger.info(f"Tracking attached to TM page: {page.url[:60]}...")
        
        for page in context.pages:
            asyncio.create_task(track_page(page))
        
        context.on("page", lambda p: asyncio.create_task(track_page(p)))

    async def update(self, **kwargs) -> None:
        """Update with new page information, accommodating Ticketmaster's DOM."""
        inputs: InputDict = kwargs
        page = inputs["page"]
        url = page.url
        
        # 1. Check for Anti-Bot / Queue immediately to avoid useless timeouts
        content = await page.content()
        if "queue-it.net" in url or "You are now in line" in content:
            logger.warning("Agent is currently in a Ticketmaster Queue.")
        elif "Pardon the Interruption" in content or "sec-text-container" in content:
            logger.error("Agent has been blocked by Ticketmaster PerimeterX/DataDome.")

        # 2. Wait for TM specific elements (Non-blocking)
        if "/event/" in url:
            try:
                await page.wait_for_selector(
                    'li[data-price], #list-view li, [data-bdd*="list-item"]',
                    state="attached",
                    timeout=10000
                )
                await page.wait_for_timeout(1000) # Hydration buffer
            except Exception:
                pass # Fail silently, we will scrape frames anyway

        # 3. RUN JS SCRAPER ACROSS ALL FRAMES
        all_frame_infos: list[InfoDict] = []
        for frame in page.frames:
            try:
                frame_infos = await frame.evaluate(self.js_script)
                if frame_infos and isinstance(frame_infos, list):
                    all_frame_infos.extend(frame_infos)
            except Exception:
                pass # Ignore cross-origin frame access errors
        
        # Deduplicate results across frames
        unique_infos = []
        seen_keys = set()
        for info in all_frame_infos:
            # Create a unique signature for each ticket to prevent double-counting
            key = (
                f"{info.get('eventName')}-{info.get('date')}-{info.get('section')}-"
                f"{info.get('row')}-{info.get('seat')}-{info.get('listingId')}-"
                f"{info.get('price')}-{info.get('source')}"
            )
            if key not in seen_keys:
                seen_keys.add(key)
                unique_infos.append(info)
        
        infos = unique_infos

        # =====================================================================
        # DEBUG: SCRAPING STAGE BREAKDOWN
        # =====================================================================
        logger.info("▼▼▼ SCRAPING STAGE BREAKDOWN ▼▼▼")
        if not infos:
            logger.warning("No data scraped at all from this page!")
        else:
            # Grab page filters from the first info dict
            f_qty = infos[0].get("filterQuantity", "Any")
            f_min = infos[0].get("filterMinPrice", "Any")
            f_max = infos[0].get("filterMaxPrice", "Any")
            f_types = infos[0].get("filterTicketTypes")
            f_ada = infos[0].get("filterADA", False)
            f_loc = infos[0].get("filterLocation") or "Any"
            f_date = infos[0].get("filterDateRange") or "Any"

            types_str = ", ".join(f_types) if f_types else "All/Default"
            ada_str = "Yes" if f_ada else "No"
            
            # Formatted onto two lines so it doesn't wrap messily in your terminal
            logger.info(f"  [DISCOVERY FILTERS] -> Loc: {f_loc} | Dates: {f_date}")
            logger.info(f"  [TICKET FILTERS]    -> Qty: {f_qty} | Min: ${f_min} | Max: ${f_max} | Types: [{types_str}] | ADA: {ada_str}")
            
            sources = {}
            for info in infos:
                src = info.get("source", "unknown_source")
                if src not in sources:
                    sources[src] = []
                sources[src].append(info)
                
            for src, items in sources.items():
                logger.info(f"  [{src.upper()}] -> Found {len(items)} items")
                for i, item in enumerate(items[:3]):
                    name = str(item.get("eventName", "Unknown")).title()[:35]
                    price = item.get("price", "N/A")
                    date = item.get("date", "N/A")
                    section = item.get("section", "N/A")
                    row = item.get("row", "N/A")
                    logger.info(f"      {i+1}. {name} | Date: {date} | Price: ${price} | Sec: {section}, Row: {row}")
                
                if len(items) > 3:
                    logger.info(f"      ... and {len(items) - 3} more items from {src}.")
        logger.info("▲▲▲==========================▲▲▲")
        # =====================================================================

        # 4. Filter and Stack logic
        page_type = infos[0].get("pageType", "unknown") if infos else "unknown"
        anti_bot = infos[0].get("antiBotStatus", "unknown") if infos else "unknown"

        self._all_infos.append(infos)
        
        base_url = url.split("?")[0]
        existing_idx = next((i for i, e in enumerate(self._navigation_stack) 
                           if e["base_url"] == base_url and e["page_type"] == page_type), None)
        
        page_entry = {
            "url": url,
            "base_url": base_url,
            "page_type": page_type,
            "anti_bot": anti_bot,
            "infos": infos,
        }
        
        if existing_idx is not None:
            self._navigation_stack[existing_idx] = page_entry
        else:
            self._navigation_stack.append(page_entry)

    async def compute(self) -> FinalResult:
        """Compute final coverage score by walking backwards through navigation stack."""
        event_listing_found = False
        fallback_infos: list[InfoDict] = []
        
        # Collect context from all pages to inherit missing metadata on event pages.
        # We key by both the individual info URL and the page_visit base_url so that
        # DOM ticket listings (which often lack their own url field) can still inherit
        # context from the page they were scraped on.
        event_contexts: dict[str, dict[str, set]] = {}
        
        def _add_to_context(key: str, info: dict) -> None:
            if key not in event_contexts:
                event_contexts[key] = {"cities": set(), "venues": set(), "categories": set()}
            ctx = event_contexts[key]
            if c := info.get("city"): ctx["cities"].add(c.lower())
            if c := info.get("filterLocation"): ctx["cities"].add(c.lower())
            if v := info.get("venue"): ctx["venues"].add(v.lower())
            if cat := info.get("eventCategory"): ctx["categories"].add(cat.lower())
        
        for page_visit in self._navigation_stack:
            page_base = page_visit["base_url"]
            for info in page_visit["infos"]:
                info_url = (info.get("url") or "").split("?")[0]
                # Add context keyed by the info's own URL
                if "/event/" in info_url:
                    _add_to_context(info_url, info)
                # Also add context keyed by the page's base URL (for DOM tickets with no url)
                if "/event/" in page_base:
                    _add_to_context(page_base, info)

        # Walk backwards
        for page_visit in reversed(self._navigation_stack):
            page_type = page_visit["page_type"]
            anti_bot = page_visit["anti_bot"]
            page_infos = page_visit["infos"]

            if anti_bot == "blocked_perimeterx":
                logger.error("Cannot verify successful completion: Agent was blocked by PerimeterX.")
                continue
                
            if page_type == "event_listing" and not event_listing_found:
                event_listing_found = True
                page_base = page_visit["base_url"]
                for i, alternative_conditions in enumerate(self.queries):
                    if self._is_query_covered[i]:
                        continue
                    for info in page_infos:
                        if self._check_alternative_conditions(i, alternative_conditions, info, event_contexts, page_base):
                            self._is_query_covered[i] = True
                            break
                break
            
            elif page_type in ["event_category", "search_results"]:
                # Propagate page-level filter metadata to individual event cards.
                # The JS scraper captures filterLocation (e.g. "Detroit, MI") in a
                # separate filter info dict.  Event cards on the same page lack this
                # field, so we merge it so city checks can match.
                page_filter_loc = None
                page_category = None
                for info in page_infos:
                    if fl := info.get("filterLocation"):
                        page_filter_loc = fl
                    if cat := info.get("eventCategory"):
                        page_category = cat
                for info in page_infos:
                    if page_filter_loc and not info.get("filterLocation"):
                        info["filterLocation"] = page_filter_loc
                    if page_category and not info.get("eventCategory"):
                        info["eventCategory"] = page_category
                fallback_infos.extend(page_infos)
        
        # Fallback for sold-out/discovery
        if not event_listing_found and fallback_infos:
            for i, alternative_conditions in enumerate(self.queries):
                if self._is_query_covered[i]:
                    continue
                for info in fallback_infos:
                    if self._check_alternative_conditions(i, alternative_conditions, info, event_contexts):
                        self._is_query_covered[i] = True
                        break
        
        # Handle exhaustion: if ALL alternatives for a query are sold out, the agent
        # navigated correctly but couldn't buy tickets — credit the agent.
        # IMPORTANT: Only apply exhaustion when require_available is NOT True.
        # If any alternative explicitly requires availability, exhaustion should not
        # override the failure — the agent was expected to find available tickets.
        for i, alternative_conditions in enumerate(self.queries):
            if self._is_query_covered[i]:
                continue
            # Skip exhaustion if ANY alternative demands available tickets
            any_requires_available = any(
                alt.get("require_available", False) for alt in alternative_conditions
            )
            if any_requires_available:
                continue
            for j, alternative_condition in enumerate(alternative_conditions):
                if not self._is_exhausted(alternative_condition, self._unavailable_evidences[i][j]):
                    break
            else:
                self._is_query_covered[i] = True

        n_queries = len(self.queries)
        n_covered = sum(self._is_query_covered)
        return FinalResult(
            score=n_covered / max(n_queries, 1),
            n_queries=n_queries,
            n_covered=n_covered,
            queries=self.queries,
            is_query_covered=self._is_query_covered,
        )

    def _check_alternative_conditions(
        self, i: int, alternative_conditions: list[MultiCandidateQuery], info: InfoDict,
        event_contexts: dict, page_base_url: str | None = None
    ) -> bool:
        for j, alternative_condition in enumerate(alternative_conditions):
            evidences = self._unavailable_evidences[i][j]
            if self._check_multi_candidate_query(alternative_condition, info, evidences, event_contexts, page_base_url):
                return True
        return False

    @classmethod
    def _check_multi_candidate_query(
        cls, query: MultiCandidateQuery, info: InfoDict, evidences: list[InfoDict],
        event_contexts: dict, page_base_url: str | None = None
    ) -> bool:
        """Check TM-specific query constraints against the scraped InfoDict."""
        
        info_url = (info.get("url") or "").split("?")[0]
        _empty_ctx = {"cities": set(), "venues": set(), "categories": set()}
        # Look up context by the info's own URL first, then fall back to the page-level URL
        context = event_contexts.get(info_url, _empty_ctx)
        if context is _empty_ctx and page_base_url:
            context = event_contexts.get(page_base_url, _empty_ctx)
        
        # 1. TEXT / CATEGORY MATCHES
        if q_names := query.get("event_names"):
            if not any(q.lower() in (info.get("eventName") or "").lower() for q in q_names):
                return False

        if q_categories := query.get("event_categories"):
            cat = (info.get("eventCategory") or "").lower()
            cat_matched = any(c.lower() in cat for c in q_categories) if cat else False
            context_cat_matched = any(any(c.lower() in ctx_c for ctx_c in context["categories"]) for c in q_categories)
            
            if not (cat_matched or context_cat_matched):
                # Soft fallback for discovery tasks: if the agent navigated to a
                # search page (not /discover/<category>) but the filterLocation
                # matches, and this is a no-event-names discovery query, treat
                # category as satisfied.  The agent found events in the right
                # location even if the explicit category signal is missing.
                is_discovery = not query.get("event_names") and not query.get("require_available", False)
                filter_loc = (info.get("filterLocation") or "").lower()
                q_cities = query.get("cities", [])
                has_filter_loc_match = any(c.lower() in filter_loc for c in q_cities) if q_cities else False
                if not (is_discovery and has_filter_loc_match):
                    return False

        # --- ENHANCED DISCOVERY PAGE CHECKS (LOCATION) ---
        if q_cities := query.get("cities"):
            # Check parsed city from event card OR the typed UI location filter
            city_data = (info.get("city") or "").lower()
            filter_loc = (info.get("filterLocation") or "").lower()
            url_data = (info.get("url") or "").lower()
            
            city_matched = any(c.lower() in city_data or c.lower() in url_data for c in q_cities)
            filter_loc_matched = any(c.lower() in filter_loc for c in q_cities)
            context_city_matched = any(any(c.lower() in ctx_c for ctx_c in context["cities"]) for c in q_cities)
            
            if not (city_matched or filter_loc_matched or context_city_matched):
                return False

        if q_venues := query.get("venues"):
            def _norm_venue(s):
                """Normalize venue for comparison: strip punctuation, collapse spaces."""
                s = s.lower()
                s = re.sub(r'[&\-–—/,.:;\'\"()\[\]]+', ' ', s)  # replace punctuation with space
                return re.sub(r'\s+', ' ', s).strip()
            
            venue_data = _norm_venue(info.get("venue") or "")
            venue_matched = any(_norm_venue(q) in venue_data for q in q_venues) if venue_data else False
            # Also check raw substring match (for simple cases like "sphere")
            venue_raw = (info.get("venue") or "").lower()
            venue_raw_matched = any(q.lower() in venue_raw for q in q_venues)
            context_venue_matched = any(
                any(_norm_venue(q) in _norm_venue(ctx_v) for ctx_v in context["venues"])
                for q in q_venues
            )
            # Also check if venue name appears in the event URL or event name
            url_venue = (info.get("url") or "").lower()
            name_venue = (info.get("eventName") or "").lower()
            url_or_name_matched = any(q.lower() in url_venue or q.lower() in name_venue for q in q_venues)
            if not (venue_matched or venue_raw_matched or context_venue_matched or url_or_name_matched):
                return False


        # 2. NUMERIC / QUANTITY CONSTRAINTS
        ticket_count = info.get("ticketCount") or info.get("filterQuantity") or 0
        if min_tickets := query.get("min_tickets"):
            if ticket_count < min_tickets:
                return False
                
        if max_tickets := query.get("max_tickets"):
            if ticket_count > max_tickets:
                return False
                
        if quantities := query.get("ticket_quantities"):
            if ticket_count not in quantities:
                return False

        # 3. PRICE & CURRENCY CONSTRAINTS
        # Price can come from: individual ticket price, filter sidebar price,
        # or LD+JSON floorPrice (schema.org lowPrice).
        effective_price = (
            info.get("price")
            or info.get("filterMaxPrice")
            or info.get("filterMinPrice")
            or info.get("floorPrice")
        )
        if max_price := query.get("max_price"):
            eval_max_price = info.get("price") or info.get("filterMaxPrice") or info.get("floorPrice")
            if eval_max_price is None or eval_max_price > max_price:
                return False
                
        if min_price := query.get("min_price"):
            eval_min_price = info.get("price") or info.get("filterMinPrice") or info.get("floorPrice")
            if eval_min_price is None or eval_min_price < min_price:
                return False
                
        if req_currency := query.get("currency"):
            info_currency = (info.get("currency") or "USD").lower()
            if req_currency.lower() != info_currency:
                return False

        # 4. SEAT LOCATION CONSTRAINTS
        if q_sections := query.get("sections"):
            info_sec = (info.get("section") or "").lower()
            if not info_sec or not any(s.lower() in info_sec for s in q_sections):
                return False
                
        if q_rows := query.get("rows"):
            info_row = (info.get("row") or "").lower()
            if not info_row or not any(r.lower() in info_row for r in q_rows):
                return False

        # 5. TICKET TYPE & RESALE CONSTRAINTS
        if q_types := query.get("ticket_types"):
            info_type = (info.get("ticketType") or "standard").lower()
            # Also check the filter array if the individual ticket is missing data
            filter_types = info.get("filterTicketTypes") or []
            
            type_matched = any(t.lower() in info_type for t in q_types)
            filter_type_matched = any(t.lower() in [ft.lower() for ft in filter_types] for t in q_types)
            
            if not (type_matched or filter_type_matched):
                return False

        if query.get("require_resale") is True:
            if not info.get("isResale", False) and "resale" not in (info.get("filterTicketTypes") or []):
                return False
            
        if query.get("exclude_resale") is True:
            # 1. Fail if this specific ticket is a resale ticket
            if info.get("isResale", False):
                return False
            # 2. Fail if the resale filter checkbox is explicitly detected as checked
            if "resale" in [t.lower() for t in (info.get("filterTicketTypes") or [])]:
                return False
            # 3. Fail if the agent failed to apply the filter and resale tickets are still visible on the screen
            if info.get("hasResaleListings", False):
                return False

        # 6. PAGE TYPE & STATUS CONSTRAINTS
        if req_page_type := query.get("require_page_type"):
            info_page_type = info.get("pageType", "")
            if isinstance(req_page_type, list):
                if info_page_type not in req_page_type:
                    return False
            else:
                if info_page_type != req_page_type:
                    return False

        info_status = (info.get("availabilityStatus") or "").lower()
        if req_statuses := query.get("availability_statuses"):
            if info_status not in [s.lower() for s in req_statuses]:
                return False

        # 7. DATE, TIME & BASE AVAILABILITY
        require_available = query.get("require_available", False)
        is_unavailable = info_status in ["sold_out", "queue", "future_sale", "cancelled"]

        # --- NEW: ENHANCED DISCOVERY PAGE CHECKS (DATES) ---
        # Helper function to check if the query date is satisfied by the UI Date Range filter
        def is_date_satisfied(q_dates):
            info_date = info.get("date")
            if info_date in q_dates:
                return True
            
            # Fallback to UI Filter Date Range (e.g. "Mar 3 - Apr 30, 2026")
            filter_date = info.get("filterDateRange")
            if filter_date:
                try:
                    # 1. Try to parse as a SINGLE date (e.g., "Apr 18, 2026")
                    single_date = datetime.strptime(filter_date, "%b %d, %Y")
                    for q_date in q_dates:
                        try:
                            if datetime.strptime(q_date, "%Y-%m-%d") == single_date:
                                return True
                        except ValueError:
                            continue
                except ValueError:
                    # 2. Try to parse as a RANGE (e.g., "Mar 3 - Apr 30, 2026")
                    range_match = re.search(r'(\w+\s+\d+).*?(\w+\s+\d+,\s*\d{4})', filter_date)
                    if range_match:
                        try:
                            # 1. Parse the end date first, as it contains the definitive year
                            range_end = datetime.strptime(range_match.group(2).replace(',', ''), "%b %d %Y")
                            
                            # 2. Extract the year from the end date to use for the start date
                            year = range_end.year
                            range_start = datetime.strptime(range_match.group(1) + f" {year}", "%b %d %Y")
                            
                            # 3. Handle end-of-year wrap around (e.g., Dec 30 - Jan 5, 2026 means Dec 30 is 2025)
                            if range_start > range_end:
                                range_start = range_start.replace(year=year - 1)

                            for q_date in q_dates:
                                try:
                                    qd = datetime.strptime(q_date, "%Y-%m-%d")
                                    if range_start <= qd <= range_end:
                                        return True
                                except ValueError:
                                    continue
                        except ValueError:
                            pass
            return False

        if is_unavailable:
            if require_available:
                evidences.append(info)
                return False
            else:
                if q_dates := query.get("dates"):
                    if not is_date_satisfied(q_dates):
                        return False
                if q_times := query.get("times"):
                    if info.get("parsedTime") not in q_times and info.get("time") not in q_times:
                        return False
                return True
        else:
            if q_dates := query.get("dates"):
                if not is_date_satisfied(q_dates):
                    return False
            if q_times := query.get("times"):
                if info.get("parsedTime") not in q_times and info.get("time") not in q_times:
                    return False
            return True

    @classmethod
    def _check_single_candidate_query(cls, query: SingleCandidateQuery, info: InfoDict) -> bool:
        if (q_name := query.get("event_name")) and q_name.lower() not in info.get("eventName", "").lower():
            return False
        if (q_date := query.get("date")) and info.get("date") != q_date:
            return False
        return True

    @classmethod
    def _is_exhausted(cls, query: MultiCandidateQuery, evidences: list[InfoDict]) -> bool:
        q_names = query.get("event_names") or [None]
        q_dates = query.get("dates") or [None]

        for q_name, q_date in itertools.product(q_names, q_dates):
            if not any(cls._check_single_candidate_query({"event_name": q_name, "date": q_date}, info) for info in evidences):
                return False
        return True


def generate_task_config_deterministic(
    mode: Literal["any", "all"],
    task: str,
    queries: list[list[MultiCandidateQuery]],
    location: str,
    timezone: str,
    timestamp: int | None = None,
    url: str = "https://www.ticketmaster.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    
    if values:
        # 1. Resolve relative dates and apply time-travel/bumping logic
        placeholder_map, current_date = initialize_placeholder_map(user_metadata, values)
        
        # 2. Render the natural language prompt with the resolved text
        task = render_task_statement(task, placeholder_map)
        
        # 3. Inject the bumped ISO dates directly into the queries
        # FIX: The placeholder map stores a tuple of (natural_language_str, list_of_iso_dates)
        date_tuple = placeholder_map.get("dateRange")
        
        if date_tuple and isinstance(date_tuple, tuple) and len(date_tuple) == 2:
            _, resolved_iso_dates = date_tuple  # Unpack the tuple
            
            if resolved_iso_dates:
                for alternative_conditions in queries:
                    for query in alternative_conditions:
                            query["dates"] = resolved_iso_dates
                        
    eval_config = {
        "_target_": get_import_path(TicketmasterInfoGathering),
        "queries": queries
    }
    
    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)