import re
from typing import TypedDict
from urllib.parse import (
    parse_qs,
    unquote_plus,
    urlparse,
)

from beartype import beartype
from loguru import logger
from pydantic import BaseModel

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


class GoatVerifierResult(BaseModel):
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =====================================================================
# FILTER INITIALIZATIONS
# =====================================================================

MULTI_VALUE_FILTERS = [
    "brands",
    "categories",
    "types",
    "activities",
    "genders",
    "sizes",
    "conditions",
    "colors",
    "years",
]

BOOLEAN_FILTERS = [
    "instant_ship",
    "under_retail",
    "in_stock",
    "sale",
]

NUMERIC_FILTERS = [
    "price_min",
    "price_max",
    "release_date_start",
    "release_date_end",
]

STRING_FILTERS = [
    "sort_type",
]

IGNORED_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "pageNumber",
    "pageSlug",
    "taxonomies",
}

PRODUCT_PREFIXES = {
    "sneakers",
}


# =====================================================================
# VERIFIER
# =====================================================================
@beartype
class GoatUrlMatch(BaseMetric):

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
        self._last_gt_url = ""
        self._match_details: dict = {}

    async def reset(self) -> None:
        self._found_match = False
        self._agent_url = ""
        self._matched_gt_url = ""
        self._last_gt_url = ""
        self._match_details = {}

    async def update(self, **kwargs) -> None:

        inputs: InputDict = kwargs
        url = inputs.get("url", "")

        if not url:
            return

        parsed = urlparse(url.strip())
        domain = (parsed.hostname or "").lower()

        if not domain.endswith("goat.com"):
            logger.debug(f"Ignoring non-goat URL: {url}")
            return

        # ALWAYS track latest URL (IMPORTANT FIX)
        self._agent_url = url
        
        self._matched_gt_url = ""

        for gt_url in self.gt_urls:

            self._last_gt_url = gt_url

            match, details = self._urls_match(url, gt_url)

            if match:
                self._found_match = True
                self._matched_gt_url = gt_url
                self._match_details = details
                return
            else:
                # keep last mismatch details for debugging
                self._match_details = details

    async def compute(self) -> FinalResult:
        final_valid, _ = self._validate_final_url(self._agent_url)
        return FinalResult(
            score=1.0 if (self._matched_gt_url and final_valid) else 0.0
        )

    async def compute_detailed(self) -> GoatVerifierResult:

        final_valid, final_errors = self._validate_final_url(self._agent_url)

        all_mismatches = list(self._match_details.get("mismatches", []))

        if final_errors:
            all_mismatches.extend(final_errors)

        is_pass = bool(self._matched_gt_url) and final_valid

        return GoatVerifierResult(
            score=1.0 if is_pass else 0.0,
            match=is_pass,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url or self._last_gt_url,
            details={"mismatches": all_mismatches},
        )

    # =========================================================
    # FINAL URL VALIDATION (NEW CORE RULE)
    # =========================================================

    def _validate_final_url(self, final_url: str) -> tuple[bool, list[str]]:

        parsed = self._parse_url(final_url)

        errors = []

        # Build allowed filter map from ALL GTs
        allowed_filters = {}

        for gt_url in self.gt_urls:
            gt = self._parse_url(gt_url)

            for k, v in gt.items():
                if k in ["page_type"]:
                    continue
                if v not in [None, "", set(), []]:
                    allowed_filters[k] = v

        # sort is always allowed
        allowed_filters["sort_type"] = "ALLOWED"

        # Check for illegal extra filters
        for key, value in parsed.items():

            if key in ["page_type"]:
                continue

            # ignore empty values
            if value in [None, "", set(), []]:
                continue

            # allow sort always
            if key == "sort_type":
                continue

            # MUST exist in at least one GT
            supported = False

            for gt_url in self.gt_urls:
                gt = self._parse_url(gt_url)

                if key in gt and gt[key] not in [None, "", set(), []]:
                    supported = True
                    break

            if not supported:
                errors.append(f"extra filter not allowed: {key}")

        return (len(errors) == 0), errors

    # =========================================================
    # EXISTING LOGIC (UNCHANGED BUT SAFE)
    # =========================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:

        try:
            agent = self._parse_url(agent_url)
            gt = self._parse_url(gt_url)

            mismatches = []

            # PAGE TYPE
            if agent["page_type"] != gt["page_type"]:
                mismatches.append(
                    f"page_type mismatch: {agent['page_type']} vs {gt['page_type']}"
                )

            # PAGE IDENTITY
            mismatches.extend(self._match_page_identity(agent, gt))

            # FILTERS
            mismatches.extend(self._match_filters(agent, gt))

            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}

# =====================================================================
# PAGE TYPE DETECTION
# =====================================================================

    def _detect_page_type(
        self,
        parsed,
    ) -> str:

        path = parsed.path.lower().strip("/")

        # HOMEPAGE
        if path == "":
            return "homepage"

        parts = self._split_path_parts(path)

        if not parts:
            return "homepage"

        # SEARCH
        if parts[0] == "search":
            return "search"

        # COLLECTION
        if parts[0] == "collections":
            return "collection"

        # BRAND
        if parts[0] == "brand":
            return "brand"

        # PRODUCT
        if len(parts) == 2:

            parent = parts[0]
            slug = parts[1]

            if (
                parent in PRODUCT_PREFIXES
                and slug.count("-") >= 3
            ):
                return "product"

        # CATEGORY
        return "category"

# =====================================================================
# URL PARSER
# =====================================================================

    def _parse_url(
        self,
        url: str,
    ) -> dict:

        parsed = urlparse(url)

        raw_query = parse_qs(parsed.query)

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

        # FILTERS
        result.update(
            self._parse_filters(query)
        )

        # PAGE SPECIFIC DATA
        path = parsed.path.lower().strip("/")

        parts = self._split_path_parts(path)

        # SEARCH
        if page_type == "search":

            result["query"] = (
                self._decode_twice(
                    self._get_param(
                        query,
                        "query",
                    )
                ).lower()
            )

        # COLLECTION
        elif page_type == "collection":

            result["collection_slug"] = (
                parts[1]
                if len(parts) > 1
                else ""
            )

        # BRAND
        elif page_type == "brand":

            result["brand_slug"] = (
                parts[1]
                if len(parts) > 1
                else ""
            )

        # PRODUCT
        elif page_type == "product":

            result["product_slug"] = (
                parts[-1]
                if parts
                else ""
            )

        # CATEGORY
        elif page_type == "category":

            result["category_path"] = [
                p.strip().lower()
                for p in parts
            ]

        return result

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

        # SEARCH
        if page_type == "search":

            gt_tokens = self._normalize_query(
                gt.get("query", "")
            )

            agent_tokens = self._normalize_query(
                agent.get("query", "")
            )

            if gt_tokens:

                if not agent_tokens:

                    mismatches.append(
                        "query missing"
                    )

                elif not self._tokens_match(
                    gt_tokens,
                    agent_tokens,
                ):

                    mismatches.append(
                        f"query mismatch: "
                        f"{agent_tokens} "
                        f"vs "
                        f"{gt_tokens}"
                    )

        # COLLECTION
        elif page_type == "collection":

            if (
                agent.get("collection_slug")
                != gt.get("collection_slug")
            ):

                mismatches.append(
                    "collection mismatch"
                )

        # BRAND
        elif page_type == "brand":

            if (
                agent.get("brand_slug")
                != gt.get("brand_slug")
            ):

                mismatches.append(
                    "brand mismatch"
                )

        # PRODUCT
        elif page_type == "product":

            if (
                agent.get("product_slug")
                != gt.get("product_slug")
            ):

                mismatches.append(
                    "product mismatch"
                )

        # CATEGORY
        elif page_type == "category":

            agent_path = agent.get(
                "category_path",
                [],
            )

            gt_path = gt.get(
                "category_path",
                [],
            )

            if gt_path:

                if (
                    agent_path[: len(gt_path)]
                    != gt_path
                ):

                    mismatches.append(
                        "category mismatch"
                    )

        return mismatches

# =====================================================================
# FILTER MATCHER
# =====================================================================

    def _brands_compatible(
        self,
        gt_brand: str,
        agent_brand: str,
    ) -> bool:
        """Check if two brands are compatible/equivalent."""
        
        # Exact match or token equivalent
        if self._token_equivalent(gt_brand, agent_brand):
            return True
        
        # Check if one brand name is contained in the other (case-insensitive)
        # E.g., "casio" is in "g-shock by casio" → compatible
        gt_lower = gt_brand.lower()
        agent_lower = agent_brand.lower()
        
        if gt_lower in agent_lower or agent_lower in gt_lower:
            return True
        
        return False

    def _match_filters(
        self,
        agent: dict,
        gt: dict,
    ) -> list[str]:

        mismatches = []

        # ---------------------------------------------------
        # MULTI VALUE FILTERS
        # ---------------------------------------------------

        for key in MULTI_VALUE_FILTERS:

            gt_vals = gt.get(key, set())

            agent_vals = agent.get(key, set())

            if not gt_vals:
                continue

            if not agent_vals:

                mismatches.append(
                    f"{key} missing"
                )

                continue

            for gt_val in gt_vals:

                # Use brand-specific matching for "brands" key
                if key == "brands":
                    match_fn = self._brands_compatible
                else:
                    match_fn = self._token_equivalent

                if not any(
                    match_fn(
                        gt_val,
                        agent_val,
                    )
                    for agent_val in agent_vals
                ):

                    mismatches.append(
                        f"{key} mismatch: "
                        f"{agent_vals} "
                        f"vs "
                        f"{gt_vals}"
                    )

                    break

        # ---------------------------------------------------
        # BOOLEAN FILTERS
        # ---------------------------------------------------

        for key in BOOLEAN_FILTERS:

            gt_val = gt.get(key)

            agent_val = agent.get(key)

            if gt_val is None:
                continue

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

            agent_val = agent.get(key)

            if gt_val is None:
                continue

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

            gt_val = gt.get(key, "")

            agent_val = agent.get(key, "")

            if not gt_val:
                continue

            if agent_val != gt_val:

                mismatches.append(
                    f"{key} mismatch: "
                    f"{agent_val} "
                    f"vs "
                    f"{gt_val}"
                )
        return mismatches

# =====================================================================
# FILTER PARSER
# =====================================================================

    def _parse_filters(
        self,
        query: dict,
    ) -> dict:

        return {

            # ---------------------------------------------------
            # MULTI VALUE
            # ---------------------------------------------------

            "brands": self._parse_multi_value(
                self._get_param(
                    query,
                    "brands",
                )
            ),

            "categories": self._parse_multi_value(
                self._get_param(
                    query,
                    "categories",
                )
            ),

            "types": self._parse_multi_value(
                self._get_param(
                    query,
                    "types",
                )
            ),

            "activities": self._parse_multi_value(
                self._get_param(
                    query,
                    "activities",
                )
            ),

            "genders": self._parse_multi_value(
                self._get_param(
                    query,
                    "genders",
                )
            ),

            "sizes": self._parse_multi_value(
                self._get_param(
                    query,
                    "sizes",
                )
            ),

            "conditions": self._parse_multi_value(
                self._get_param(
                    query,
                    "conditions",
                )
            ),

            "colors": self._parse_multi_value(
                self._get_param(
                    query,
                    "colors",
                )
            ),

            "years": self._parse_multi_value(
                self._get_param(
                    query,
                    "years",
                )
            ),

            # ---------------------------------------------------
            # PRICE
            # ---------------------------------------------------

            "price_min": self._to_int(
                self._get_param(
                    query,
                    "priceMin",
                )
            ),

            "price_max": self._to_int(
                self._get_param(
                    query,
                    "priceMax",
                )
            ),

            # ---------------------------------------------------
            # BOOLEAN
            # ---------------------------------------------------

            "instant_ship": self._to_bool(
                self._get_param(
                    query,
                    "instantShip",
                )
            ),

            "under_retail": self._to_bool(
                self._get_param(
                    query,
                    "underRetail",
                )
            ),

            "in_stock": self._to_bool(
                self._get_param(
                    query,
                    "inStock",
                )
            ),

            "sale": self._to_bool(
                self._get_param(
                    query,
                    "sale",
                )
            ),

            # ---------------------------------------------------
            # SORT
            # ---------------------------------------------------

            "sort_type": self._get_param(
                query,
                "sortType",
            ).lower(),

            # ---------------------------------------------------
            # RELEASE DATES
            # ---------------------------------------------------

            "release_date_start": self._to_int(
                self._get_param(
                    query,
                    "releaseDateStart",
                )
            ),

            "release_date_end": self._to_int(
                self._get_param(
                    query,
                    "releaseDateEnd",
                )
            ),
        }

# =====================================================================
# HELPERS
# =====================================================================

    @staticmethod
    def _get_param(
        query: dict,
        key: str,
    ) -> str:

        if key in query and query[key]:
            return query[key][0].strip()

        return ""

    @staticmethod
    def _to_bool(
        value: str,
    ) -> bool | None:

        if not value:
            return None

        return (
            value.strip().lower()
            == "true"
        )

    @staticmethod
    def _to_int(value: str):

        try:
            return int(value)
        except:
            return None

    def _decode_twice(
        self,
        value: str,
    ) -> str:

        try:
            return unquote_plus(
                unquote_plus(value)
            )
        except:
            return unquote_plus(value)

    def _parse_multi_value(
        self,
        value: str,
    ) -> set[str]:

        if not value:
            return set()

        value = (
            self._decode_twice(value)
            .lower()
        )

        parts = re.split(
            r"[|,]",
            value,
        )

        return {
            p.strip()
            for p in parts
            if p.strip()
        }

    def _normalize_query(
        self,
        query: str,
    ) -> set[str]:

        if not query:
            return set()

        query = (
            unquote_plus(query)
            .lower()
            .strip()
        )

        tokens = re.split(
            r"[+\s]+",
            query,
        )

        stopwords = {
            "for",
            "and",
            "the",
            "with",
            "a",
            "an",
            "of",
        }

        return {
            t
            for t in tokens
            if t and t not in stopwords
        }

    def _tokens_match(
        self,
        gt_tokens: set[str],
        agent_tokens: set[str],
    ) -> bool:

        for gt in gt_tokens:

            if any(
                self._token_equivalent(
                    gt,
                    a,
                )
                for a in agent_tokens
            ):
                continue

            return False

        return True

    def _token_equivalent(
        self,
        a: str,
        b: str,
    ) -> bool:

        if a == b:
            return True

        # ies ↔ y
        if (
            a.endswith("ies")
            and a[:-3] + "y" == b
        ):
            return True

        if (
            b.endswith("ies")
            and b[:-3] + "y" == a
        ):
            return True

        # es endings
        es_endings = (
            "xes",
            "ches",
            "shes",
            "zes",
            "ses",
        )

        if (
            a.endswith(es_endings)
            and a[:-2] == b
        ):
            return True

        if (
            b.endswith(es_endings)
            and b[:-2] == a
        ):
            return True

        # simple plurals
        def valid_s_plural(x, y):

            return (
                x.endswith("s")
                and not x.endswith(
                    ("ss", "us", "is")
                )
                and x[:-1] == y
            )

        if valid_s_plural(a, b):
            return True

        if valid_s_plural(b, a):
            return True

        return False

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
            r"^[a-z]{2}-[a-z]{2}$",
            re.IGNORECASE,
        )

        if parts and locale_pattern.match(parts[0]):
            parts = parts[1:]

        return parts

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
    url: str = "https://www.goat.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """
    Minimal task config for GOAT URL verification.
    """

    if (
        gt_url is None
        and ground_truth_url is not None
    ):
        gt_url = [ground_truth_url]

    elif isinstance(gt_url, str):
        gt_url = [gt_url]

    elif gt_url is None:

        raise ValueError(
            "Either 'gt_url' or "
            "'ground_truth_url' "
            "must be provided."
        )

    values = values or {}

    user_metadata = initialize_user_metadata(
        timezone,
        location,
        timestamp,
    )

    resolved_placeholders, _ = (
        initialize_placeholder_map(
            user_metadata,
            values,
        )
    )

    rendered_task = render_task_statement(
        task,
        resolved_placeholders,
    )

    rendered_gt_urls: list[str] = []

    for template in gt_url:

        rendered_u = template

        for key, (_, vals) in (
            resolved_placeholders.items()
        ):

            placeholder = f"{{{key}}}"

            if (
                placeholder in rendered_u
                and vals
            ):

                rendered_u = rendered_u.replace(
                    placeholder,
                    vals[0],
                )

        rendered_gt_urls.append(
            rendered_u
        )

    eval_target = get_import_path(
        GoatUrlMatch
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
