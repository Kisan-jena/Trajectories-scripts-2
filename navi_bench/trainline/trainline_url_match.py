"""Trainline URL Match verifier for train search navigation.

This module provides functionality to verify AI agent navigation on Trainline
by comparing the agent's final URL against expected ground truth URLs.

The verifier handles all Trainline URL variations including:
- Search results path: /book/results
- Station identifiers: urn:trainline:generic:loc:{CODE}{NUM}{COUNTRY}
- Journey types: single, return, openReturn
- Date/time: ISO datetime YYYY-MM-DDTHH:MM:SS
- Passengers: encoded as DOBs (passengers[]=YYYY-MM-DD), one per person;
  OMITTED when default 1 adult (browser-verified Apr 2026)
- Passenger categories: Adults (16+), Children (0-15) based on travel date
- Domain: thetrainline.com (with/without www prefix)

Browser-Verified Patterns (Apr 2026 on thetrainline.com):
  Search path: /book/results
  Journey type: journeySearchType=single|return|openReturn
  Origin: origin=urn:trainline:generic:loc:EUS1444gb
  Destination: destination=urn:trainline:generic:loc:MAN2968gb
  Outward date: outwardDate=2026-05-01T13:15:00
  Outward type: outwardDateType=departAfter
  Inward date: inwardDate=2026-05-05T14:30:00 (return only)
  Inward type: inwardDateType=departAfter (return only)
  Passengers: passengers[]=1991-04-13 (DOB per traveller)
              ABSENT when 1-adult default → verifier assumes 1 adult
  Language: lang=en-us (ignored)
  Transport: transportModes[]=mixed (ignored)
  Tabs: selectedTab=train (ignored)

Station URN examples (browser-verified Apr 2026):
  IMPORTANT: Trainline assigns varying numeric suffixes to the same CRS station.
  For example, Kings Cross was observed as both KGX4832gb and KGX6121gb.
  The verifier therefore matches on CRS PREFIX only (ignoring the numeric suffix).

  London (Any)                → urn:trainline:generic:loc:182gb
  Manchester (Any)            → urn:trainline:generic:loc:115gb
  Glasgow (Any)               → urn:trainline:generic:loc:81gb
  London St Pancras Intl      → urn:trainline:generic:loc:STP1555gb
  London Kings Cross          → urn:trainline:generic:loc:KGX6121gb
  London Euston               → urn:trainline:generic:loc:EUS1444gb
  London Paddington           → urn:trainline:generic:loc:PAD3087gb
  London Victoria             → urn:trainline:generic:loc:VIC5426gb
  London Waterloo             → urn:trainline:generic:loc:WAT5598gb
  London Liverpool Street     → urn:trainline:generic:loc:LST6965gb
  Manchester Piccadilly       → urn:trainline:generic:loc:MAN2968gb
  Edinburgh (Waverley)        → urn:trainline:generic:loc:EDB9328gb
  Birmingham New Street       → urn:trainline:generic:loc:BHM1127gb
  Leeds                       → urn:trainline:generic:loc:LDS8487gb
  Glasgow Central             → urn:trainline:generic:loc:GLC9012gb
  York                        → urn:trainline:generic:loc:YRK8263gb
  Bristol Temple Meads        → urn:trainline:generic:loc:BRI3231gb
  Liverpool Lime Street       → urn:trainline:generic:loc:LIV2246gb
  Newcastle                   → urn:trainline:generic:loc:NCL7728gb
  Brighton                    → urn:trainline:generic:loc:BTN5268gb
  Cambridge                   → urn:trainline:generic:loc:CBG7022gb
  Oxford                      → urn:trainline:generic:loc:OXF3115gb
  Paris (Any)                 → urn:trainline:generic:loc:4916

Note: Travel class (Standard / 1st class) is selected on the results page,
NOT encoded in the URL. Therefore class verification is out of scope.
"""

import asyncio
import functools
import re
from datetime import date
from pathlib import Path
from typing import Any
from typing_extensions import TypedDict
from urllib.parse import parse_qs, unquote, urlparse

from beartype import beartype
from loguru import logger
from pydantic import BaseModel

from navi_bench.base import BaseMetric, BaseTaskConfig, get_import_path
from navi_bench.dates import (
    initialize_placeholder_map,
    initialize_user_metadata,
    render_task_statement,
)


# =============================================================================
# TypedDicts
# =============================================================================


class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class TrainlineVerifierResult(BaseModel):
    """Detailed verification result for Trainline URL matching."""

    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


class MultiCandidateQuery(TypedDict, total=False):
    """Query definition for deterministic Trainline info-gathering tasks.

    URLs are validated via CRS-prefix matching on origin/destination.
    Passenger counts are verified via DOM-scraped summary text.
    """
    # URL that the agent should navigate to
    urls: list[str] | None
    # Expected station names (DOM-level, not URN)
    origin_station: str | None
    destination_station: str | None
    # Expected passenger summary (scraped from DOM)
    passenger_summary: str | None
    # Expected counts
    adults: int | None
    children: int | None
    # Journey type
    journey_type: str | None  # 'single' or 'return'


class InfoDict(TypedDict, total=False):
    """Info scraped from the Trainline DOM by trainline_info_gathering.js."""
    url: str
    source: str
    pageType: str
    antiBotStatus: str
    # Search header
    originStation: str
    destinationStation: str
    passengerSummary: str
    adults: int
    children: int
    outwardDate: str
    journeyType: str
    # Journey card
    price: float | None
    departTime: str | None
    arrivalTime: str | None
    duration: int | None
    operator: str
    changes: int | None
    info: str
    # URL metadata
    urlOrigin: str
    urlDestination: str
    urlOutwardDate: str
    urlInwardDate: str
    urlJourneyType: str
    urlPassengerCount: int


class InfoGatheringResult(BaseModel):
    """Result from TrainlineInfoGathering.compute()."""
    score: float
    n_queries: int
    n_covered: int
    queries: list[list[MultiCandidateQuery]]
    is_query_covered: list[bool]


# =============================================================================
# CONSTANTS
# =============================================================================

# Valid Trainline domain patterns
VALID_BASE_DOMAINS = {
    "thetrainline.com",
}

# Regional / alternate domains
REGIONAL_DOMAINS = {
    "trainline.com",
    "trainline.eu",
    "trainline.fr",
    "trainline.it",
    "trainline.es",
    "trainline.de",
}

# Query parameters to IGNORE during comparison
IGNORED_PARAMS = {
    "lang",
    "selectedTab",
    "splitSave",
    "directSearch",
    "dpiCookieId",
    "partnershipType",
    "partnershipSelection",
    "selectedOutward",
    "selectedInward",
    "transportModes[]",
    "transportmodes[]",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "ref",
    "gclid",
    "msclkid",
    "fbclid",
    "searchId",
    "wcid",
    "source",
    "cmpid",
    "redirected",
    "type",
    "qd",
}

# URN prefix for Trainline station identifiers
STATION_URN_PREFIX = "urn:trainline:generic:loc:"

# Journey type normalization
JOURNEY_TYPE_MAP = {
    "single": "single",
    "oneway": "single",
    "one-way": "single",
    "return": "return",
    "roundtrip": "return",
    "round-trip": "return",
    "openreturn": "openReturn",
    "open-return": "openReturn",
    "openReturn": "openReturn",
}

# Adult age threshold: 16+ years old on travel date
ADULT_AGE_THRESHOLD = 16


# =============================================================================
# PARSING HELPERS
# =============================================================================


def _get_param(query: dict, *keys: str) -> str:
    """Get the first non-empty value from query dict for any of the keys.

    Handles both exact keys and case-insensitive fallback.
    """
    for key in keys:
        if key in query and query[key]:
            return query[key][0]
        key_lower = key.lower()
        if key_lower in query and query[key_lower]:
            return query[key_lower][0]
    return ""


def _get_all_params(query: dict, *keys: str) -> list[str]:
    """Get ALL values for any of the keys (for passengers[] arrays).

    Handles the array format: passengers[]=DOB1&passengers[]=DOB2
    """
    for key in keys:
        if key in query and query[key]:
            return query[key]
        key_lower = key.lower()
        if key_lower in query and query[key_lower]:
            return query[key_lower]
    return []


def _normalize_station_urn(urn: str) -> str:
    """Normalize a Trainline station URN for comparison.

    Handles:
      - Full URN: urn:trainline:generic:loc:EUS1444gb → eus1444gb
      - URL-encoded URN: urn%3Atrainline%3Ageneric%3Aloc%3AEUS1444gb → eus1444gb
      - Bare code: EUS1444gb → eus1444gb

    Returns lowercased station ID portion only.
    """
    if not urn:
        return ""

    urn = unquote(urn).strip()

    # Strip the URN prefix if present
    lower_urn = urn.lower()
    prefix_lower = STATION_URN_PREFIX.lower()
    if lower_urn.startswith(prefix_lower):
        return lower_urn[len(prefix_lower):]

    # Already bare code
    return lower_urn


def _extract_crs_prefix(station_id: str) -> str:
    """Extract the CRS (alpha) prefix from a Trainline station ID.

    Browser-verified (Apr 2026): Trainline assigns varying numeric suffixes
    to the same station. For example, Kings Cross appears as both
    KGX4832gb and KGX6121gb. The CRS prefix (KGX) is the stable identifier.

    Patterns:
      eus1444gb  → eus
      kgx4832gb  → kgx
      kgx6121gb  → kgx  (same station, different suffix)
      182gb      → 182gb  (city-level, no alpha prefix → return as-is)
      115gb      → 115gb  (city-level, no alpha prefix → return as-is)
      4916       → 4916   (European, numeric-only → return as-is)

    Returns:
      CRS prefix (lowercased) for stations with alpha prefixes.
      Original ID for city-level / numeric-only IDs.
    """
    if not station_id:
        return ""

    # Match pattern: {ALPHA_PREFIX}{DIGITS}{OPTIONAL_COUNTRY}
    # e.g., eus1444gb, kgx4832gb, man2968gb
    m = re.match(r"^([a-z]+)(\d+)(gb)?$", station_id)
    if m:
        return m.group(1)

    # Numeric-only (city-level or European): 182gb, 115gb, 4916
    return station_id


def _stations_match(agent_id: str, gt_id: str) -> bool:
    """Compare two normalized station IDs using CRS prefix matching.

    This handles the case where Trainline assigns different numeric
    suffixes to the same physical station:
      KGX4832gb vs KGX6121gb → both have CRS prefix 'kgx' → MATCH
      EUS1444gb vs EUS1444gb → exact match → MATCH
      EUS1444gb vs MAN2968gb → eus vs man → NO MATCH
      182gb vs 182gb         → numeric city-level → exact match → MATCH
      115gb vs 182gb         → different cities → NO MATCH
    """
    if not agent_id or not gt_id:
        return False

    # Fast path: exact match
    if agent_id == gt_id:
        return True

    # Extract CRS prefixes and compare
    agent_crs = _extract_crs_prefix(agent_id)
    gt_crs = _extract_crs_prefix(gt_id)

    return agent_crs == gt_crs


def _extract_date_only(datetime_str: str) -> str:
    """Extract the date portion from a Trainline ISO datetime string.

    Handles:
      - 2026-05-01T13:15:00 → 2026-05-01
      - 2026-05-01T13%3A15%3A00 → 2026-05-01  (URL-decoded)
      - 2026-05-01 → 2026-05-01
      - Empty → ""
    """
    if not datetime_str:
        return ""

    datetime_str = unquote(datetime_str).strip()

    # Try to parse ISO datetime
    # Handle format: YYYY-MM-DDTHH:MM:SS
    t_match = re.match(r"^(\d{4}-\d{2}-\d{2})", datetime_str)
    if t_match:
        return t_match.group(1)

    return datetime_str


def _normalize_journey_type(raw: str) -> str:
    """Normalize journey type to canonical value."""
    if not raw:
        return ""
    return JOURNEY_TYPE_MAP.get(raw.lower().strip(), raw.lower().strip())


def _dob_to_age(dob_str: str, travel_date_str: str) -> int:
    """Calculate age from DOB on the travel date.

    Args:
        dob_str: Date of birth in YYYY-MM-DD format
        travel_date_str: Travel date in YYYY-MM-DD format

    Returns:
        Age in years on the travel date
    """
    try:
        dob = date.fromisoformat(dob_str)
        travel = date.fromisoformat(travel_date_str)
        age = travel.year - dob.year
        if (travel.month, travel.day) < (dob.month, dob.day):
            age -= 1
        return max(0, age)
    except (ValueError, TypeError):
        # If we can't parse, assume adult
        return 30


def _classify_passengers(
    dob_list: list[str], travel_date_str: str
) -> dict[str, int]:
    """Classify passenger DOBs into adults and children counts.

    Args:
        dob_list: List of DOB strings (YYYY-MM-DD)
        travel_date_str: Travel date (YYYY-MM-DD) for age calculation

    Returns:
        dict with keys: adults, children, total
    """
    adults = 0
    children = 0

    for dob in dob_list:
        age = _dob_to_age(dob.strip(), travel_date_str)
        if age >= ADULT_AGE_THRESHOLD:
            adults += 1
        else:
            children += 1

    return {
        "adults": adults,
        "children": children,
        "total": adults + children,
    }


# =============================================================================
# URL PARSER
# =============================================================================


def parse_trainline_url(url: str) -> dict[str, Any]:
    """Parse a Trainline search URL into normalized components.

    Trainline search URL anatomy (browser-verified Apr 2026):
      /book/results?
        journeySearchType=single|return
        &origin=urn:trainline:generic:loc:EUS1444gb
        &destination=urn:trainline:generic:loc:MAN2968gb
        &outwardDate=2026-05-01T13:15:00
        &outwardDateType=departAfter
        [&inwardDate=2026-05-05T14:30:00]
        [&inwardDateType=departAfter]
        &passengers[]=1991-04-13
        [&passengers[]=2018-06-15]
        [&lang=en-us]

    Returns dict with keys:
      origin, destination, outward_date, inward_date,
      journey_type, passenger_dobs, adults, children, total_passengers
    """
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)

    result: dict[str, Any] = {
        "origin": "",
        "destination": "",
        "outward_date": "",
        "inward_date": "",
        "journey_type": "",
        "passenger_dobs": [],
        "adults": 0,
        "children": 0,
        "total_passengers": 0,
    }

    # Journey type
    journey_type_raw = _get_param(query, "journeySearchType", "journeysearchtype")
    result["journey_type"] = _normalize_journey_type(journey_type_raw)

    # Origin station
    origin_urn = _get_param(query, "origin")
    result["origin"] = _normalize_station_urn(origin_urn)

    # Destination station
    dest_urn = _get_param(query, "destination")
    result["destination"] = _normalize_station_urn(dest_urn)

    # Outward date (extract date only, ignore time)
    outward_raw = _get_param(query, "outwardDate", "outwarddate")
    result["outward_date"] = _extract_date_only(outward_raw)

    # Inward date (return trips only)
    inward_raw = _get_param(query, "inwardDate", "inwarddate")
    result["inward_date"] = _extract_date_only(inward_raw)

    # Passengers (array of DOBs)
    passenger_dobs = _get_all_params(query, "passengers[]", "passengers%5B%5D")
    result["passenger_dobs"] = [dob.strip() for dob in passenger_dobs if dob.strip()]

    # Classify passengers using outward travel date
    if result["passenger_dobs"] and result["outward_date"]:
        pax = _classify_passengers(result["passenger_dobs"], result["outward_date"])
        result["adults"] = pax["adults"]
        result["children"] = pax["children"]
        result["total_passengers"] = pax["total"]
    elif result["passenger_dobs"]:
        result["total_passengers"] = len(result["passenger_dobs"])
    else:
        # Browser-verified (Apr 2026): when 1-adult default is used,
        # Trainline OMITS passengers[] from the URL entirely.
        # Assume 1 adult, 0 children.
        result["adults"] = 1
        result["children"] = 0
        result["total_passengers"] = 1

    return result


# =============================================================================
# VERIFIER CLASS
# =============================================================================


@beartype
class TrainlineUrlMatch(BaseMetric):
    """Comprehensive Trainline URL verifier for train searches.

    Browser-Verified (Apr 2026 on thetrainline.com):
    - Search path: /book/results
    - Station IDs: urn:trainline:generic:loc:{CODE}{NUM}{COUNTRY}
    - Journey types: single, return, openReturn
    - Dates: ISO datetime (date portion only matters)
    - Passengers: DOBs → classified as adults (16+) / children (0-15)
    - Domain variations: thetrainline.com, trainline.eu, etc.
    """

    def __init__(self, gt_url: str | list[str]) -> None:
        """
        Args:
            gt_url: Ground truth URL(s). If a list is provided, matching ANY
                    URL in the list counts as a match (OR semantics).
        """
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
        """Reset the match state for new evaluation."""
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details = {}

    async def update(self, **kwargs) -> None:
        """Update with new URL to check against ground truth."""
        inputs: InputDict = kwargs
        url = inputs.get("url", "")

        if not url:
            logger.debug("Empty URL provided")
            return

        # Validate domain
        parsed = urlparse(url.strip())
        domain = (parsed.hostname or "").lower()
        if domain and not self._is_valid_trainline_domain(domain):
            logger.debug(f"Ignoring non-Trainline URL: {url}")
            return

        # Don't overwrite after match
        if self._found_match:
            return

        self._agent_url = url

        for gt_url in self.gt_urls:
            match, details = self._urls_match(url, gt_url)
            if match:
                self._found_match = True
                self._matched_gt_url = gt_url
                self._match_details = details
                logger.info(f"Match found: {url[:100]}...")
                return

        logger.info(f"No match found: {url[:100]}...")

    async def compute(self) -> FinalResult:
        """Compute final score (1.0 = match, 0.0 = no match)."""
        score = 1.0 if self._found_match else 0.0
        result = FinalResult(score=score)
        logger.info(f"Final score: {score}")
        return result

    async def compute_detailed(self) -> TrainlineVerifierResult:
        """Compute detailed result with match info."""
        score = 1.0 if self._found_match else 0.0
        return TrainlineVerifierResult(
            score=score,
            match=self._found_match,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

    # ========================================================================
    # DOMAIN VALIDATION
    # ========================================================================

    @staticmethod
    def _is_valid_trainline_domain(domain: str) -> bool:
        """Check if domain is a valid Trainline domain.

        Accepts:
        - Exact matches: thetrainline.com
        - www prefix: www.thetrainline.com
        - Regional: trainline.eu, trainline.fr, etc.
        - Any subdomain of the above
        """
        domain = domain.lower().rstrip(".")

        # Direct match on known domains
        for base in VALID_BASE_DOMAINS:
            if domain == base or domain.endswith("." + base):
                return True

        # Regional domains
        for regional in REGIONAL_DOMAINS:
            if domain == regional or domain.endswith("." + regional):
                return True

        # Generic pattern: anything.trainline.xxx or anything.thetrainline.xxx
        if re.match(r"^([\w-]+\.)*(the)?trainline\.\w+(\.\w+)?$", domain):
            return True

        return False

    # ========================================================================
    # URL MATCHING
    # ========================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        """Compare two Trainline search URLs."""
        details: dict[str, Any] = {"mismatches": [], "extra_params": []}

        try:
            agent = parse_trainline_url(agent_url)
            gt = parse_trainline_url(gt_url)

            # 1. Origin station (CRS prefix matching)
            if gt["origin"]:
                if not agent["origin"]:
                    details["mismatches"].append(
                        f"Origin missing (expected '{gt['origin']}')"
                    )
                    return False, details
                if not _stations_match(agent["origin"], gt["origin"]):
                    details["mismatches"].append(
                        f"Origin: '{agent['origin']}' vs '{gt['origin']}'"
                    )
                    return False, details

            # 2. Destination station (CRS prefix matching)
            if gt["destination"]:
                if not agent["destination"]:
                    details["mismatches"].append(
                        f"Destination missing (expected '{gt['destination']}')"
                    )
                    return False, details
                if not _stations_match(agent["destination"], gt["destination"]):
                    details["mismatches"].append(
                        f"Destination: '{agent['destination']}' vs '{gt['destination']}'"
                    )
                    return False, details

            # 3. Outward date (date only, time ignored)
            if gt["outward_date"]:
                if not agent["outward_date"]:
                    details["mismatches"].append(
                        f"Outward date missing (expected '{gt['outward_date']}')"
                    )
                    return False, details
                if agent["outward_date"] != gt["outward_date"]:
                    details["mismatches"].append(
                        f"Outward date: '{agent['outward_date']}' vs '{gt['outward_date']}'"
                    )
                    return False, details

            # 4. Inward date (return trips only)
            if gt["inward_date"]:
                if not agent["inward_date"]:
                    details["mismatches"].append(
                        f"Inward date missing (expected '{gt['inward_date']}')"
                    )
                    return False, details
                if agent["inward_date"] != gt["inward_date"]:
                    details["mismatches"].append(
                        f"Inward date: '{agent['inward_date']}' vs '{gt['inward_date']}'"
                    )
                    return False, details

            # 5. Journey type — strict: fail if GT specifies but agent omits
            if gt["journey_type"]:
                if not agent["journey_type"]:
                    details["mismatches"].append(
                        f"Journey type: agent missing, expected '{gt['journey_type']}'"
                    )
                    return False, details
                if agent["journey_type"] != gt["journey_type"]:
                    details["mismatches"].append(
                        f"Journey type: '{agent['journey_type']}' vs '{gt['journey_type']}'"
                    )
                    return False, details

            # 6. Adults count — always verify (no > 0 guard; default 1
            #    must still match to prevent extra-passenger loopholes)
            if agent["adults"] != gt["adults"]:
                details["mismatches"].append(
                    f"Adults: {agent['adults']} vs {gt['adults']}"
                )
                return False, details

            # 7. Children count — always verify (closing the loophole
            #    where gt children=0 was skipped, letting extra children pass)
            if agent["children"] != gt["children"]:
                details["mismatches"].append(
                    f"Children: {agent['children']} vs {gt['children']}"
                )
                return False, details

            return True, details

        except Exception as e:
            logger.error(f"Error comparing URLs: {e}")
            details["mismatches"].append(f"Parse error: {str(e)}")
            return False, details


# =============================================================================
# TASK CONFIG GENERATION
# =============================================================================


def generate_task_config(
    task: str,
    location: str,
    timezone: str,
    gt_url: list[str] | None = None,
    ground_truth_url: str | None = None,
    timestamp: int | None = None,
    url: str = "https://www.thetrainline.com/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for Trainline URL matching.

    Accepts either ``gt_url`` (list of strings) or ``ground_truth_url``
    (single string) for backward compat.

    Args:
        task: Task description. May contain ``{placeholder}`` tokens.
        location: User location string.
        timezone: IANA timezone string.
        gt_url: Ground-truth URL(s).
        ground_truth_url: Single GT URL (alternative to gt_url).
        timestamp: Unix timestamp. ``None`` means "now".
        url: Starting URL.
        values: Placeholder-key → relative-date expression mapping.
    """
    # Resolve gt_url from either parameter
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

    eval_target = get_import_path(TrainlineUrlMatch)
    eval_config = {"_target_": eval_target, "gt_url": rendered_gt_urls}
    return BaseTaskConfig(
        url=url,
        task=rendered_task,
        user_metadata=user_metadata,
        eval_config=eval_config,
    )


# =============================================================================
# INFO GATHERING — DOM-BASED VERIFIER
# =============================================================================


class TrainlineInfoGathering(BaseMetric):
    """DOM + URL hybrid verifier for Trainline search tasks.

    Unlike TrainlineUrlMatch (pure URL comparison), this verifier:
    1. Injects trainline_info_gathering.js into the browser page
    2. Scrapes station names, passenger summary, prices from the DOM
    3. Compares scraped data against expected queries

    This matches the pattern used by Kayak, VividSeats, Ticketmaster, etc.
    The seniors' CSV format (with ``queries``, ``passenger_summary_scraped``,
    ``origin_station``, ``destination_station``) targets this verifier.
    """

    def __init__(self, queries: list[list[MultiCandidateQuery]]) -> None:
        super().__init__()
        self.queries = queries
        self._all_infos: list[list[InfoDict]] = []
        self._is_query_covered: list[bool] = [False] * len(queries)
        self._navigation_stack: list[dict] = []
        self._tracked_pages: set = set()

    @functools.cached_property
    def js_script(self) -> str:
        with open(Path(__file__).parent / "trainline_info_gathering.js", "r") as f:
            return f.read()

    async def reset(self) -> None:
        self._all_infos = []
        self._is_query_covered = [False] * len(self.queries)
        self._navigation_stack = []
        self._tracked_pages = set()

    def attach_to_context(self, context) -> None:
        """Attach page-navigation listeners to automatically scrape new pages."""
        async def track_page(page) -> None:
            page_id = id(page)
            if page_id in self._tracked_pages:
                return
            self._tracked_pages.add(page_id)

            async def on_frame_navigated(frame):
                if frame != page.main_frame:
                    return
                if "trainline" not in frame.url:
                    return
                try:
                    logger.info(f"[NAV] Trainline: {frame.url[:80]}...")
                    await self.update(page=page)
                except Exception:
                    pass

            page.on(
                "framenavigated",
                lambda f: asyncio.create_task(on_frame_navigated(f)),
            )

        for page in context.pages:
            asyncio.create_task(track_page(page))
        context.on("page", lambda p: asyncio.create_task(track_page(p)))

    async def update(self, **kwargs) -> None:
        page = kwargs["page"]
        content = await page.content()

        if any(s in content.lower() for s in [
            "px-captcha", "challenge-running", "verify you are human",
        ]):
            logger.error("Agent blocked by Trainline Anti-Bot.")

        all_frame_infos: list[InfoDict] = []
        for frame in page.frames:
            try:
                frame_infos = await asyncio.wait_for(
                    frame.evaluate(self.js_script), timeout=3.0
                )
                if frame_infos and isinstance(frame_infos, list):
                    all_frame_infos.extend(frame_infos)
            except Exception:
                pass

        # Deduplication (includes operator to avoid dropping different-operator
        # tickets that share the same departure time and price)
        unique_infos = []
        seen = set()
        for info in all_frame_infos:
            key = (
                f"{info.get('source')}-{info.get('departTime')}-"
                f"{info.get('price')}-{info.get('originStation')}-"
                f"{info.get('operator', '')}"
            )
            if key not in seen:
                seen.add(key)
                unique_infos.append(info)

        infos = unique_infos

        if infos:
            print(f"\n[SCRAPED DATA FROM: {page.url[:60]}...]", flush=True)
            for i, item in enumerate(infos[:10], 1):
                price = item.get("price", "N/A")
                origin = item.get("originStation", "?")
                dest = item.get("destinationStation", "?")
                pax = item.get("passengerSummary", "?")
                depart = item.get("departTime", "XX:XX")
                arrive = item.get("arrivalTime", "XX:XX")
                print(
                    f"  {i}. {origin} → {dest} | {pax} | "
                    f"{depart}-{arrive} | £{price}",
                    flush=True,
                )

        page_type = infos[0].get("pageType", "unknown") if infos else "unknown"
        anti_bot = infos[0].get("antiBotStatus", "unknown") if infos else "unknown"

        self._all_infos.append(infos)

        base_url = page.url.split("?")[0]
        page_entry = {
            "url": page.url,
            "base_url": base_url,
            "page_type": page_type,
            "anti_bot": anti_bot,
            "infos": infos,
        }

        existing_idx = next(
            (
                i
                for i, e in enumerate(self._navigation_stack)
                if e["base_url"] == base_url and e["page_type"] == page_type
            ),
            None,
        )
        if existing_idx is not None:
            self._navigation_stack[existing_idx] = page_entry
        else:
            self._navigation_stack.append(page_entry)

    async def compute(self) -> InfoGatheringResult:
        for page_visit in reversed(self._navigation_stack):
            if page_visit["anti_bot"] != "clear":
                continue
            if page_visit["page_type"] in ["train_results"]:
                for i, alternative_conditions in enumerate(self.queries):
                    if self._is_query_covered[i]:
                        continue
                    for info in page_visit["infos"]:
                        if self._check_alternative_conditions(
                            i, alternative_conditions, info
                        ):
                            self._is_query_covered[i] = True
                            break

        n_queries = len(self.queries)
        n_covered = sum(self._is_query_covered)
        return InfoGatheringResult(
            score=n_covered / max(n_queries, 1),
            n_queries=n_queries,
            n_covered=n_covered,
            queries=self.queries,
            is_query_covered=self._is_query_covered,
        )

    def _check_alternative_conditions(
        self,
        i: int,
        alternative_conditions: list[MultiCandidateQuery],
        info: InfoDict,
    ) -> bool:
        for cond in alternative_conditions:
            if self._check_query(cond, info):
                return True
        return False

    @classmethod
    def _check_query(cls, query: MultiCandidateQuery, info: InfoDict) -> bool:
        """Check if a single DOM-scraped info dict satisfies one query."""

        # 1. Origin station name (DOM text, fuzzy substring)
        if q_origin := query.get("origin_station"):
            info_origin = (info.get("originStation") or "").lower()
            if q_origin.lower() not in info_origin:
                return False

        # 2. Destination station name (DOM text, fuzzy substring)
        if q_dest := query.get("destination_station"):
            info_dest = (info.get("destinationStation") or "").lower()
            if q_dest.lower() not in info_dest:
                return False

        # 3. Passenger summary (DOM text match)
        if q_pax := query.get("passenger_summary"):
            # Parse query summary into counts, compare against JS-scraped counts
            q_adults, q_children = _parse_passenger_summary(q_pax)
            i_adults = info.get("adults", 0)
            i_children = info.get("children", 0)
            if q_adults != i_adults or q_children != i_children:
                return False

        # 4. Explicit adult count
        if "adults" in query and query["adults"] is not None:
            if info.get("adults", 0) != query["adults"]:
                return False

        # 5. Explicit child count
        if "children" in query and query["children"] is not None:
            if info.get("children", 0) != query["children"]:
                return False

        # 6. Journey type
        if q_jtype := query.get("journey_type"):
            info_jtype = (info.get("journeyType") or "").lower()
            if q_jtype.lower() != info_jtype:
                return False

        # 7. URL-based station + date check via CRS prefix (fallback)
        if q_urls := query.get("urls"):
            # The JS scraper returns full URNs, normalize them first
            info_url_origin = _normalize_station_urn(
                info.get("urlOrigin", "")
            )
            info_url_dest = _normalize_station_urn(
                info.get("urlDestination", "")
            )
            info_outward_date = (info.get("urlOutwardDate") or "").split("T")[0]
            info_inward_date = (info.get("urlInwardDate") or "").split("T")[0]

            if info_url_origin or info_url_dest:
                matched_any_url = False
                for expected_url in q_urls:
                    parsed = parse_trainline_url(expected_url)
                    gt_origin = parsed.get("origin", "")
                    gt_dest = parsed.get("destination", "")
                    gt_outward = parsed.get("outward_date", "")
                    gt_inward = parsed.get("inward_date", "")
                    # Station CRS match
                    if gt_origin and info_url_origin:
                        if not _stations_match(info_url_origin, gt_origin):
                            continue
                    if gt_dest and info_url_dest:
                        if not _stations_match(info_url_dest, gt_dest):
                            continue
                    # Date match (date portion only, ignore time)
                    if gt_outward and info_outward_date:
                        if info_outward_date != gt_outward:
                            continue
                    if gt_inward and info_inward_date:
                        if info_inward_date != gt_inward:
                            continue
                    matched_any_url = True
                    break
                if not matched_any_url:
                    return False

        return True


def _parse_passenger_summary(text: str) -> tuple[int, int]:
    """Parse a passenger summary string like '2 adults, 1 child' into (adults, children)."""
    text = text.lower().strip()
    adults = 0
    children = 0

    adult_match = re.search(r"(\d+)\s*adult", text)
    if adult_match:
        adults = int(adult_match.group(1))

    child_match = re.search(r"(\d+)\s*child(?:ren)?", text)
    if child_match:
        children = int(child_match.group(1))

    # Default: if nothing parsed, assume 1 adult
    if adults == 0 and children == 0:
        adults = 1

    return adults, children


# =============================================================================
# DETERMINISTIC TASK CONFIG GENERATION
# =============================================================================


def generate_task_config_deterministic(
    task: str,
    queries: list[list[str]],
    location: str,
    timezone: str,
    passenger_summary_scraped: str = "1 adult",
    origin_station: str = "",
    destination_station: str = "",
    timestamp: int | None = None,
    url: str = "https://www.thetrainline.com/",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """Generate task configuration for deterministic Trainline info-gathering.

    This is the new-format config generator that matches the seniors' CSV
    structure. It uses ``queries`` (list of URL alternatives) instead of
    ``gt_url``, and supports DOM-level fields like ``passenger_summary_scraped``.

    Args:
        task: Natural language task description with ``{placeholder}`` tokens.
        queries: Nested list of GT URLs: ``[["url1"], ["url2"]]``.
                 Each inner list is a set of alternative URLs for one query.
        location: User location (e.g. "United Kingdom").
        timezone: IANA timezone (e.g. "Europe/London").
        passenger_summary_scraped: Expected passenger text from DOM
            (e.g. "2 adults, 1 child").
        origin_station: Expected origin station name from DOM.
        destination_station: Expected destination station name from DOM.
        timestamp: Unix timestamp. ``None`` means "now".
        url: Starting URL for the agent.
        values: Placeholder-key → relative-date expression mapping.
    """
    values = values or {}
    user_metadata = initialize_user_metadata(timezone, location, timestamp)
    resolved_placeholders, _ = initialize_placeholder_map(user_metadata, values)

    # Render {placeholder} tokens in task text
    rendered_task = render_task_statement(task, resolved_placeholders)

    # Resolve dates in query URLs
    rendered_queries: list[list[MultiCandidateQuery]] = []
    adults, children = _parse_passenger_summary(passenger_summary_scraped)

    for url_alternatives in queries:
        resolved_urls = []
        for u in url_alternatives:
            rendered_u = u
            for placeholder_key, (_, dates) in resolved_placeholders.items():
                template = "{" + placeholder_key + "}"
                if template in rendered_u and dates:
                    rendered_u = rendered_u.replace(template, dates[0])
            resolved_urls.append(rendered_u)

        query_condition: MultiCandidateQuery = {
            "urls": resolved_urls,
            "origin_station": origin_station,
            "destination_station": destination_station,
            "passenger_summary": passenger_summary_scraped,
            "adults": adults,
            "children": children,
        }
        rendered_queries.append([query_condition])

    eval_config = {
        "_target_": get_import_path(TrainlineInfoGathering),
        "queries": rendered_queries,
    }
    return BaseTaskConfig(
        url=url,
        task=rendered_task,
        user_metadata=user_metadata,
        eval_config=eval_config,
    )