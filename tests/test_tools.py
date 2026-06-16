"""
Tests for the three FitFindr tools.

The search_listings tests are pure/local and always run. The LLM-backed tests
(suggest_outfit / create_fit_card) only assert on the guard branches that do NOT
call the network, so the suite passes without a GROQ_API_KEY. A live happy-path
check is in agent.py / the Milestone 5 commands.

Run with:  pytest tests/
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_empty_wardrobe


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Impossible query — nothing in the dataset matches all three constraints.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []  # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_case_insensitive():
    results = search_listings("track jacket", size="m", max_price=None)
    # "M" should match listings whose size contains "M" (e.g. "M", "S/M").
    assert all("m" in item["size"].lower() for item in results)


def test_search_ranked_by_relevance():
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    # A graphic tee should outrank a result that only matches "vintage".
    assert len(results) >= 2
    titles = [r["title"].lower() for r in results]
    assert any("tee" in t or "graphic" in t for t in titles[:1])


# ── create_fit_card (guard branch — no network) ─────────────────────────────

def test_create_fit_card_empty_outfit_returns_message():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result.strip() != ""
    # Should be the guard message, not a crash or an LLM call.
    assert "without an outfit" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_message():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("   \n  ", item)
    assert "without an outfit" in result.lower()


# ── suggest_outfit (smoke — never raises, always returns a non-empty str) ────

def test_suggest_outfit_empty_wardrobe_returns_string():
    # Whether or not the network/key is available, the tool must return a
    # non-empty string (real advice on success, fallback string on failure).
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""
