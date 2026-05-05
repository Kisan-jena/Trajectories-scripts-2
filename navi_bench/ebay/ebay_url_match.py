"""
Ebay URL Match Verifier

Purpose:
    Validates whether an agent-generated eBay URL satisfies a ground-truth (GT) URL.

Supported Page Types:
    1. Search Pages      (/sch/i.html)
    2. Category Pages    (/b/.../<category-id>/...)
    3. Brand Pages       (/b/.../bn_<id>)

Matching Logic:
    - Query tokens (subset match with plural normalization)
    - Category / browse node (bn_) matching
    - Common filters:
        * Buying format (auction, buy-it-now)
        * Price range (min/max with tolerance)
        * Item condition
        * Item location
        * Shipping & returns flags
        * Deals / seller filters
        * Sorting
    - Aspect filters (key-value attributes; GT ⊆ agent required)

Key Behaviors:
    - Subset matching: Agent may include extra filters but must satisfy all GT constraints
    - First-match-wins: Once a GT URL matches, state is locked
    - Multi-GT support: Any GT match results in success
    - Non-eBay domains are ignored
    - Robust to malformed / empty URLs
"""

import re
from typing import Any, TypedDict
from urllib.parse import parse_qs, unquote, urlparse

from beartype import beartype
from loguru import logger
from pydantic import BaseModel
from datetime import datetime
from itertools import product

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


class EbayVerifierResult(BaseModel):
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =====================================================================
# VERIFIER
# =====================================================================

@beartype
class EbayUrlMatch(BaseMetric):

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

        if not domain.endswith("ebay.com"):
            logger.debug(f"Ignoring non-Ebay URL: {url}")
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

    async def compute_detailed(self) -> EbayVerifierResult:
        return EbayVerifierResult(
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

        # SEARCH RESULTS PAGE -> /sch/i.html?_nkw=...
        if gt_path.startswith("/sch/i.html"):
            return self._search_urls_match(agent_url, gt_url)

        # CATEGORY / BRAND / REFINEMENT PAGE -> /b/... (multiple variants)
        if gt_path.startswith("/b/"):
            path_parts = [p for p in gt_path.split("/") if p]

            # Detect numeric category ID
            has_category_id = any(p.isdigit() for p in path_parts)

            # Detect browse node
            has_bn = any(p.startswith("bn_") for p in path_parts)

            # -----------------------------------------------------------------------
            # 3A. CATEGORY PAGE (with category-id) => /b/<slug>/<category-id>/bn_<id>
            # -----------------------------------------------------------------------
            if has_category_id:
                return self._category_urls_match(agent_url, gt_url)

            # -----------------------------------------------------------------------------
            # 3B. BRAND / REFINEMENT PAGE (no category-id, only bn_) => /b/<brand>/bn_<id>
            # -----------------------------------------------------------------------------
            if has_bn:
                return self._brand_urls_match(agent_url, gt_url)

        # UNKNOWN TYPE
        return False, {"mismatches": ["Unknown eBay URL type"]}

# =================================================================
# MATCH LOGIC
# =================================================================

    def _match_common_filters(self, agent: dict, gt: dict) -> list[str]:
        mismatches = []

        # BUYING FORMAT
        for key in ["auction", "buy_it_now"]:
            if gt[key] is not None and agent[key] != gt[key]:
                mismatches.append(f"{key} mismatch")

        # CONDITION
        if gt["conditions"]:
            if not agent["conditions"]:
                mismatches.append("conditions missing")
            elif not gt["conditions"].issubset(agent["conditions"]):
                mismatches.append(
                    f"conditions mismatch: {agent['conditions']} vs {gt['conditions']}"
                )

        # PRICE
        if gt["min_price"] is not None:
            if agent["min_price"] is None or not self._price_equal(agent["min_price"], gt["min_price"]):
                mismatches.append(
                    f"min_price mismatch: {agent['min_price']} vs {gt['min_price']}"
                )

        if gt["max_price"] is not None:
            if agent["max_price"] is None or not self._price_equal(agent["max_price"], gt["max_price"]):
                mismatches.append(
                    f"max_price mismatch: {agent['max_price']} vs {gt['max_price']}"
                )

        # LOCATION
        if gt["item_location"]:
            if agent["item_location"] != gt["item_location"]:
                mismatches.append("item_location mismatch")

        # SHOW ONLY
        for key in ["deals", "authorized_seller", "free_returns", "returns_accepted"]:
            if gt[key] is not None and agent[key] != gt[key]:
                mismatches.append(f"{key} mismatch")

        # DELIVERY
        for key in ["free_shipping", "local_pickup"]:
            if gt[key] is not None and agent[key] != gt[key]:
                mismatches.append(f"{key} mismatch")

        # SORT
        if gt["sort"]:
            if agent["sort"] != gt["sort"]:
                mismatches.append("sort mismatch")

        return mismatches
    
    # --------------------- SEARCH URL MATCH --------------------
    def _search_urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        try:
            agent = self._parse_search_url(agent_url)
            gt = self._parse_search_url(gt_url)

            mismatches = []

            # 1. QUERY
            gt_tokens = self._normalize_query(gt["query"])
            agent_tokens = self._normalize_query(agent["query"])

            if gt_tokens:
                if not agent_tokens:
                    return False, {"mismatches": ["query missing"]}

                if not self._tokens_match(gt_tokens, agent_tokens):
                    return False, {
                        "mismatches": [
                            f"query mismatch: agent={agent_tokens} vs gt={gt_tokens}"
                        ]
                    }

            # 2. CATEGORY
            if gt["category"] and gt["category"] != "0":
                if agent["category"] != gt["category"]:
                    mismatches.append("category mismatch")

            # 3. COMMON FILTERS
            mismatches.extend(self._match_common_filters(agent, gt))

            # 4. ATTRBUTES FILTERS
            mismatches.extend(self._match_aspects(agent, gt)) 

            # MISMATCHED CASE
            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}

    # --------------------- CATEGORY URL MATCH --------------------
    def _category_urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        try:
            agent = self._parse_category_url(agent_url)
            gt = self._parse_category_url(gt_url)

            mismatches = []

            # 1. CATEGORY ID 
            if gt["category_id"]:
                if not agent["category_id"]:
                    return False, {"mismatches": ["category_id missing"]}
                if agent["category_id"] != gt["category_id"]:
                    mismatches.append(
                        f"category_id mismatch: {agent['category_id']} vs {gt['category_id']}"
                    )

            # 2. BROWSE NODE (bn_) 
            if gt["bn_id"]:
                if agent["bn_id"] != gt["bn_id"]:
                    mismatches.append(
                        f"bn_id mismatch: {agent['bn_id']} vs {gt['bn_id']}"
                    )

            # 3. COMMON FILTERS
            mismatches.extend(self._match_common_filters(agent, gt))

            # 4. ATTRIBURES FILTERS 
            mismatches.extend(self._match_aspects(agent, gt)) 

            # MISMATCH CASE
            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}

    # --------------------- BRANDS URL MATCH --------------------
    def _brand_urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        try:
            agent = self._parse_brand_url(agent_url)
            gt = self._parse_brand_url(gt_url)

            mismatches = []

            # 1. BN ID 
            if gt["bn_id"]:
                if not agent["bn_id"]:
                    return False, {"mismatches": ["bn_id missing"]}

                if agent["bn_id"] != gt["bn_id"]:
                    mismatches.append(
                        f"bn_id mismatch: {agent['bn_id']} vs {gt['bn_id']}"
                    )

            # 2. COMMON FILTERS
            mismatches.extend(self._match_common_filters(agent, gt))

            # 3. ATTRIBUTES FILTERS
            mismatches.extend(self._match_aspects(agent, gt)) 

            # MISMATCH CASE
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

            # missing aspect
            if key not in agent_aspects:
                mismatches.append(f"missing aspect: {key}")
                continue

            agent_vals = agent_aspects[key]

            # ❌ subset check
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
        result = {
            "auction": self._to_bool(self._get_param(query, "LH_Auction")),
            "buy_it_now": self._to_bool(self._get_param(query, "LH_BIN")),

            "conditions": set(),
            "item_location": self._get_param(query, "LH_PrefLoc"),

            "min_price": self._to_float(self._get_param(query, "_udlo")),
            "max_price": self._to_float(self._get_param(query, "_udhi")),

            "deals": self._to_bool(self._get_param(query, "LH_Savings")),
            "authorized_seller": self._to_bool(self._get_param(query, "LH_AS")),
            "free_returns": self._to_bool(self._get_param(query, "LH_FR")),
            "returns_accepted": self._to_bool(self._get_param(query, "LH_RPA")),

            "free_shipping": self._to_bool(self._get_param(query, "LH_FS")),
            "local_pickup": self._to_bool(self._get_param(query, "LH_LPickup")),

            "sort": self._get_param(query, "_sop"),
        }

        # CONDITION parsing
        cond_raw = self._get_param(query, "LH_ItemCondition")
        if cond_raw:
            cond_raw = unquote(cond_raw)
            result["conditions"] = {
                x.strip() for x in cond_raw.split("|") if x.strip()
            }
        
        result["aspects"] = self._parse_aspects(query)

        return result

    # --------------------- SEARCH PARSER --------------------
    def _parse_search_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = self._parse_common_filters(query)

        result.update({
            "query": self._get_param(query, "_nkw").lower(),
            "category": self._get_param(query, "_sacat"),
        })

        return result

    # --------------------- CATEGORY PARSER --------------------
    def _parse_category_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = self._parse_common_filters(query)

        result.update({
            "category_id": "",
            "bn_id": "",
        })

        path_parts = [p for p in parsed.path.split("/") if p]

        for p in path_parts:
            if p.isdigit():
                result["category_id"] = p
            elif p.startswith("bn_"):
                result["bn_id"] = p.replace("bn_", "")

        return result

    # --------------------- BRANDS PARSER --------------------
    def _parse_brand_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = self._parse_common_filters(query)

        result.update({
            "bn_id": "",
        })

        path_parts = [p for p in parsed.path.split("/") if p]

        for p in path_parts:
            if p.startswith("bn_"):
                result["bn_id"] = p.replace("bn_", "")

        return result

    # --------------------- ATTRIBUTES PARSER --------------------    
    def _parse_aspects(self, query: dict) -> dict[str, set[str]]:
        aspects = {}

        for key, values in query.items():

            # skip system params
            if key.startswith("_") or key.startswith("LH_"):
                continue

            if not values:
                continue

            # decode key (double decode for ebay)
            decoded_key = self._decode_twice(key).lower().strip()

            # decode value
            decoded_val = self._decode_twice(values[0]).lower()

            # split multi values
            parts = re.split(r"[|,]", decoded_val)

            clean_values = set()

            for p in parts:
                p = p.strip()

                if not p:
                    continue

                # remove negation (!value)
                if p.startswith("!"):
                    p = p[1:]

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
            return query[key][0].strip()
        return ""

    @staticmethod
    def _to_int(value: str):
        try:
            return int(value)
        except:
            return None
        
    @staticmethod
    def _to_bool(value: str) -> bool | None:
        if not value:
            return None
        return value.strip().lower() == "true"
    
    @staticmethod
    def _to_float(value: str):
        try:
            return float(value)
        except:
            return None

    def _price_equal(self, a, b, tol=0.01):
        return abs(a - b) <= tol

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


    def _parse_multi_value_param(self, query: dict, key: str) -> set[str]:
        raw_values = query.get(key, [])
        result = set()

        for val in raw_values:
            decoded = self._decode_twice(val)

            # split multi-values
            parts = re.split(r"[|,]", decoded)

            for p in parts:
                p = p.strip().lower()

                if not p:
                    continue

                # normalize: remove leading "!"
                if p.startswith("!"):
                    p = p[1:]

                result.add(p)

        return result

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
    url: str = "https://www.ebay.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """
    Minimal task config for Ebay URL verification (Search page).

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

    eval_target = get_import_path(EbayUrlMatch)
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