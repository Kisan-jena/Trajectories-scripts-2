import re
from datetime import datetime
from itertools import product
from typing import TypedDict
from urllib.parse import (
    parse_qs,
    unquote_plus,
    urlparse,
)
from beartype import beartype
from loguru import logger
from pydantic import BaseModel
from pydantic import Field
from navi_bench.base import (
    BaseMetric,
    BaseTaskConfig,
    get_import_path,
)

from navi_bench.dates import (
    initialize_placeholder_map,
    initialize_user_metadata,
    render_task_statement,
)

# =====================================================================
# TYPES
# =====================================================================

class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class AirbnbVerifierResult(BaseModel):
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = Field(default_factory=dict)


# =====================================================================
# FILTER INITIALIZATIONS
# =====================================================================

MULTI_VALUE_FILTERS = [

    # Homes
    "amenities",
    "kg_and_tags",
    "tier_ids",
    "host_languages",
    "room_types",
    "l2_property_type_ids",

    # Experiences
    "activity_listing_tiers",
    "kg_or_tags",
    "experience_time_of_day",
    "experience_languages",
    "experience_accessibility_tags",
    "experience_traveler_type_tags",

    # Services
    "service_time_of_day",
    "service_languages",
    "service_accessibility_tags",

    # Flexible dates
    "flexible_trip_lengths",
    "flexible_trip_dates",
]

BOOLEAN_FILTERS = [
    "ib",
    "flexible_cancellation",
    "guest_favorite",
]

NUMERIC_FILTERS = [

    # Guests
    "adults",
    "children",
    "infants",
    "pets",

    # Prices
    "price_min",
    "price_max",

    # Homes
    "min_bedrooms",
    "min_beds",
    "min_bathrooms",

    # Experiences / Services
    "min_duration",
    "max_duration",

    # Flexible dates
    "monthly_length",
    "flexible_date_search_filter_type",
]

STRING_FILTERS = [

    # Identity
    "place_id",

    # Dates
    "date_picker_type",
    "checkin",
    "checkout",

    # Flexible dates
    "monthly_start_date",
    "monthly_end_date",

    # Services
    "service_type_tag",
]

IGNORED_PARAMS = {
    "source",
    "modal",
    "search_mode",
    "pagination_search",
    "tab_id",
    "refinement_paths",
    "search_type",
    "federated_search_session_id",
}

NON_FILTER_FIELDS = {
    "place_id",
    "date_picker_type",
    "location_slug",
    "monthly_start_date",
    "monthly_end_date",
    "monthly_length",
    "flexible_trip_lengths",
    "flexible_trip_dates",
    "flexible_date_search_filter_type",
}

ALLOWED_EXTRA_FILTERS = {
    "checkin",
    "checkout",
    "adults",
    "children",
    "infants",
}
# =====================================================================
# VERIFIER
# =====================================================================

@beartype
class AirbnbUrlMatch(BaseMetric):

    def __init__(
        self,
        gt_url: str | list[str],
    ) -> None:

        super().__init__()

        if isinstance(gt_url, str):
            self.gt_urls = [gt_url]
        else:
            self.gt_urls = gt_url

        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._match_details: dict = {}

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

        if domain != "airbnb.com" and not domain.endswith(".airbnb.com"):

            logger.debug(
                f"Ignoring non-airbnb URL: {url}"
            )

            return

        if self._found_match:
            return

        self._agent_url = url

        for gt_url in self.gt_urls:

            match, details = self._urls_match(
                url,
                gt_url,
            )

            if match:

                self._found_match = True
                self._matched_gt_url = gt_url
                self._match_details = details

                return

    def __repr__(self) -> str:

        return (
            f"{self.__class__.__name__}"
            f"(gt_urls={self.gt_urls})"
        )

    async def compute(self) -> FinalResult:

        return FinalResult(
            score=1.0 if self._found_match else 0.0
        )

    async def compute_detailed(
        self,
    ) -> AirbnbVerifierResult:

        return AirbnbVerifierResult(
            score=1.0 if self._found_match else 0.0,
            match=self._found_match,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

    def _detect_extra_filters(
        self,
        agent: dict,
        gt: dict,
    ) -> list[str]:

        extras = []

        all_filters = (
            MULTI_VALUE_FILTERS
            + BOOLEAN_FILTERS
            + NUMERIC_FILTERS
            + STRING_FILTERS
        )

        for key in all_filters:

            if (
                key in ALLOWED_EXTRA_FILTERS
                or key in NON_FILTER_FIELDS
            ):
                continue

            gt_val = gt.get(key)
            agent_val = agent.get(key)

            # -------------------------
            # MULTI VALUE
            # -------------------------

            if key in MULTI_VALUE_FILTERS:

                if (
                    not gt_val
                    and agent_val
                ):
                    extras.append(
                        f"extra filter applied: {key}={agent_val}"
                    )

            # -------------------------
            # BOOLEAN / NUMERIC
            # -------------------------

            elif key in BOOLEAN_FILTERS + NUMERIC_FILTERS:

                if (
                    gt_val is None
                    and agent_val is not None
                ):
                    extras.append(
                        f"extra filter applied: {key}={agent_val}"
                    )

            # -------------------------
            # STRING
            # -------------------------

            else:

                if (
                    not gt_val
                    and agent_val
                ):
                    extras.append(
                        f"extra filter applied: {key}={agent_val}"
                    )

        return extras
    
# =====================================================================
# URL MATCH
# =====================================================================

    def _urls_match(
        self,
        agent_url: str,
        gt_url: str,
    ) -> tuple[bool, dict]:

        try:

            agent = self._parse_url(agent_url)
            gt = self._parse_url(gt_url)

            mismatches = []

            if (
                agent["page_type"]
                != gt["page_type"]
            ):

                mismatches.append(
                    f"page_type mismatch: "
                    f"{agent['page_type']} "
                    f"vs "
                    f"{gt['page_type']}"
                )

            mismatches.extend(
                self._match_page_identity(
                    agent,
                    gt,
                )
            )

            mismatches.extend(
                self._match_filters(
                    agent,
                    gt,
                )
            )

            mismatches.extend(
                self._detect_extra_filters(
                    agent,
                    gt,
                )
            )

            if mismatches:

                return False, {
                    "mismatches": mismatches
                }

            return True, {}

        except Exception as e:

            logger.error(e)

            return False, {
                "mismatches": [str(e)]
            }

# =====================================================================
# PAGE TYPE DETECTION
# =====================================================================

    def _detect_page_type(
        self,
        parsed,
    ) -> str:

        path = parsed.path.lower().strip("/")

        parts = self._split_path_parts(path)

        if not parts:
            return "homepage"

        if (
            len(parts) >= 3
            and parts[0] == "s"
        ):

            if parts[-1] == "homes":
                return "homes_search"

            if parts[-1] == "experiences":
                return "experiences_search"

            if parts[-1] == "services":
                return "services_search"

        if (
            len(parts) >= 2
            and parts[0] == "experiences"
        ):

            if re.search(
                r"\d+",
                parts[1],
            ):
                return "experience_detail"

        if (
            len(parts) == 1
            and parts[0] == "services"
        ):
            return "services_page"

        return "unknown"

# =====================================================================
# URL PARSER
# =====================================================================

    def _parse_url(
        self,
        url: str,
    ) -> dict[str, object]:

        parsed = urlparse(url)

        raw_query = parse_qs(
            parsed.query,
            keep_blank_values=True,
        )

        query = {
            k: v
            for k, v in raw_query.items()
            if k not in IGNORED_PARAMS
        }

        page_type = self._detect_page_type(
            parsed
        )

        result = {
            "page_type": page_type,
        }

        result.update(
            self._parse_filters(query)
        )

        path = parsed.path.lower().strip("/")

        parts = self._split_path_parts(path)

        # --------------------------------------------------
        # SEARCH PAGES
        # --------------------------------------------------

        if page_type in {
            "homes_search",
            "experiences_search",
            "services_search",
        }:

            location_slug = ""

            if (
                len(parts) >= 3
                and parts[0] == "s"
            ):
                location_slug = parts[1]

            result["location_slug"] = (
                self._normalize_location_slug(
                    location_slug
                )
            )

        # --------------------------------------------------
        # EXPERIENCE DETAIL
        # --------------------------------------------------

        elif page_type == "experience_detail":

            experience_id = ""

            if len(parts) > 1:

                match = re.search(
                    r"\d+",
                    parts[1],
                )

                if match:
                    experience_id = match.group()

            result["experience_id"] = experience_id

        return result

# =====================================================================
# FILTER PARSER
# =====================================================================

    def _parse_filters(
        self,
        query: dict,
    ) -> dict:

        # --------------------------------------------------
        # PRICE NORMALIZATION
        # --------------------------------------------------

        price_min = None

        for key in (
            "price_min",
            "experience_price_min",
            "service_price_min",
        ):

            val = self._to_int(
                self._get_param(
                    query,
                    key,
                )
            )

            if val is not None:
                price_min = val
                break

        price_max = None

        for key in (
            "price_max",
            "experience_price_max",
            "service_price_max",
        ):

            val = self._to_int(
                self._get_param(
                    query,
                    key,
                )
            )

            if val is not None:
                price_max = val
                break

        return {

            # --------------------------------------------------
            # IDENTITY
            # --------------------------------------------------

            "place_id": self._get_param(
                query,
                "place_id",
            ),

            # --------------------------------------------------
            # DATES
            # --------------------------------------------------

            "date_picker_type": self._get_param(
                query,
                "date_picker_type",
            ).lower(),

            "checkin": self._get_param(
                query,
                "checkin",
            ),

            "checkout": self._get_param(
                query,
                "checkout",
            ),

            # --------------------------------------------------
            # FLEXIBLE DATES
            # --------------------------------------------------

            "flexible_date_search_filter_type":
                self._to_int(
                    self._get_param(
                        query,
                        "flexible_date_search_filter_type",
                    )
                ),

            "flexible_trip_lengths":
                self._parse_multi_value_list(
                    query.get(
                        "flexible_trip_lengths[]",
                        [],
                    )
                ),

            "flexible_trip_dates":
                self._parse_multi_value_list(
                    query.get(
                        "flexible_trip_dates[]",
                        [],
                    )
                ),

            "monthly_start_date":
                self._get_param(
                    query,
                    "monthly_start_date",
                ),

            "monthly_end_date":
                self._get_param(
                    query,
                    "monthly_end_date",
                ),

            "monthly_length":
                self._to_int(
                    self._get_param(
                        query,
                        "monthly_length",
                    )
                ),

            # --------------------------------------------------
            # GUESTS
            # --------------------------------------------------

            "adults": self._to_int(
                self._get_param(
                    query,
                    "adults",
                )
            ),

            "children": self._to_int(
                self._get_param(
                    query,
                    "children",
                )
            ),

            "infants": self._to_int(
                self._get_param(
                    query,
                    "infants",
                )
            ),

            "pets": self._to_int(
                self._get_param(
                    query,
                    "pets",
                )
            ),

            # --------------------------------------------------
            # PRICE
            # --------------------------------------------------

            "price_min": price_min,
            "price_max": price_max,

            # --------------------------------------------------
            # HOME FILTERS
            # --------------------------------------------------

            "min_bedrooms": self._to_int(
                self._get_param(
                    query,
                    "min_bedrooms",
                )
            ),

            "min_beds": self._to_int(
                self._get_param(
                    query,
                    "min_beds",
                )
            ),

            "min_bathrooms": self._to_int(
                self._get_param(
                    query,
                    "min_bathrooms",
                )
            ),

            "amenities":
                self._parse_multi_value_list(
                    query.get(
                        "amenities[]",
                        [],
                    )
                ),

            "kg_and_tags":
                self._parse_multi_value_list(
                    query.get(
                        "kg_and_tags[]",
                        [],
                    )
                ),

            "tier_ids":
                self._parse_multi_value_list(
                    query.get(
                        "tier_ids[]",
                        [],
                    )
                ),

            "host_languages":
                self._parse_multi_value_list(
                    query.get(
                        "host_languages[]",
                        [],
                    )
                ),

            "room_types":
                self._parse_multi_value_list(
                    query.get(
                        "room_types[]",
                        [],
                    )
                ),

            "ib":
                self._to_bool(
                    self._get_param(
                        query,
                        "ib",
                    )
                ),

            "flexible_cancellation":
                self._to_bool(
                    self._get_param(
                        query,
                        "flexible_cancellation",
                    )
                ),

            "guest_favorite":
                self._to_bool(
                    self._get_param(
                        query,
                        "guest_favorite",
                    )
                ),
            
            "l2_property_type_ids":
                self._parse_multi_value_list(
                    query.get(
                        "l2_property_type_ids[]",
                        [],
                    )
                ),

            # --------------------------------------------------
            # EXPERIENCE FILTERS
            # --------------------------------------------------

            "activity_listing_tiers":
                self._parse_multi_value_list(
                    query.get(
                        "activity_listing_tiers[]",
                        [],
                    )
                ),

            "kg_or_tags":
                self._parse_multi_value_list(
                    query.get(
                        "kg_or_tags[]",
                        [],
                    )
                ),

            "experience_time_of_day":
                self._parse_multi_value_list(
                    query.get(
                        "experience_time_of_day[]",
                        [],
                    )
                ),

            "experience_languages":
                self._parse_multi_value_list(
                    query.get(
                        "experience_languages[]",
                        [],
                    )
                ),

            "experience_accessibility_tags":
                self._parse_multi_value_list(
                    query.get(
                        "experience_accessibility_tags[]",
                        [],
                    )
                ),

            "experience_traveler_type_tags":
                self._parse_multi_value_list(
                    query.get(
                        "experience_traveler_type_tags[]",
                        [],
                    )
                ),

            # --------------------------------------------------
            # SERVICE FILTERS
            # --------------------------------------------------

            "service_type_tag":
                self._get_param(
                    query,
                    "service_type_tag",
                ),

            "service_time_of_day":
                self._parse_multi_value_list(
                    query.get(
                        "service_time_of_day[]",
                        [],
                    )
                ),

            "service_languages":
                self._parse_multi_value_list(
                    query.get(
                        "service_languages[]",
                        [],
                    )
                ),

            "service_accessibility_tags":
                self._parse_multi_value_list(
                    query.get(
                        "service_accessibility_tags[]",
                        [],
                    )
                ),

            # --------------------------------------------------
            # EXPERIENCE / SERVICE
            # --------------------------------------------------

            "min_duration":
                self._to_int(
                    self._get_param(
                        query,
                        "min_duration",
                    )
                ),

            "max_duration":
                self._to_int(
                    self._get_param(
                        query,
                        "max_duration",
                    )
                ),
        }

# =====================================================================
# PAGE IDENTITY MATCHER
# =====================================================================

    def _match_page_identity(
        self,
        agent: dict,
        gt: dict,
    ) -> list[str]:

        mismatches = []

        page_type = gt["page_type"]

        if page_type in {
            "homes_search",
            "experiences_search",
            "services_search",
        }:

            agent_slug = self._normalize_location_slug(
                agent.get("location_slug", "")
            )

            gt_slug = self._normalize_location_slug(
                gt.get("location_slug", "")
            )

            if not self._locations_match(
                agent_slug,
                gt_slug,
            ):

                mismatches.append(
                    f"location mismatch: "
                    f"{agent_slug} "
                    f"vs "
                    f"{gt_slug}"
                )

        elif page_type == "experience_detail":

            if (
                agent.get("experience_id")
                != gt.get("experience_id")
            ):

                mismatches.append(
                    f"experience mismatch: "
                    f"{agent.get('experience_id')} "
                    f"vs "
                    f"{gt.get('experience_id')}"
                )

        return mismatches

# =====================================================================
# FILTER MATCHER
# =====================================================================

    def _match_filters(
        self,
        agent: dict,
        gt: dict,
    ) -> list[str]:

        mismatches = []

        # ---------------------------------------------------
        # MULTI VALUE FILTERS
        # STRICT EQUALITY
        # ---------------------------------------------------

        for key in MULTI_VALUE_FILTERS:

            gt_vals = gt.get(
                key,
                set(),
            )

            agent_vals = agent.get(
                key,
                set(),
            )

            if not gt_vals:
                continue

            if agent_vals != gt_vals:

                mismatches.append(
                    f"{key} mismatch: "
                    f"{agent_vals} "
                    f"vs "
                    f"{gt_vals}"
                )

        # ---------------------------------------------------
        # BOOLEAN FILTERS
        # ---------------------------------------------------

        for key in BOOLEAN_FILTERS:

            gt_val = gt.get(key)

            if gt_val is None:
                continue

            agent_val = agent.get(key)

            if agent_val != gt_val:

                mismatches.append(
                    f"{key} mismatch: "
                    f"{agent_val} "
                    f"vs "
                    f"{gt_val}"
                )

        # ---------------------------------------------------
        # NUMERIC FILTERS
        # ---------------------------------------------------

        for key in NUMERIC_FILTERS:

            gt_val = gt.get(key)

            if gt_val is None:
                continue

            agent_val = agent.get(key)

            if agent_val != gt_val:

                mismatches.append(
                    f"{key} mismatch: "
                    f"{agent_val} "
                    f"vs "
                    f"{gt_val}"
                )

        # ---------------------------------------------------
        # STRING FILTERS
        # ---------------------------------------------------

        for key in STRING_FILTERS:

            gt_val = gt.get(
                key,
                "",
            )

            if not gt_val:
                continue

            agent_val = agent.get(
                key,
                "",
            )

            if agent_val != gt_val:

                mismatches.append(
                    f"{key} mismatch: "
                    f"{agent_val} "
                    f"vs "
                    f"{gt_val}"
                )

        return mismatches

# =====================================================================
# HELPERS
# =====================================================================

    def _locations_match(
        self,
        agent_slug: str,
        gt_slug: str,
    ) -> bool:

        agent_slug = self._normalize_location_slug(
            agent_slug
        )

        gt_slug = self._normalize_location_slug(
            gt_slug
        )

        if agent_slug == gt_slug:
            return True

        agent_parts = agent_slug.split("--")
        gt_parts = gt_slug.split("--")

        return agent_parts[0] == gt_parts[0]

    def _normalize_location_slug(
        self,
        slug: str,
    ) -> str:

        return (
            self._decode_twice(slug)
            .strip()
            .lower()
        )

    @staticmethod
    def _get_param(
        query: dict,
        key: str,
    ) -> str:

        if key in query and query[key]:

            return (
                query[key][0]
                .strip()
            )

        return ""

    @staticmethod
    def _to_bool(
        value: str,
    ) -> bool | None:

        if not value:
            return None

        return value.strip().lower() in {
            "true",
            "1",
        }

    @staticmethod
    def _to_int(
        value: str,
    ) -> int | None:

        try:
            return int(value)

        except Exception:
            return None

    def _decode_twice(
        self,
        value: str,
    ) -> str:

        try:

            return unquote_plus(
                unquote_plus(value)
            )

        except Exception:

            return unquote_plus(value)

    def _normalize_token(
        self,
        value: str,
    ) -> str:

        return (
            self._decode_twice(value)
            .strip()
            .lower()
        )

    def _parse_multi_value_list(
        self,
        values: list[str],
    ) -> set[str]:

        if not values:
            return set()

        output = set()

        for value in values:

            decoded = (
                self._decode_twice(value)
            )

            parts = re.split(
                r"[|,]",
                decoded,
            )

            for part in parts:

                part = (
                    self._normalize_token(
                        part
                    )
                )

                if part:
                    output.add(part)

        return output

    def _split_path_parts(
        self,
        path: str,
    ) -> list[str]:

        parts = [
            p
            for p in path.split("/")
            if p
        ]

        locale_pattern = re.compile(
            r"^[a-z]{2}(-[a-z]{2})?$",
            re.IGNORECASE,
        )

        if (
            parts
            and locale_pattern.match(
                parts[0]
            )
        ):

            parts = parts[1:]

        return parts

    def _normalize_location_slug(
        self,
        slug: str,
    ) -> str:

        return (
            self._decode_twice(slug)
            .strip()
            .lower()
        )

# =====================================================================
# TASK CONFIG
# =====================================================================

def generate_task_config(
    task: str,
    location: str,
    timezone: str,
    gt_url: list[str] | None = None,
    ground_truth_url: str | None = None,
    timestamp: int | None = None,
    url: str = "https://www.airbnb.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:

    if (
        gt_url is None
        and ground_truth_url
        is not None
    ):

        gt_url = [
            ground_truth_url
        ]

    elif isinstance(
        gt_url,
        str,
    ):

        gt_url = [gt_url]

    elif gt_url is None:

        raise ValueError(
            "Either gt_url "
            "or "
            "ground_truth_url "
            "must be provided."
        )

    values = values or {}

    user_metadata = (
        initialize_user_metadata(
            timezone,
            location,
            timestamp,
        )
    )

    (
        resolved_placeholders,
        _,
    ) = initialize_placeholder_map(
        user_metadata,
        values,
    )

    rendered_task = (
        render_task_statement(
            task,
            resolved_placeholders,
        )
    )

    rendered_gt_urls: list[str] = []

    for template in gt_url:

        placeholders_in_template = {
            k: dates
            for k, (_, dates) in resolved_placeholders.items()
            if any(
                token in template
                for token in (
                    f"{{{k}}}",
                    f"{{{k}Day}}",
                    f"{{{k}Month}}",
                    f"{{{k}Year}}",
                )
            )
        }

        if not placeholders_in_template:

            rendered_gt_urls.append(
                template
            )

            continue

        keys = list(
            placeholders_in_template.keys()
        )

        date_lists = list(
            placeholders_in_template.values()
        )

        for combination in product(
            *date_lists
        ):

            rendered_u = template

            for k, v in zip(
                keys,
                combination,
            ):

                rendered_u = (
                    rendered_u.replace(
                        f"{{{k}}}",
                        v,
                    )
                )

                try:

                    dt = datetime.strptime(
                        v,
                        "%Y-%m-%d",
                    )

                    replacements = {
                        f"{{{k}Day}}":
                            str(dt.day),

                        f"{{{k}Month}}":
                            str(dt.month),

                        f"{{{k}Year}}":
                            str(dt.year),
                    }

                    for (
                        token,
                        value,
                    ) in replacements.items():

                        if token in rendered_u:

                            rendered_u = (
                                rendered_u.replace(
                                    token,
                                    value,
                                )
                            )

                except Exception:

                    pass

            rendered_gt_urls.append(
                rendered_u
            )

    rendered_gt_urls = list(
        set(rendered_gt_urls)
    )


    eval_target = (
        get_import_path(
            AirbnbUrlMatch
        )
    )

    eval_config = {
        "_target_": eval_target,
        "gt_url": rendered_gt_urls,
    }

    return BaseTaskConfig(
        url=url,
        task=rendered_task,
        user_metadata=user_metadata,
        eval_config=eval_config,
    )