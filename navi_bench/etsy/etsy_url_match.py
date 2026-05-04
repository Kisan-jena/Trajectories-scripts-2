"""
Etsy URL Matching Verifier

This module implements a deterministic URL verifier for Etsy pages.

It evaluates whether an AGENT-generated Etsy URL matches one or more
GROUND TRUTH (GT) URLs based on structured semantic rules.

Key properties:

1. GT is treated as a SET of acceptable targets (OR logic)
2. Agent produces multiple URLs over time (streaming updates)
3. A match is triggered if ANY agent URL matches ANY GT URL
4. Matching is page-type aware (search / category / group)
5. Matching is strict for structured fields (price, flags, attributes)
6. Query matching is semantic subset-based (token inclusion)

=====================================================================
SUPPORTED PAGE TYPES
=====================================================================

1. /search  → search result matching (query-heavy)
2. /c/      → category page matching (path-based)
3. /r/      → group/collection page matching (filter-based)

Each type has its own parsing + comparison logic.

=====================================================================
IMPORTANT BEHAVIOR NOTES
=====================================================================

- Query matching is SUBSET-based:
    GT tokens must be contained in agent tokens

- Attributes are treated as SET inclusion:
    GT attributes ⊆ agent attributes

- Price, flags, sort, etc. are STRICT equality checks

- FIRST MATCH WINS:
    Once `_found_match = True`, future updates are ignored

=====================================================================
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


class EtsyVerifierResult(BaseModel):
    score: float
    match: bool
    agent_url: str = ""
    gt_url: str = ""
    details: dict = {}


# =====================================================================
# VERIFIER
# =====================================================================

@beartype
class EtsyUrlMatch(BaseMetric):

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

        if not domain.endswith("etsy.com"):
            logger.debug(f"Ignoring non-Etsy URL: {url}")
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

    async def compute_detailed(self) -> EtsyVerifierResult:
        return EtsyVerifierResult(
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

        # 1. Search Results Page
        if gt_path.startswith("/search"):
            return self._search_urls_match(agent_url, gt_url)

        # 2. Category Page
        if gt_path.startswith("/c/"):
            return self._category_urls_match(agent_url, gt_url)

        # 3. Group / Collection Page
        if gt_path.startswith("/r/"):
            return self._group_urls_match(agent_url, gt_url)

        # Unknown
        return False, {"mismatches": ["Unknown Etsy URL type"]}

# =================================================================
# MATCH LOGIC
# =================================================================
    
    # --------------------- SEARCH URL MATCH --------------------
    def _search_urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        try:
            agent = self._parse_search_url(agent_url)
            gt = self._parse_search_url(gt_url)

            mismatches = []

            # 1. Query (MANDATORY)
            gt_tokens = self._normalize_query(gt["query"])
            agent_tokens = self._normalize_query(agent["query"])

            if gt_tokens:
                if not agent_tokens:
                    return False, {"mismatches": ["query missing"]}

                # core logic: GT tokens must be subset of agent tokens
                # if not gt_tokens.issubset(agent_tokens):
                if not self._tokens_match(gt_tokens, agent_tokens):
                    return False, {
                        "mismatches": [
                            f"query mismatch: agent={agent_tokens} vs gt={gt_tokens}"
                        ]
                    }

            # 2. Category Path
            if gt["category_path"]:
                if not agent["category_path"].startswith(gt["category_path"]):
                    mismatches.append("category_path mismatch")

            # 3. Price
            mismatches.extend(self._compare_price(agent, gt))

            # 4. Special offers
            for key in ["free_shipping", "is_discounted"]:
                if gt[key] is not None and agent[key] != gt[key]:
                    mismatches.append(f"{key} mismatch")

            # 5. Location
            if gt["ship_to"] and agent["ship_to"] != gt["ship_to"]:
                mismatches.append("ship_to mismatch")

            if gt["location_query"] and agent["location_query"] != gt["location_query"]:
                mismatches.append("locationQuery mismatch")

            # 6. Delivery time
            if gt["delivery_days"] and agent["delivery_days"] != gt["delivery_days"]:
                mismatches.append("delivery_days mismatch")

            # 7. Item format
            if gt["instant_download"] is not None and agent["instant_download"] != gt["instant_download"]:
                mismatches.append("instant_download mismatch")

            # 8. Item type
            if gt["item_type"] and agent["item_type"] != gt["item_type"]:
                mismatches.append("item_type mismatch")

            # 9. Etsy's Picks
            if gt["is_merch_library"] is not None and agent["is_merch_library"] != gt["is_merch_library"]:
                mismatches.append("is_merch_library mismatch")

            # 10. Star seller
            if gt["is_star_seller"] is not None and agent["is_star_seller"] != gt["is_star_seller"]:
                mismatches.append("is_star_seller mismatch")

            # 11. Attributes
            attr_match, attr_details = self._compare_attributes(
                agent["attributes"], gt["attributes"]
            )
            if not attr_match:
                mismatches.extend(attr_details.get("mismatches", []))

            # 12. Sort
            if gt["sort"] and agent["sort"] != gt["sort"]:
                mismatches.append("sort mismatch")
        
            # 13. Customizable
            if gt["customizable"] is not None and agent["customizable"] != gt["customizable"]:
                mismatches.append("customizable mismatch")
            
            # 14. Gift wrap
            if gt.get("gift_wrap") is not None and agent.get("gift_wrap") != gt.get("gift_wrap"):
                mismatches.append("gift_wrap mismatch")

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

            if gt["category_path"]:
                if not agent["category_path"]:
                    return False, {"mismatches": ["category path missing"]}

                if agent["category_path"] != gt["category_path"]:
                    mismatches.append(
                        f"category_path: {agent['category_path']} vs {gt['category_path']}"
                    )

            # Price
            mismatches.extend(self._compare_price(agent, gt))

            # Offers
            for key in ["free_shipping", "is_discounted"]:
                if gt[key] is not None and agent[key] != gt[key]:
                    mismatches.append(f"{key} mismatch")

            # Location
            if gt["ship_to"] and agent["ship_to"] != gt["ship_to"]:
                mismatches.append("ship_to mismatch")

            if gt["location_query"] and agent["location_query"] != gt["location_query"]:
                mismatches.append("locationQuery mismatch")

            # Item format
            if gt["instant_download"] is not None and agent["instant_download"] != gt["instant_download"]:
                mismatches.append("instant_download mismatch")

            # Item type
            if gt["item_type"] and agent["item_type"] != gt["item_type"]:
                mismatches.append("item_type mismatch")

            # Star seller
            if gt["is_star_seller"] is not None and agent["is_star_seller"] != gt["is_star_seller"]:
                mismatches.append("is_star_seller mismatch")

            # Etsy Pick
            if gt["is_merch_library"] is not None and agent["is_merch_library"] != gt["is_merch_library"]:
                mismatches.append("is_merch_library mismatch")

            # Customizable
            if gt["customizable"] is not None and agent["customizable"] != gt["customizable"]:
                mismatches.append("customizable mismatch")

            # Attributes
            attr_match, attr_details = self._compare_attributes(
                agent["attributes"], gt["attributes"]
            )
            if not attr_match:
                mismatches.extend(attr_details.get("mismatches", []))

            #gift wrap
            if gt.get("gift_wrap") is not None and agent.get("gift_wrap") != gt.get("gift_wrap"):
                mismatches.append("gift_wrap mismatch")

            # Sort
            if gt["sort"] and agent["sort"] != gt["sort"]:
                mismatches.append("sort mismatch")

            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}
    

    # --------------------- GROUP/ COLLECTION URL MATCH -------------------- 
    def _group_urls_match(self, agent_url: str, gt_url: str) -> tuple[bool, dict]:
        try:
            agent = self._parse_group_url(agent_url)
            gt = self._parse_group_url(gt_url)

            mismatches = []

            # Price
            mismatches.extend(self._compare_price(agent, gt))

            # On sale
            if gt["is_on_sale"] is not None and agent["is_on_sale"] != gt["is_on_sale"]:
                mismatches.append("is_on_sale mismatch")

            # Etsy pick
            if gt["is_etsy_pick"] is not None and agent["is_etsy_pick"] != gt["is_etsy_pick"]:
                mismatches.append("is_etsy_pick mismatch")

            # Ships from
            if gt["ships_from"] and agent["ships_from"] != gt["ships_from"]:
                mismatches.append("ships_from mismatch")

            # Item type
            if gt["item_type"] and agent["item_type"] != gt["item_type"]:
                mismatches.append("item_type mismatch")

            # Attributes
            attr_match, attr_details = self._compare_attributes(
                agent["attributes"], gt["attributes"]
            )
            if not attr_match:
                mismatches.extend(attr_details.get("mismatches", []))

            if mismatches:
                return False, {"mismatches": mismatches}

            return True, {}

        except Exception as e:
            logger.error(e)
            return False, {"mismatches": [str(e)]}

# ============================================================
# PARSER
# ============================================================

    # --------------------- SEARCH PARSER --------------------
    def _parse_search_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = {
            "query": "",
            "category_path": "",
            "min_price": None,
            "max_price": None,
            "free_shipping": None,
            "is_discounted": None,
            "ship_to": "",
            "location_query": "",
            "delivery_days": "",
            "instant_download": "",
            "item_type": "",
            "is_merch_library": None,
            "is_star_seller": None,
            "customizable": None,
            "attributes": {},
            "sort": "",
            "gift_wrap": None,
        }

        # Query
        q = self._get_param(query, "q")
        result["query"] = q.lower()

        # Category path
        result["category_path"] = self._get_param(query, "category_path").lower()

        # Price
        result["min_price"] = self._to_int(self._get_param(query, "min"))
        result["max_price"] = self._to_int(self._get_param(query, "max"))

        # Offers
        result["free_shipping"] = self._to_bool(self._get_param(query, "free_shipping"))
        result["is_discounted"] = self._to_bool(self._get_param(query, "is_discounted"))

        # Location
        result["ship_to"] = self._get_param(query, "ship_to").lower()
        result["location_query"] = self._get_param(query, "locationQuery").lower()

        # Delivery
        result["delivery_days"] = self._get_param(query, "delivery_days").lower()

        # Format
        result["instant_download"] = self._to_bool(self._get_param(query, "instant_download"))

        # Item type
        result["item_type"] = self._get_param(query, "item_type").lower()

        # Etsy's Picks
        result["is_merch_library"] = self._to_bool(self._get_param(query, "is_merch_library"))

        # Star seller
        result["is_star_seller"] = self._to_bool(self._get_param(query, "is_star_seller"))

        # Sort
        result["sort"] = self._get_param(query, "order").lower()

        #customizable
        result["customizable"] = self._to_bool(self._get_param(query, "customizable"))

        # Attributes
        result["attributes"] = self._parse_attributes(query)

        # gift-wrapped
        result["gift_wrap"] = self._to_bool(self._get_param(query, "gift_wrap"))

        return result


    def _compare_price(self, agent: dict, gt: dict) -> list[str]:
        mismatches = []

        # min_price (with fallback to 0)
        if gt.get("min_price") is not None:
            gt_val = gt["min_price"]
            agent_val = agent.get("min_price") if agent.get("min_price") is not None else 0

            if agent_val != gt_val:
                mismatches.append("min_price mismatch")

        # max_price (strict)
        if gt.get("max_price") is not None:
            if agent.get("max_price") != gt["max_price"]:
                mismatches.append("max_price mismatch")

        return mismatches

    # --------------------- CATEGORY PARSER --------------------
    def _parse_category_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = {
            "category_path": "",
            "min_price": None,
            "max_price": None,
            "free_shipping": None,
            "is_discounted": None,
            "ship_to": "",
            "location_query": "",
            "instant_download": "",
            "item_type": "",
            "is_star_seller": None,
            "is_merch_library": None, 
            "customizable": None,
            "attributes": {},
            "sort": "",
            "gift_wrap": None,
        }

        path_parts = [p for p in parsed.path.split("/") if p]

        if "c" in path_parts:
            idx = path_parts.index("c")
            category_parts = path_parts[idx + 1:]
            result["category_path"] = "/".join(category_parts).lower()

        result["min_price"] = self._to_int(self._get_param(query, "min"))
        result["max_price"] = self._to_int(self._get_param(query, "max"))

        result["free_shipping"] = self._to_bool(self._get_param(query, "free_shipping"))
        result["is_discounted"] = self._to_bool(self._get_param(query, "is_discounted"))

        result["ship_to"] = self._get_param(query, "ship_to").lower()
        result["location_query"] = self._get_param(query, "locationQuery").lower()

        result["instant_download"] = self._to_bool(self._get_param(query, "instant_download"))
        result["item_type"] = self._get_param(query, "item_type").lower()

        result["is_star_seller"] = self._to_bool(self._get_param(query, "is_star_seller"))

        result["is_merch_library"] = self._to_bool(self._get_param(query, "is_merch_library"))

        result["sort"] = self._get_param(query, "order").lower()

        result["customizable"] = self._to_bool(self._get_param(query, "customizable"))

        result["attributes"] = self._parse_attributes(query)

        result["gift_wrap"] = self._to_bool(self._get_param(query, "gift_wrap"))

        return result

    # --------------------- GROUP/ COLLECTION PARSER --------------------
    def _parse_group_url(self, url: str) -> dict:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        result = {
            "min_price": None,
            "max_price": None,
            "is_on_sale": None,
            "is_etsy_pick": None,
            "ships_from": "",
            "item_type": "",
            "attributes": {},
        }

        result["min_price"] = self._to_int(self._get_param(query, "min_price"))
        result["max_price"] = self._to_int(self._get_param(query, "max_price"))

        result["is_on_sale"] = self._to_bool(self._get_param(query, "is_on_sale"))
        result["is_etsy_pick"] = self._to_bool(self._get_param(query, "is_etsy_pick"))

        result["ships_from"] = self._get_param(query, "ships_from").lower()
        result["item_type"] = self._get_param(query, "item_type").lower()

        result["attributes"] = self._parse_attributes(query)

        return result

    # ============================================================
    # ATTRIBUTE PARSING
    # ============================================================

    def _parse_attributes(self, query: dict) -> dict:
        attrs = {}

        for key, values in query.items():
            if key.startswith("attr_"):
                attr_id = key.replace("attr_", "")
                split_vals = []

                for v in values:
                    split_vals.extend([x.strip().lower() for x in v.split(",")])

                attrs[attr_id] = set(split_vals)

        return attrs

    def _compare_attributes(self, agent_attrs, gt_attrs):
        mismatches = []

        for key, gt_vals in gt_attrs.items():
            if key not in agent_attrs:
                mismatches.append(f"Missing attr_{key}")
                continue

            if not gt_vals.issubset(agent_attrs[key]):
                mismatches.append(
                    f"attr_{key}: {agent_attrs[key]} does not include {gt_vals}"
                )

        return (False, {"mismatches": mismatches}) if mismatches else (True, {})

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
    url: str = "https://www.etsy.com",
    values: dict[str, str] | None = None,
) -> BaseTaskConfig:
    """
    Minimal task config for Etsy URL verification (Search page).

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

    eval_target = get_import_path(EtsyUrlMatch)
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
