"""
Tests for the FitFindr planning loop (agent.py).

Run with:  pytest tests/

These verify the loop *branches* on the search result and passes state
forward correctly — not the exact LLM wording.
"""

from agent import run_agent, _parse_query
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query parsing ─────────────────────────────────────────────────────────────

def test_parse_price():
    assert _parse_query("vintage tee under $30")["max_price"] == 30.0


def test_parse_size_explicit():
    assert _parse_query("track jacket size M")["size"] == "M"


def test_parse_size_shoe_number():
    assert _parse_query("combat boots size 8")["size"] == "8"


def test_parse_all_three():
    parsed = _parse_query("designer ballgown size XXS under $5")
    assert parsed["size"] == "XXS"
    assert parsed["max_price"] == 5.0
    assert "ballgown" in parsed["description"]


# ── happy path: state flows through all three tools ───────────────────────────

def test_happy_path_runs_all_tools():
    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    assert session["error"] is None
    assert session["selected_item"] is not None
    assert session["outfit_suggestion"]
    assert session["fit_card"]


def test_selected_item_is_top_result():
    # State integrity: the item handed downstream IS the top search result.
    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    assert session["selected_item"] is session["search_results"][0]


# ── branch path: no results stops before the LLM tools ────────────────────────

def test_no_results_sets_error_and_stops():
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None
    assert session["search_results"] == []
    # suggest_outfit / create_fit_card must NOT have run.
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_empty_wardrobe_still_completes():
    # Empty wardrobe is not an error — the loop runs to completion.
    session = run_agent("vintage graphic tee under $30", get_empty_wardrobe())
    assert session["error"] is None
    assert session["fit_card"]
