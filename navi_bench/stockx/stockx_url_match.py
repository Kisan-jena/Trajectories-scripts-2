import re
from typing import Any, TypedDict
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

class InputDict(TypedDict, total=False):
    url: str


class FinalResult(BaseModel):
    score: float


class StockxVerifierResult(BaseModel):
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =====================================================================
# VERIFIER
# =====================================================================

@beartype
class StockxUrlMatch(BaseMetric):

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

        if not domain.endswith("stockx.com"):
            logger.debug(f"Ignoring non-stockx URL: {url}")
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
                return

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(gt_urls={self.gt_urls})"
    
    async def compute(self) -> FinalResult:
        return FinalResult(score=1.0 if self._found_match else 0.0)

    async def compute_detailed(self) -> StockxVerifierResult:
        return StockxVerifierResult(
            score=1.0 if self._found_match else 0.0,
            match=self._found_match,
            agent_url=self._agent_url,
            gt_url=self._matched_gt_url,
            details=self._match_details,
        )

# =================================================================
# PAGETYPE BASED URL MATCH LOGIC
# =================================================================

    def _urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        parsed_gt = urlparse(gt_url)
        gt_path = (parsed_gt.path or "").lower()

        # 1. SEARCH PAGE (/search?s=...)
        if gt_path.startswith("/search"):
            return self._search_urls_match(agent_url, gt_url)

        # 2. CATEGORY PAGE (/category/<type>)
        if gt_path.startswith("/category/"):
            return self._category_urls_match(agent_url, gt_url)

        # 3. BRAND PAGE (/brands/<brand>)
        if gt_path.startswith("/brands/"):
            return self._brand_urls_match(agent_url, gt_url)

        # 4. BROWSE PAGE (/browse/<segment>)
        if gt_path.startswith("/browse/"):
            return self._browse_urls_match(agent_url, gt_url)

        # UNKNOWN
        return False, {"mismatches": ["Unknown StockX URL type"]}

# =================================================================
# MATCH LOGIC
# =================================================================
    # --------------------- COMMON FILTERS URL MATCH --------------------   
    def _match_common_filters(self, agent: dict, gt: dict) -> list[str]:
        mismatches = []

        # -----------------------------
        # BOOLEAN FILTERS
        # -----------------------------
        for key in ["available_now", "xpress_ship"]:
            if gt[key] is not None:
                if agent[key] != gt[key]:
                    mismatches.append(f"{key} mismatch")

        # -----------------------------
        # MULTI VALUE FILTERS
        # -----------------------------
        for key in ["gender", "brand", "activity", "color"]:
            if gt[key]:
                if key not in agent or not agent[key]:
                    mismatches.append(f"{key} missing")
                elif not gt[key].issubset(agent[key]):
                    mismatches.append(
                        f"{key} mismatch: {agent[key]} vs {gt[key]}"
                    )

        # -----------------------------
        # PRICE RANGE 
        # -----------------------------
        if gt["min_price"] is not None:
            if agent["min_price"] != gt["min_price"]:
                mismatches.append(
                    f"min_price mismatch: {agent['min_price']} vs {gt['min_price']}"
                )

        if gt["max_price"] is not None:
            if agent["max_price"] != gt["max_price"]:
                mismatches.append(
                    f"max_price mismatch: {agent['max_price']} vs {gt['max_price']}"
                )

        # -----------------------------
        # SORT 
        # -----------------------------
        if gt["sort"]:
            if agent["sort"] != gt["sort"]:
                mismatches.append(
                    f"sort mismatch: {agent['sort']} vs {gt['sort']}"
                )

        return mismatches
    
    # --------------------- SEARCH PAGE URL MATCH --------------------   
    def _search_urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        try:
            agent = self._parse_search_url(agent_url)
            gt = self._parse_search_url(gt_url)

            mismatches = []
            
            agent_path = urlparse(agent_url).path.lower()
            if not agent_path.startswith("/search"):
                mismatches.append(f"path mismatch: not on search page ({agent_path})")

            gt_tokens = self._normalize_query(gt.get("query", ""))
            agent_tokens = self._normalize_query(agent.get("query", ""))

            if gt_tokens:
                if not agent_tokens:
                    mismatches.append("query missing")
                elif not self._tokens_match(gt_tokens, agent_tokens):
                    mismatches.append(
                        f"query mismatch: {agent_tokens} vs {gt_tokens}"
                    )

            mismatches.extend(self._match_common_filters(agent, gt))
            mismatches.extend(self._match_aspects(agent, gt))

            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}
        
    # --------------------- CATEGORY PAGE URL MATCH --------------------   
    def _category_urls_match(self, agent_url, gt_url):
        try:
            agent = self._parse_category_url(agent_url)
            gt = self._parse_category_url(gt_url)

            mismatches = []

            if agent["category_path"] != gt["category_path"]:
                mismatches.append(
                    f"category mismatch: {agent['category_path']} vs {gt['category_path']}"
                )

            mismatches.extend(self._match_common_filters(agent, gt))
            mismatches.extend(self._match_aspects(agent, gt))

            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}
    
    # --------------------- BRANDS PAGE URL MATCH --------------------   
    def _brand_urls_match(self, agent_url, gt_url):
        try:
            agent = self._parse_brand_url(agent_url)
            gt = self._parse_brand_url(gt_url)

            mismatches = []

            # ---------------------------------
            # Canonical brand check via path
            # ---------------------------------
            if gt["brand_slug"]:
                if agent["brand_slug"] != gt["brand_slug"]:
                    mismatches.append(
                        f"brand mismatch: {agent['brand_slug']} vs {gt['brand_slug']}"
                    )

            # ---------------------------------
            # Ignore redundant brand query filter
            # for /brands/* pages
            # ---------------------------------
            agent_common = dict(agent)
            gt_common = dict(gt)

            agent_common["brand"] = set()
            gt_common["brand"] = set()

            mismatches.extend(
                self._match_common_filters(agent_common, gt_common)
            )

            mismatches.extend(self._match_aspects(agent, gt))

            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}
    
    # --------------------- BROWSE PAGE URL MATCH --------------------   
    def _browse_urls_match(self, agent_url, gt_url):
        try:
            agent = self._parse_browse_url(agent_url)
            gt = self._parse_browse_url(gt_url)

            mismatches = []

            if gt["browse_segment"]:
                if agent["browse_segment"] != gt["browse_segment"]:
                    mismatches.append(
                        f"browse mismatch: {agent['browse_segment']} vs {gt['browse_segment']}"
                    )

            mismatches.extend(self._match_common_filters(agent, gt))
            mismatches.extend(self._match_aspects(agent, gt))

            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}
        
    # --------------------- ATTRIBUTES URL MATCH --------------------   
    def _match_aspects(self, agent: dict, gt: dict) -> list[str]:
        mismatches = []

        gt_aspects = gt.get("aspects", {})
        agent_aspects = agent.get("aspects", {})

        for key, gt_vals in gt_aspects.items():

            # missing attribute
            if key not in agent_aspects:
                mismatches.append(f"missing aspect: {key}")
                continue

            agent_vals = agent_aspects[key]

            # subset check
            if not gt_vals.issubset(agent_vals):
                mismatches.append(
                    f"{key} mismatch: {agent_vals} vs {gt_vals}"
                )

        return mismatches

# ============================================================
# PARSER
# ============================================================

    # --------------------- COMMON FILTERS PARSE--------------------
    def _parse_common_filters(self, query: dict) -> dict:

        min_price, max_price = self._parse_price_range(
            self._get_param(query, "lowest-ask-range")
        )

        result = {
            "available_now": self._to_bool(self._get_param(query, "available-now")),
            "xpress_ship": self._to_bool(self._get_param(query, "xpress-ship")),

            "gender": self._parse_multi_value(self._get_param(query, "gender")),
            "brand": self._parse_multi_value(self._get_param(query, "brand")),
            "activity": self._parse_multi_value(self._get_param(query, "activity")),
            "color": self._parse_multi_value(self._get_param(query, "color")),

            "sort": self._get_param(query, "sort"),

            "min_price": min_price,
            "max_price": max_price,

            "aspects": self._parse_aspects(query),
        }

        return result
    
    # --------------------- SEARCH PARSE--------------------
    def _parse_search_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = self._parse_common_filters(query)

        result.update({
            "query": self._decode_twice(self._get_param(query, "s")).lower(),
        })

        return result

    # --------------------- CATEGORY PARSE--------------------
    def _parse_category_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = self._parse_common_filters(query)

        result["category_path"] = self._extract_category_path(url)

        return result
    
    # --------------------- BRANDS PARSE--------------------
    def _parse_brand_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = self._parse_common_filters(query)

        parts = parsed.path.lower().strip("/").split("/")
        result["brand_slug"] = parts[1] if len(parts) > 1 else ""

        return result
    # --------------------- BROWSE PARSE--------------------
    def _parse_browse_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = self._parse_common_filters(query)

        parts = parsed.path.lower().strip("/").split("/")
        result["browse_segment"] = parts[1] if len(parts) > 1 else ""

        return result
    
    # --------------------- ATTRIBUTES PARSER --------------------    
    def _parse_aspects(self, query: dict) -> dict[str, set[str]]:
        aspects = {}

        for key, values in query.items():

            if key in {
                "s",
                "sort",
                "available-now",
                "xpress-ship",
                "lowest-ask-range",
                "gender",
                "brand",
                "activity",
                "color",
            }:
                continue

            if not values:
                continue

            decoded_key = self._decode_twice(key).lower().strip()

            clean_values = set()
            for val in values:
                decoded_val = self._decode_twice(val).lower()
                parts = re.split(r"[|,]", decoded_val)
                for p in parts:
                    p = p.strip()
                    if p:
                        clean_values.add(p)

            if clean_values:
                aspects[decoded_key] = clean_values

        return aspects
# ============================================================
# HELPERS
# ============================================================

    @staticmethod
    def _get_param(query: dict, key: str) -> str:
        if key in query and query[key]:
            return ",".join([v.strip() for v in query[key] if v.strip()])
        return ""
        
    @staticmethod
    def _to_bool(value: str) -> bool | None:
        if not value:
            return None
        return value.strip().lower() == "true"
    
    def _parse_price_range(self, value: str):
        if not value:
            return None, None

        try:
            parts = value.split("-")
            if len(parts) != 2:
                return None, None

            min_price = float(parts[0]) if parts[0].strip() else None
            max_price = float(parts[1]) if parts[1].strip() else None
            return min_price, max_price
        except:
            return None, None

    def _normalize_query(self, query: str) -> set[str]:
        if not query:
            return set()

        # decode + normalize
        query = unquote(query).lower().strip()

        # split words
        tokens = re.split(r"[+\s\-_]+", query)

        # remove stopwords 
        stopwords = {"for", "and", "the", "with", "a", "an", "of"}

        return {t for t in tokens if t and t not in stopwords}

    def _tokens_match(self, gt_tokens: set[str], agent_tokens: set[str]) -> bool:
        for gt in gt_tokens:
            if any(self._token_equivalent(gt, a) for a in agent_tokens):
                continue
            return False
        return True

    def _token_equivalent(self, a: str, b: str) -> bool:
        if a == b:
            return True

        # -----------------------------
        # ies ↔ y  (party ↔ parties)
        # -----------------------------
        if a.endswith("ies") and a[:-3] + "y" == b:
            return True
        if b.endswith("ies") and b[:-3] + "y" == a:
            return True

        # -----------------------------
        # es (boxes, dresses, watches)
        # ONLY for valid endings
        # -----------------------------
        es_endings = ("xes", "ches", "shes", "zes", "ses")

        if a.endswith(es_endings) and a[:-2] == b:
            return True
        if b.endswith(es_endings) and b[:-2] == a:
            return True

        # -----------------------------
        # simple 's' plural
        # but AVOID bad stems
        # -----------------------------
        def valid_s_plural(x, y):
            return (
                x.endswith("s")
                and not x.endswith(("ss", "us", "is"))
                and x[:-1] == y
            )

        if valid_s_plural(a, b):
            return True
        if valid_s_plural(b, a):
            return True

        return False
 
    def _decode_twice(self, value: str) -> str:
        try:
            return unquote(unquote(value))
        except:
            return unquote(value)


    def _parse_multi_value(self, value: str) -> set[str]:
        if not value:
            return set()

        value = self._decode_twice(value).lower()

        parts = re.split(r"[|,]", value)
        return {p.strip() for p in parts if p.strip()}
    
    def _extract_category_path(self, url: str) -> list[str]:
        path = urlparse(url).path.lower().strip("/")
        parts = path.split("/")

        if parts and parts[0] == "category":
            return parts[1:]

        return []

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
    url: str = "https://www.stockx.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """
    Minimal task config for Stockx URL verification (Search page).

    - No multi-date expansion
    - Simple placeholder replacement
    - GT URLs rendered with first resolved value
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

    rendered_task = render_task_statement(task, resolved_placeholders)

    rendered_gt_urls: list[str] = []

    for template in gt_url:
        rendered_u = template

        for key, (_, vals) in resolved_placeholders.items():
            placeholder = f"{{{key}}}"
            if placeholder in rendered_u and vals:
                rendered_u = rendered_u.replace(placeholder, vals[0])

        rendered_gt_urls.append(rendered_u)

    eval_target = get_import_path(StockxUrlMatch)
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
