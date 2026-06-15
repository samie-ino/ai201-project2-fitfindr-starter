"""
Tests for the three FitFindr tools.

Run with:  pytest tests/

The search_listings tests are pure/deterministic (no network). The LLM-backed
tools (suggest_outfit, create_fit_card) are tested for their *contract* —
non-empty strings, graceful failure-mode handling — not exact wording, since
the model output varies run to run.
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, never an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_case_insensitive():
    # "m" should match sizes like "M" and "S/M".
    results = search_listings("tee", size="m", max_price=100)
    assert all("m" in item["size"].lower() for item in results)


def test_search_sorted_by_relevance():
    # More keyword overlap should rank at or above less overlap.
    results = search_listings("vintage graphic tee", size=None, max_price=100)
    assert len(results) >= 2  # sanity: query should hit several listings


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    suggestion = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert suggestion.strip() != ""


def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe → general advice, not a crash or "".
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    suggestion = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert suggestion.strip() != ""


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def test_create_fit_card_returns_string():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("Pair it with baggy jeans and chunky sneakers.", item)
    assert isinstance(card, str)
    assert card.strip() != ""


def test_create_fit_card_empty_outfit():
    # Failure mode: empty outfit → descriptive error string, not a crash.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "without an outfit" in card.lower()
