"""Hotels.com verifier module for hotel search navigation.

This module verifies AI agent hotel search results on Hotels.com by comparing
the agent's final URL against expected ground truth URLs (URL-based verifier).
"""

from navi_bench.hotels_com.hotels_com_url_match import (
    HotelsComUrlMatch,
    generate_task_config,
)

__all__ = [
    "HotelsComUrlMatch",
    "generate_task_config",
]
