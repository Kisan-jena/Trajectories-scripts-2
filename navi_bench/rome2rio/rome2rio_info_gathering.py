import functools
from loguru import logger
from pydantic import BaseModel
from typing import TypedDict, List
from pathlib import Path

from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import initialize_user_metadata, initialize_placeholder_map, render_task_statement

# ---------------- TYPES ----------------


class Query(TypedDict, total=False):
    modes: List[str]
    max_price: float
    min_price: float
    max_duration: int
    min_duration: int
    min_stars: int
    min_score: float
    min_rating: float
    origins: List[str]
    destinations: List[str]
    cities: List[str]


class Info(TypedDict, total=False):
    mode: str
    min_price: float
    max_price: float
    currency: str
    duration: int
    pageType: str
    name: str
    stars: int
    score: float
    rating: float
    location_score: float
    origin: str
    destination: str
    route_text: str


class FinalResult(BaseModel):
    score: float
    n_queries: int
    n_covered: int


# ---------------- CORE CLASS ----------------


class Rome2RioInfoGathering(BaseMetric):

    def __init__(self, queries, mode: str = "any"):
        super().__init__()
        self.queries = queries
        self.mode = mode  # "any": one info matching one query covers a group
        self._infos = []
        self._covered = [False] * len(queries)
        self.seen_signatures = set()
        self._page_city = None  # Store the current page's city for validation

    async def reset(self) -> None:
        self._infos = []
        self._covered = [False] * len(self.queries)
        self.seen_signatures = set()
        self._page_city = None

    @functools.cached_property
    def js_script(self) -> str:
        return (Path(__file__).parent / "rome2rio_info_gathering.js").read_text()

    async def update(self, **kwargs):
        page = kwargs["page"]

        try:
            # Extract page city/location from page title for validation
            try:
                page_title = await page.title()
                self._page_city = self._extract_city_from_title(page_title)
            except (AttributeError, TypeError):
                # page.title() might not be available in tests or mock objects
                self._page_city = None

            data = await page.evaluate(self.js_script)

            if isinstance(data, list):
                new_data = []

                # Deduplication logic
                for r in data:
                    page_type = r.get("pageType")
                    if page_type in ["hotels", "experiences"]:
                        sig = f"{page_type}_{r.get('name')}_{r.get('min_price')}"
                    else:
                        sig = f"{page_type}_{r.get('mode')}_{r.get('min_price')}_{r.get('duration')}"

                    if sig not in self.seen_signatures:
                        self.seen_signatures.add(sig)
                        new_data.append(r)
                        self._infos.append(r)

                if new_data:
                    print(f"\n[SCRAPED {len(new_data)} NEW ITEMS] -> {page.url}")

                    for i, r in enumerate(new_data[:10], 1):
                        price_display = f"{r.get('min_price')}" if r.get("min_price") is not None else "N/A"
                        duration_display = f"{r.get('duration')} min" if r.get("duration") is not None else "N/A"

                        if r.get("pageType") == "hotels":
                            stars_display = f"{r.get('stars')}★" if r.get("stars") else "Unrated"
                            print(f"{i}. [HOTEL] {r.get('name')} ({stars_display}) | {price_display}")
                        elif r.get("pageType") == "experiences":
                            rating_display = f"{r.get('rating')}★" if r.get("rating") else "Unrated"
                            print(
                                f"{i}. [EXPERIENCE] {r.get('name')} ({rating_display}) | {price_display} | {duration_display}"
                            )
                        elif r.get("pageType") == "trip_details":
                            print(f"{i}. [TRIP DETAILS] {r.get('mode')} | {price_display} | {duration_display}")
                        else:
                            print(f"{i}. [ROUTE] {r.get('mode')} | {price_display} | {duration_display}")

        except Exception as e:
            logger.error(f"Exception during scraping: {e}", exc_info=True)
            print(f"[ERROR] scraping failed: {e}")

    async def compute(self):
        for info in self._infos:
            for i, query_group in enumerate(self.queries):
                if self._covered[i]:
                    continue
                for query in query_group:
                    if self._match(query, info):
                        self._covered[i] = True
                        break

        n_queries = len(self.queries)
        n_covered = sum(self._covered)

        result = FinalResult(score=n_covered / max(n_queries, 1), n_queries=n_queries, n_covered=n_covered)
        return result

    def _price_to_usd(self, price: float | None, _currency: str | None = None) -> float | None:
        """Return price as-is. All prices are in USD on the website."""
        return price

    def _extract_city_from_title(self, page_title: str) -> str | None:
        """Extract city name from Booking.com page title.
        E.g., 'Hotels in Paris - Search Results | Booking.com' -> 'Paris'
        Works for ANY city without hardcoding.
        """
        if not page_title:
            return None

        import re

        # Pattern 1: "Hotels in [CITY] - Search Results"
        match = re.search(r"Hotels in\s+([^-|]+?)\s*(?:-|[|])", page_title)
        if match:
            city = match.group(1).strip()
            return city

        # Pattern 2: "Hotels in [CITY]" (if no dash follows)
        match = re.search(r"Hotels in\s+([^-|]+?)(?:\s|$)", page_title)
        if match:
            city = match.group(1).strip()
            return city

        # Pattern 3: Just extract the first meaningful word sequence
        # This catches other potential formats
        match = re.search(r"[Hh]otels?\s+(?:in\s+)?([A-Za-z\s]+?)(?:\s*[-|]|$)", page_title)
        if match:
            city = match.group(1).strip()
            if city and city.lower() != "search" and len(city) > 1:
                return city

        return None

    def _match(self, query, info):
        page_type = info.get("pageType", "")

        # Check cities constraint (for hotels and other location-based searches)
        if "cities" in query and page_type == "hotels":
            # Skip city check if page city is not set (will be detected only from Booking.com titles)
            if self._page_city is not None:
                query_cities = [c.lower() for c in query["cities"]]
                page_city_lower = self._page_city.lower()
                if not any(city in page_city_lower for city in query_cities):
                    return False

        if "modes" in query:
            check = all if self.mode == "all" else any
            if page_type in ("hotels", "experiences"):
                # Hotels and experiences: match modes against the name field
                # because JS emits static mode strings ("Hotel", "Experience")
                name = (info.get("name") or "").lower()
                if not check(m.lower() in name for m in query["modes"]):
                    return False
            elif page_type == "schedule":
                mode = (info.get("mode") or "").lower()
                route_text = (info.get("route_text") or "").lower()
                haystack = f"{mode} {route_text}".strip()

                # Exact word matching: all words from query_mode must match
                def word_match(query_mode, haystack_text):
                    """Check if all words from query_mode match exactly in haystack_text.
                    E.g., 'indigo airlines' requires both 'indigo' AND 'airlines' to be present."""
                    query_words = query_mode.lower().split()
                    haystack_words = haystack_text.lower().split()
                    # All query words must have an exact match in haystack
                    for qw in query_words:
                        if qw not in haystack_words:
                            return False
                    return True

                if not check(word_match(m, haystack) for m in query["modes"]):
                    return False
            else:
                mode = (info.get("mode") or "").lower()
                if not check(m.lower() in mode for m in query["modes"]):
                    return False

        # Check destinations in the route mode string
        # NOTE: Routes/trip_details have origin/destination implicit in the URL.
        if "destinations" in query:
            destinations = query["destinations"]
            if page_type == "schedule":
                route_dest = (info.get("destination") or "").lower()
                if route_dest and not any(dest.lower() in route_dest for dest in destinations):
                    print(
                        f"  [QUERY FAIL] Destination mismatch: looking for {destinations} in schedule destination: {repr(route_dest)}"
                    )
                    return False
            elif page_type not in ("results", "trip_details"):
                mode = (info.get("mode") or "").lower()
                match = any(dest.lower() in mode for dest in destinations)
                if not match:
                    print(f"  [QUERY FAIL] Destination mismatch: looking for {destinations} in mode: {repr(mode)}")
                    return False

        # Check origins in the route mode string
        # NOTE: Routes/trip_details have origin/destination implicit in the URL.
        if "origins" in query:
            origins = query["origins"]
            if page_type == "schedule":
                route_origin = (info.get("origin") or "").lower()
                # Check if origin matches OR if Hindon is in the route (Hindon airport serves Delhi)
                hindon_in_modes = any("hindon" in m.lower() for m in query.get("modes", []))
                if route_origin:
                    origin_match = any(orig.lower() in route_origin for orig in origins)
                    hindon_match = hindon_in_modes and route_origin == "hindon"
                    if not (origin_match or hindon_match):
                        print(
                            f"  [QUERY FAIL] Origin mismatch: looking for {origins} in schedule origin: {repr(route_origin)}"
                        )
                        return False
            elif page_type not in ("results", "trip_details"):
                mode = (info.get("mode") or "").lower()
                match = any(orig.lower() in mode for orig in origins)
                if not match:
                    print(f"  [QUERY FAIL] Origin mismatch: looking for {origins} in mode: {repr(mode)}")
                    return False

        if "max_price" in query:
            currency = info.get("currency")
            price = self._price_to_usd(info.get("min_price"), currency)
            if price is None or price > query["max_price"]:
                return False

        if "min_price" in query:
            # Use max_price from the scraped range so a route like  30k– 45k
            # correctly satisfies min_price: 33000 (some options exceed the floor).
            currency = info.get("currency")
            price = self._price_to_usd(info.get("max_price"), currency)
            if price is None or price < query["min_price"]:
                return False

        if "max_duration" in query:
            duration = info.get("duration")
            if duration is None or duration > query["max_duration"]:
                return False

        if "min_duration" in query:
            duration = info.get("duration")
            if duration is None or duration < query["min_duration"]:
                return False

        if "min_stars" in query:
            stars = info.get("stars")
            if stars is None or stars < query["min_stars"]:
                return False

        if "max_stars" in query:
            stars = info.get("stars")
            if stars is None or stars > query["max_stars"]:
                return False

        if "min_score" in query:
            score = info.get("score")
            if score is None or score < query["min_score"]:
                return False

        if "min_rating" in query:
            rating = info.get("rating")
            if rating is None or rating < query["min_rating"]:
                return False

        return True

    def why_not_match(self, query, info) -> list:
        """Return list of reasons why `info` does not match `query`.
        Empty list means it matches.
        """
        reasons = []
        page_type = info.get("pageType", "")

        # Cities check
        if "cities" in query and page_type == "hotels":
            # Only check if page city was detected from Booking.com-style title
            if self._page_city is not None:
                query_cities = [c.lower() for c in query["cities"]]
                page_city_lower = self._page_city.lower()
                if not any(city in page_city_lower for city in query_cities):
                    reasons.append(f"page city '{self._page_city}' not in query cities {query['cities']}")

        # Modes
        if "modes" in query:
            if page_type in ("hotels", "experiences"):
                name = (info.get("name") or "").lower()
                if not (all if self.mode == "all" else any)(m.lower() in name for m in query["modes"]):
                    reasons.append(f"mode/name doesn't contain any of {query['modes']}")
            elif page_type == "schedule":
                mode = (info.get("mode") or "").lower()
                route_text = (info.get("route_text") or "").lower()
                haystack = f"{mode} {route_text}".strip()

                # Exact word matching: all words from query_mode must match
                def word_match(query_mode, haystack_text):
                    """Check if all words from query_mode match exactly in haystack_text.
                    E.g., 'indigo airlines' requires both 'indigo' AND 'airlines' to be present."""
                    query_words = query_mode.lower().split()
                    haystack_words = haystack_text.lower().split()
                    # All query words must have an exact match in haystack
                    for qw in query_words:
                        if qw not in haystack_words:
                            return False
                    return True

                if not (all if self.mode == "all" else any)(word_match(m, haystack) for m in query["modes"]):
                    reasons.append(f"mode/route doesn't match {query['modes']} (airlines: '{mode}', route: '{route_text}')")
            else:
                mode = (info.get("mode") or "").lower()
                if not (all if self.mode == "all" else any)(m.lower() in mode for m in query["modes"]):
                    reasons.append(f"mode '{mode}' doesn't match {query['modes']}")

        # Price checks
        if "max_price" in query:
            price = self._price_to_usd(info.get("min_price"), info.get("currency"))
            if price is None:
                reasons.append("price unknown")
            elif price > query["max_price"]:
                reasons.append(f"price {price:.2f} USD > max_price {query['max_price']}")

        if "min_price" in query:
            price = self._price_to_usd(info.get("max_price"), info.get("currency"))
            if price is None:
                reasons.append("price unknown")
            elif price < query["min_price"]:
                reasons.append(f"price {price:.2f} USD < min_price {query['min_price']}")

        # Duration checks
        if "max_duration" in query:
            duration = info.get("duration")
            if duration is None:
                reasons.append("duration unknown")
            elif duration > query["max_duration"]:
                reasons.append(f"duration {duration} > max_duration {query['max_duration']}")

        if "min_duration" in query:
            duration = info.get("duration")
            if duration is None:
                reasons.append("duration unknown")
            elif duration < query["min_duration"]:
                reasons.append(f"duration {duration} < min_duration {query['min_duration']}")

        # Stars
        if "min_stars" in query:
            stars = info.get("stars")
            if stars is None:
                reasons.append("stars unknown")
            elif stars < query["min_stars"]:
                reasons.append(f"stars {stars} < min_stars {query['min_stars']}")

        if "max_stars" in query:
            stars = info.get("stars")
            if stars is None:
                reasons.append("stars unknown")
            elif stars > query["max_stars"]:
                reasons.append(f"stars {stars} > max_stars {query['max_stars']}")

        # Score / rating
        if "min_score" in query:
            score = info.get("score")
            if score is None:
                reasons.append("score unknown")
            elif score < query["min_score"]:
                reasons.append(f"score {score} < min_score {query['min_score']}")

        if "min_rating" in query:
            rating = info.get("rating")
            if rating is None:
                reasons.append("rating unknown")
            elif rating < query["min_rating"]:
                reasons.append(f"rating {rating} < min_rating {query['min_rating']}")

        return reasons


# ---------------- TASK CONFIG ----------------


def generate_task_config_deterministic(
    mode: str,
    task: str,
    queries: list,
    location: str,
    timezone: str,
    timestamp: int | None = None,
    url: str = "https://www.rome2rio.com/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    user_metadata = initialize_user_metadata(timezone, location, timestamp)

    if values:
        placeholder_map, _ = initialize_placeholder_map(user_metadata, values)
        task = render_task_statement(task, placeholder_map)

    eval_config = {
        "_target_": get_import_path(Rome2RioInfoGathering),
        "queries": queries,
        "mode": mode,
    }
    return BaseTaskConfig(url=url, task=task, user_metadata=user_metadata, eval_config=eval_config)
