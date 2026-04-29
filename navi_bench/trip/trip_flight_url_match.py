"""Trip.com Flight URL verifier for flight search tasks.

Verifies that an AI agent navigated to the correct Trip.com flight search
results page by comparing URL parameters.

Browser-Verified URL patterns (Mar 2026 on us.trip.com):

Round-trip search:
  https://us.trip.com/flights/showfarefirst
    ?dcity=nyc          # departure city IATA code
    &acity=lon          # arrival city IATA code
    &ddate=2026-04-10   # departure date (YYYY-MM-DD)
    &rdate=2026-04-17   # return date (YYYY-MM-DD)
    &flighttype=rt      # round-trip
    &class=y            # economy (y), business (c), first (f)
    &quantity=1          # number of passengers
    &lowpricemode=false  # optional
    &searchboxarg=t      # optional

One-way search:
  https://us.trip.com/flights/showfarefirst
    ?dcity=lax
    &acity=tyo
    &ddate=2026-05-01
    &flighttype=ow      # one-way
    &class=y
    &quantity=1

Alternative path patterns:
  /flights/city-to-city/tickets-xxx-yyy?...
  /flights/showfarefirst?...
"""

from typing import Any
from urllib.parse import parse_qs, urlparse, unquote

from beartype import beartype
from loguru import logger
from pydantic import BaseModel
from typing_extensions import TypedDict

from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import (
    initialize_user_metadata,
    initialize_placeholder_map,
    render_task_statement,
)


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

VALID_DOMAINS = {
    "trip.com",
    "us.trip.com",
    "www.trip.com",
    "uk.trip.com",
    "sg.trip.com",
    "au.trip.com",
    "in.trip.com",
}

# Cabin class codes
CABIN_CLASSES = {
    "y": "economy",
    "c": "business",
    "f": "first",
    "s": "premium_economy",
}

# Flight type codes
FLIGHT_TYPES = {
    "rt": "round_trip",
    "ow": "one_way",
    "mt": "multi_city",
}

# Query params that are auto-set / cosmetic and should be ignored
IGNORED_PARAMS = {
    "lowpricemode",
    "searchboxarg",
    "locale",
    "curr",
    "from",
    "source",
    "sessionId",
}


# ─────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────

class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class FlightVerifierResult(BaseModel):
    score: float
    match: bool
    agent_url: str
    gt_url: str
    details: dict


# ─────────────────────────────────────────────────────────────
# VERIFIER CLASS
# ─────────────────────────────────────────────────────────────


@beartype
class TripFlightUrlMatch(BaseMetric):
    """Trip.com Flight URL verifier.

    Compares departure/arrival cities, dates, flight type, cabin class,
    and passenger count between agent URL and ground truth URL.
    """

    def __init__(self, gt_url: str | list[str]) -> None:
        super().__init__()
        if isinstance(gt_url, str):
            self.gt_urls = [gt_url]
        else:
            self.gt_urls = gt_url
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details: dict = {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(gt_urls={self.gt_urls})"

    async def reset(self) -> None:
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details = {}

    async def update(self, **kwargs) -> None:
        inputs: InputDict = kwargs
        url = inputs.get("url", "")

        if not url:
            return

        parsed = urlparse(url.strip())
        domain = (parsed.hostname or "").lower()
        if domain and not self._is_valid_trip_domain(domain):
            logger.debug(f"Ignoring non-Trip.com URL: {url}")
            return

        # Must be a flights page
        if "/flights/" not in parsed.path.lower():
            logger.debug(f"Ignoring non-flights URL: {url}")
            return

        if self._found_match:
            return

        self._agent_url = url

        for gt_url in self.gt_urls:
            match, details = self._urls_match(url, gt_url)
            if match:
                self._found_match = True
                self._matched_gt_url = gt_url
                self._match_details = details
                logger.info(f"Flight match found: {url[:100]}...")
                return

        logger.info(f"No flight match: {url[:100]}...")

    async def compute(self) -> FinalResult:
        score = 1.0 if self._found_match else 0.0
        return FinalResult(score=score)

    async def compute_detailed(self) -> FlightVerifierResult:
        score = 1.0 if self._found_match else 0.0
        return FlightVerifierResult(
            score=score,
            match=self._found_match,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

    # ──────────────────────────────────────────────────────────
    # DOMAIN VALIDATION
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_valid_trip_domain(domain: str) -> bool:
        domain = domain.lower()
        if domain in VALID_DOMAINS:
            return True
        if domain.endswith(".trip.com"):
            return True
        return False

    # ──────────────────────────────────────────────────────────
    # URL MATCHING
    # ──────────────────────────────────────────────────────────

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Check if two Trip.com flight URLs represent the same search."""
        details: dict[str, Any] = {"mismatches": []}
        try:
            agent_parts = self._parse_flight_url(agent_url)
            gt_parts = self._parse_flight_url(gt_url)

            # 1. Departure city (IATA code, case-insensitive)
            if gt_parts["dcity"]:
                if not agent_parts["dcity"]:
                    details["mismatches"].append(
                        f"Departure city missing (expected '{gt_parts['dcity']}')"
                    )
                    return False, details
                if agent_parts["dcity"] != gt_parts["dcity"]:
                    details["mismatches"].append(
                        f"Departure city: '{agent_parts['dcity']}' vs '{gt_parts['dcity']}'"
                    )
                    return False, details

            # 2. Arrival city
            if gt_parts["acity"]:
                if not agent_parts["acity"]:
                    details["mismatches"].append(
                        f"Arrival city missing (expected '{gt_parts['acity']}')"
                    )
                    return False, details
                if agent_parts["acity"] != gt_parts["acity"]:
                    details["mismatches"].append(
                        f"Arrival city: '{agent_parts['acity']}' vs '{gt_parts['acity']}'"
                    )
                    return False, details

            # 3. Departure date
            if gt_parts["ddate"]:
                if not agent_parts["ddate"]:
                    details["mismatches"].append(
                        f"Departure date missing (expected '{gt_parts['ddate']}')"
                    )
                    return False, details
                if agent_parts["ddate"] != gt_parts["ddate"]:
                    details["mismatches"].append(
                        f"Departure date: '{agent_parts['ddate']}' vs '{gt_parts['ddate']}'"
                    )
                    return False, details

            # 4. Return date (only for round-trip)
            if gt_parts["rdate"]:
                if not agent_parts["rdate"]:
                    details["mismatches"].append(
                        f"Return date missing (expected '{gt_parts['rdate']}')"
                    )
                    return False, details
                if agent_parts["rdate"] != gt_parts["rdate"]:
                    details["mismatches"].append(
                        f"Return date: '{agent_parts['rdate']}' vs '{gt_parts['rdate']}'"
                    )
                    return False, details

            # 5. Flight type (rt / ow)
            if gt_parts["flighttype"]:
                if not agent_parts["flighttype"]:
                    details["mismatches"].append(
                        f"Flight type missing (expected '{gt_parts['flighttype']}')"
                    )
                    return False, details
                if agent_parts["flighttype"] != gt_parts["flighttype"]:
                    details["mismatches"].append(
                        f"Flight type: '{agent_parts['flighttype']}' vs '{gt_parts['flighttype']}'"
                    )
                    return False, details

            # 6. Cabin class
            if gt_parts["class"]:
                if not agent_parts["class"]:
                    details["mismatches"].append(
                        f"Cabin class missing (expected '{gt_parts['class']}')"
                    )
                    return False, details
                if agent_parts["class"] != gt_parts["class"]:
                    details["mismatches"].append(
                        f"Cabin class: '{agent_parts['class']}' vs '{gt_parts['class']}'"
                    )
                    return False, details

            # 7. Passengers
            if gt_parts["quantity"]:
                if not agent_parts["quantity"]:
                    details["mismatches"].append(
                        f"Passengers missing (expected '{gt_parts['quantity']}')"
                    )
                    return False, details
                if agent_parts["quantity"] != gt_parts["quantity"]:
                    details["mismatches"].append(
                        f"Passengers: '{agent_parts['quantity']}' vs '{gt_parts['quantity']}'"
                    )
                    return False, details

            return True, details

        except Exception as e:
            logger.error(f"Error comparing flight URLs: {e}")
            details["mismatches"].append(f"Parse error: {str(e)}")
            return False, details

    # ──────────────────────────────────────────────────────────
    # URL PARSING
    # ──────────────────────────────────────────────────────────

    def _parse_flight_url(self, url: str) -> dict:
        """Parse a Trip.com flight URL into normalized components."""
        url = unquote(url.strip())
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)

        return {
            "dcity": self._get_param(query, "dcity").lower(),
            "acity": self._get_param(query, "acity").lower(),
            "ddate": self._get_param(query, "ddate"),
            "rdate": self._get_param(query, "rdate"),
            "flighttype": self._get_param(query, "flighttype").lower(),
            "class": self._get_param(query, "class").lower(),
            "quantity": self._get_param(query, "quantity"),
        }

    @staticmethod
    def _get_param(query: dict, *keys: str) -> str:
        for key in keys:
            if key in query and query[key]:
                return query[key][0]
            key_lower = key.lower()
            if key_lower in query and query[key_lower]:
                return query[key_lower][0]
        return ""


# ─────────────────────────────────────────────────────────────
# TASK CONFIG GENERATION
# ─────────────────────────────────────────────────────────────

def generate_task_config(
    task: str,
    location: str,
    timezone: str,
    gt_url: list[str] | None = None,
    ground_truth_url: str | None = None,
    timestamp: int | None = None,
    url: str = "https://us.trip.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Trip.com flight URL matching.

    Args:
        task: Task description. May contain {placeholder} tokens.
        location: User location string.
        timezone: IANA timezone string.
        gt_url: Ground-truth URL(s).
        ground_truth_url: Single GT URL (alternative to gt_url).
        timestamp: Unix timestamp. None means "now".
        url: Starting URL.
        values: Placeholder-key → relative-date expression mapping.
    """
    if gt_url is None and ground_truth_url is not None:
        gt_url = [ground_truth_url]
    elif isinstance(gt_url, str):
        gt_url = [gt_url]
    elif gt_url is None:
        raise ValueError("Either 'gt_url' or 'ground_truth_url' must be provided.")

    values = values or {}
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    resolved_placeholders, _ = initialize_placeholder_map(user_metadata, values)

    # Render {placeholder} tokens in task text
    rendered_task = render_task_statement(task, resolved_placeholders)

    # Substitute resolved dates into gt_url strings
    rendered_gt_urls: list[str] = []
    for u in gt_url:
        rendered_u = u
        for placeholder_key, (_, dates) in resolved_placeholders.items():
            template = "{" + placeholder_key + "}"
            if template in rendered_u and dates:
                rendered_u = rendered_u.replace(template, dates[0])
        rendered_gt_urls.append(rendered_u)

    eval_target = get_import_path(TripFlightUrlMatch)
    eval_config = {"_target_": eval_target, "gt_url": rendered_gt_urls}
    return BaseTaskConfig(
        url=url, task=rendered_task, user_metadata=user_metadata, eval_config=eval_config
    )