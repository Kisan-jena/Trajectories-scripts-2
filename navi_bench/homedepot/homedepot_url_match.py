import re
from typing import TypedDict
from urllib.parse import (
    parse_qs,
    unquote,
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


class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class HomeDepotVerifierResult(BaseModel):
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =====================================================================
# QUERY PARAMS TO IGNORE
# =====================================================================

IGNORED_QUERY_PARAMS = {
    "ncni",
    "ncni-5",
    "searchredirect",
    "semantictoken",
    "adobe_mc",
    "cm_mmc",
    "mtc",
    "locstorenum",
    "storeselection",
    "irgwc",
    "cm_sp",
    "source",
    "emtpp",
    "omt",
    "eid",
    "g_store",
    "merch",
    "cm_cat",
    "cm_ven",
}

SEMANTIC_QUERY_KEYS = {
    "ntt",
    "keyword",
    "query",
    "search",
}

ALLOWED_EXTRA_QUERY_PARAMS = {
    "sortby",
}

# =====================================================================
# VERIFIER
# =====================================================================

@beartype
class HomeDepotUrlMatch(BaseMetric):

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

        domain = (
            parsed.hostname or ""
        ).lower()

        if not (
            domain == "homedepot.com"
            or domain.endswith(".homedepot.com")
        ):
            logger.debug(
                f"Ignoring non-homedepot URL: {url}"
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

    async def compute(self) -> FinalResult:

        return FinalResult(
            score=1.0 if self._found_match else 0.0
        )

    async def compute_detailed(
        self,
    ) -> HomeDepotVerifierResult:

        return HomeDepotVerifierResult(
            score=1.0 if self._found_match else 0.0,
            match=self._found_match,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

# =====================================================================
# URL MATCH CORE
# =====================================================================

    def _urls_match(
        self,
        agent_url: str,
        gt_url: str,
    ) -> tuple[bool, dict]:

        try:

            agent = self._parse_url(
                agent_url
            )

            gt = self._parse_url(
                gt_url
            )

            mismatches = []

            # ---------------------------------------------------------
            # PAGE TYPE
            # ---------------------------------------------------------

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

            # ---------------------------------------------------------
            # PAGE IDENTITY
            # ---------------------------------------------------------

            mismatches.extend(
                self._match_page_identity(
                    agent,
                    gt,
                )
            )

            # ---------------------------------------------------------
            # FILTER MATCHING
            # ---------------------------------------------------------

            mismatches.extend(
                self._match_filters(
                    agent,
                    gt,
                )
            )

            # ---------------------------------------------------------
            # RESULT
            # ---------------------------------------------------------

            if mismatches:

                return False, {
                    "mismatches": mismatches,
                    "agent_parsed": agent,
                    "gt_parsed": gt,
                }

            return True, {
                "agent_parsed": agent,
                "gt_parsed": gt,
            }

        except Exception as e:

            logger.exception(e)

            return False, {
                "mismatches": [str(e)]
            }

# =====================================================================
# URL PARSER
# =====================================================================

    def _parse_url(
        self,
        url: str,
    ) -> dict:

        parsed = urlparse(url)

        page_type = (
            self._detect_page_type(
                parsed.path
            )
        )

        # -------------------------------------------------------------
        # QUERY FILTERS
        # combines:
        # - normal query params
        # - Ntt / Ntk path semantic params
        # -------------------------------------------------------------

        query_filters = (
            self._extract_query_filters(
                parsed.query
            )
        )

        path_search_filters = (
            self._extract_search_tokens(
                parsed.path
            )
        )

        for key, vals in (
            path_search_filters.items()
        ):

            query_filters.setdefault(
                key,
                [],
            ).extend(vals)

        result = {
            "page_type": page_type,

            "filters": (
                self._extract_filters_from_path(
                    parsed.path
                )
            ),

            "query_filters": query_filters,
        }

        if page_type == "search":

            result["query"] = (
                self._extract_search_query(
                    parsed.path
                )
            )

        elif page_type == "product":

            result["product_id"] = (
                self._extract_product_id(
                    parsed.path
                )
            )

        elif page_type in {
            "category",
            "brand",
        }:

            result["taxonomy_id"] = (
                self._extract_taxonomy_id(
                    parsed.path
                )
            )

        elif page_type == "services":

            result["service_id"] = (
                self._extract_service_id(
                    parsed.path
                )
            )

        elif page_type == "room":

            result["room_slug"] = (
                self._extract_room_slug(
                    parsed.path
                )
            )

        return result

# =====================================================================
# PAGE TYPE DETECTION
# =====================================================================

    def _detect_page_type(
        self,
        path: str,
    ) -> str:

        path = (
            path.lower()
            .strip("/")
        )

        if path == "":
            return "homepage"

        if path.startswith("p/"):
            return "product"

        if path.startswith(
            "services/"
        ):
            return "services"

        if path.startswith("room/"):
            return "room"

        if path.startswith("s/"):
            return "search"

        if path.startswith("b/"):
            return "category"

        return "unknown"

# =====================================================================
# PAGE IDENTITY MATCHING
# =====================================================================

    def _match_page_identity(
        self,
        agent: dict,
        gt: dict,
    ) -> list[str]:

        mismatches = []

        page_type = gt["page_type"]

        if page_type == "search":

            gt_query = (
                self._normalize_string(
                    gt.get("query", "")
                )
            )

            agent_query = (
                self._normalize_string(
                    agent.get("query", "")
                )
            )

            if gt_query != agent_query:

                mismatches.append(
                    f"search mismatch: "
                    f"{agent_query} "
                    f"vs "
                    f"{gt_query}"
                )

        elif page_type == "product":

            if (
                agent.get("product_id")
                != gt.get("product_id")
            ):

                mismatches.append(
                    "product mismatch"
                )

        elif page_type == "category":

            if (
                agent.get("taxonomy_id")
                != gt.get("taxonomy_id")
            ):

                mismatches.append(
                    "category mismatch"
                )

        elif page_type == "brand":

            if (
                agent.get("taxonomy_id")
                != gt.get("taxonomy_id")
            ):

                mismatches.append(
                    "brand mismatch"
                )

        elif page_type == "services":

            if (
                agent.get("service_id")
                != gt.get("service_id")
            ):

                mismatches.append(
                    "service mismatch"
                )

        elif page_type == "room":

            if (
                agent.get("room_slug")
                != gt.get("room_slug")
            ):

                mismatches.append(
                    "room mismatch"
                )

        return mismatches

# =====================================================================
# FILTER MATCHING
# =====================================================================

    def _match_filters(
        self,
        agent: dict,
        gt: dict,
    ) -> list[str]:

        mismatches = []

        # -------------------------------------------------------------
        # PATH FILTERS
        # -------------------------------------------------------------

        gt_filters = gt.get(
            "filters",
            set(),
        )

        agent_filters = agent.get(
            "filters",
            set(),
        )

        missing_filters = (
            gt_filters - agent_filters
        )

        extra_filters = (
            agent_filters - gt_filters
        )

        if missing_filters:

            mismatches.append(
                f"missing path filters: "
                f"{sorted(missing_filters)}"
            )

        if extra_filters:

            mismatches.append(
                f"extra path filters: "
                f"{sorted(extra_filters)}"
            )

        # -------------------------------------------------------------
        # QUERY FILTERS
        # -------------------------------------------------------------

        gt_query_filters = gt.get(
            "query_filters",
            {},
        )

        agent_query_filters = agent.get(
            "query_filters",
            {},
        )

        for key, gt_vals in (
            gt_query_filters.items()
        ):

            agent_vals = (
                agent_query_filters.get(
                    key,
                    [],
                )
            )

            # ---------------------------------------------------------
            # semantic query matching
            # ---------------------------------------------------------

            if key in SEMANTIC_QUERY_KEYS:

                for gt_val in gt_vals:

                    gt_tokens = (
                        self._normalize_query(
                            gt_val
                        )
                    )

                    matched = False

                    for agent_val in agent_vals:

                        agent_tokens = (
                            self._normalize_query(
                                agent_val
                            )
                        )

                        if self._tokens_match(
                            gt_tokens,
                            agent_tokens,
                        ):

                            matched = True
                            break

                    if not matched:

                        mismatches.append(
                            f"semantic query mismatch: "
                            f"{key}={gt_val}"
                        )

            # ---------------------------------------------------------
            # exact query matching
            # ---------------------------------------------------------

            else:

                for gt_val in gt_vals:

                    if gt_val not in agent_vals:

                        mismatches.append(
                            f"missing query filter: "
                            f"{key}={gt_val}"
                        )
        
        # ---------------------------------------------------------
        # Reject extra query filters
        # (except allowed sort params)
        # ---------------------------------------------------------

        extra_query_keys = (
            set(agent_query_filters.keys())
            - set(gt_query_filters.keys())
        )

        extra_query_keys -= ALLOWED_EXTRA_QUERY_PARAMS

        if extra_query_keys:

            mismatches.append(
                f"extra query filters: "
                f"{sorted(extra_query_keys)}"
            )

        # ---------------------------------------------------------
        # Reject extra values for existing keys
        # ---------------------------------------------------------

        for key in (
            set(agent_query_filters.keys())
            & set(gt_query_filters.keys())
        ):

            if (
                key in ALLOWED_EXTRA_QUERY_PARAMS
                or key in SEMANTIC_QUERY_KEYS
            ):
                continue

            gt_vals = set(
                gt_query_filters.get(key, [])
            )

            agent_vals = set(
                agent_query_filters.get(key, [])
            )

            extra_vals = (
                agent_vals - gt_vals
            )

            if extra_vals:

                mismatches.append(
                    f"extra query filter values: "
                    f"{key}={sorted(extra_vals)}"
                )

        return mismatches

# =====================================================================
# FILTER EXTRACTION
# =====================================================================

    def _extract_filters_from_path(
        self,
        path: str,
    ) -> set[str]:

        filters = set()

        matches = re.findall(
            r"/N-([^/?]+)",
            path,
            re.IGNORECASE,
        )

        for match in matches:

            parts = re.split(
                r"[Zz]",
                match,
            )

            for part in parts:

                token = (
                    part.strip()
                    .lower()
                )

                if not token:
                    continue

                if token == "5yc1v":
                    continue

                filters.add(token)

        return filters

# =====================================================================
# QUERY PARAM EXTRACTION
# =====================================================================

    def _extract_query_filters(
        self,
        query: str,
    ) -> dict:

        raw_query = parse_qs(
            query,
            keep_blank_values=True,
        )

        result = {}

        for key, vals in raw_query.items():

            normalized_key = (
                key.lower().strip()
            )

            if (
                normalized_key
                in IGNORED_QUERY_PARAMS
            ):
                continue

            normalized_vals = [
                self._normalize_string(v)
                for v in vals
                if self._normalize_string(v) != ""
            ]

            if normalized_vals:
                result[normalized_key] = (
                    normalized_vals
                )

        return result

# =====================================================================
# SEARCH TOKEN EXTRACTION
# =====================================================================

    def _extract_search_tokens(
        self,
        path: str,
    ) -> dict[str, list[str]]:

        result: dict[str, list[str]] = {}

        parts = [
            p
            for p in path.strip("/").split("/")
            if p
        ]

        for part in parts:

            lower = part.lower()

            # ---------------------------------------------------------
            # Ntt-searchterm
            # ---------------------------------------------------------

            if lower.startswith("ntt-"):

                value = part[4:]

                result.setdefault(
                    "ntt",
                    [],
                ).append(
                    self._decode_twice(value)
                )

            # ---------------------------------------------------------
            # Ntk-searchmode
            # ---------------------------------------------------------

            elif lower.startswith("ntk-"):

                value = part[4:]

                result.setdefault(
                    "ntk",
                    [],
                ).append(
                    self._decode_twice(value)
                )

        return result

# =====================================================================
# QUERY NORMALIZATION
# =====================================================================

    def _normalize_query(
        self,
        query: str,
    ) -> set[str]:

        if not query:
            return set()

        query = (
            self._decode_twice(query)
            .lower()
            .strip()
        )

        tokens = re.split(
            r"[+\s\-_]+",
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

            found = False

            for agent in agent_tokens:

                if self._token_equivalent(
                    gt,
                    agent,
                ):

                    found = True
                    break

            if not found:
                return False

        return True

    def _token_equivalent(
        self,
        a: str,
        b: str,
    ) -> bool:

        if a == b:
            return True

        # -------------------------------------------------------------
        # ies ↔ y
        # -------------------------------------------------------------

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

        # -------------------------------------------------------------
        # es plurals
        # -------------------------------------------------------------

        plural_map = {
            "xes": "x",
            "ches": "ch",
            "shes": "sh",
            "zes": "z",
            "ses": "s",
        }

        for plural_suffix, singular_suffix in plural_map.items():

            if a.endswith(plural_suffix):

                singular = (
                    a[:-len(plural_suffix)]
                    + singular_suffix
                )

                if singular == b:
                    return True

            if b.endswith(plural_suffix):

                singular = (
                    b[:-len(plural_suffix)]
                    + singular_suffix
                )

                if singular == a:
                    return True

        # -------------------------------------------------------------
        # simple plural
        # -------------------------------------------------------------

        def valid_s_plural(
            x,
            y,
        ):

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

    def _decode_twice(
        self,
        value: str,
    ) -> str:

        try:

            return unquote(
                unquote(value)
            )

        except Exception:

            return unquote(value)

# =====================================================================
# HELPERS
# =====================================================================

    def _extract_search_query(
        self,
        path: str,
    ) -> str:

        parts = [
            p
            for p in path.strip("/").split("/")
            if p
        ]

        if len(parts) >= 2:

            return self._normalize_string(
                parts[1]
            )

        return ""

    def _extract_product_id(
        self,
        path: str,
    ) -> str:

        match = re.search(
            r"/p/(?:.*-)?(\d+)",
            path,
            re.IGNORECASE,
        )

        if match:
            return match.group(1)

        return ""

    def _extract_taxonomy_id(
        self,
        path: str,
    ) -> frozenset[str]:

        match = re.search(
            r"/N-([A-Za-z0-9Zz]+)",
            path,
            re.IGNORECASE,
        )

        if not match:
            return frozenset()

        raw = (
            match.group(1)
            .strip()
            .lower()
        )

        parts = re.split(
            r"[Zz]",
            raw,
        )

        cleaned = [
            p
            for p in parts
            if p and p != "5yc1v"
        ]

        return frozenset(cleaned)

    def _extract_service_id(
        self,
        path: str,
    ) -> str:

        parts = [
            p
            for p in path.strip("/").split("/")
            if p
        ]

        if len(parts) >= 4:

            return (
                parts[3]
                .strip()
                .lower()
            )

        return ""

    def _extract_room_slug(
        self,
        path: str,
    ) -> str:

        parts = [
            p
            for p in path.strip("/").split("/")
            if p
        ]

        if len(parts) >= 2:

            return (
                parts[1]
                .strip()
                .lower()
            )

        return ""

    def _normalize_string(
        self,
        value: str,
    ) -> str:

        return value.strip().lower()


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
    url: str = "https://www.homedepot.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:

    if (
        gt_url is None
        and ground_truth_url is not None
    ):
        gt_url = [ground_truth_url]

    elif isinstance(gt_url, str):
        gt_url = [gt_url]

    elif gt_url is None:

        raise ValueError(
            "gt_url or ground_truth_url required"
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
        HomeDepotUrlMatch
    )

    return BaseTaskConfig(
        url=url,
        task=rendered_task,
        user_metadata=user_metadata,
        eval_config={
            "_target_": eval_target,
            "gt_url": rendered_gt_urls,
        },
    )