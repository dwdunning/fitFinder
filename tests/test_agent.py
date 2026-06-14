"""
tests/test_agent.py

Lightweight tests for _parse_query() and the run_agent() planning loop.
Run from the project root: pytest tests/test_agent.py -v
"""

import pytest
from agent import _parse_query, run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── _parse_query: price extraction ───────────────────────────────────────────

def test_parse_under_dollar_price():
    result = _parse_query("vintage graphic tee under $30")
    assert result["max_price"] == 30.0

def test_parse_under_no_dollar_price():
    result = _parse_query("vintage graphic tee under 30")
    assert result["max_price"] == 30.0

def test_parse_bare_dollar_price():
    result = _parse_query("vintage graphic tee $30")
    assert result["max_price"] == 30.0

def test_parse_below_price():
    result = _parse_query("denim jacket below $45")
    assert result["max_price"] == 45.0

def test_parse_less_than_price():
    result = _parse_query("cottagecore cardigan less than $25")
    assert result["max_price"] == 25.0

def test_parse_no_price_returns_none():
    result = _parse_query("vintage graphic tee")
    assert result["max_price"] is None


# ── _parse_query: size extraction ────────────────────────────────────────────

def test_parse_letter_size():
    result = _parse_query("vintage tee size M")
    assert result["size"] == "M"

def test_parse_numeric_size():
    result = _parse_query("platform sneakers size 8")
    assert result["size"] == "8"

def test_parse_no_size_returns_none():
    result = _parse_query("vintage graphic tee under $30")
    assert result["size"] is None


# ── _parse_query: description cleaning ───────────────────────────────────────

def test_parse_removes_budget_phrase_from_description():
    result = _parse_query("looking for a vintage graphic tee under $30")
    assert result["description"] == "looking for a vintage graphic tee"
    assert result["max_price"] == 30.0

def test_parse_removes_size_phrase_from_description():
    result = _parse_query("vintage graphic tee size M")
    assert "size" not in result["description"].lower()
    assert result["size"] == "M"

def test_parse_full_query():
    result = _parse_query("designer ballgown size XXS under $5")
    assert result["max_price"] == 5.0
    assert result["size"] == "XXS"
    assert "ballgown" in result["description"]


# ── run_agent: planning loop behavior ────────────────────────────────────────

def test_run_agent_no_results_sets_error():
    """When search returns nothing, error is set and downstream fields stay None."""
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert session["error"] is not None
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None

def test_run_agent_no_results_does_not_call_downstream_tools():
    """Confirm downstream state keys are untouched after a no-results early stop."""
    session = run_agent("unicorn spacesuit", get_empty_wardrobe())
    assert session["search_results"] == []
    assert session["fit_card"] is None
