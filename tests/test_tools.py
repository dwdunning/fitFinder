"""
tests/test_tools.py

Pytest tests for all three tools (Milestone 3).
Run from the project root: pytest tests/test_tools.py -v
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card, compare_price
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Fixtures for create_fit_card tests ───────────────────────────────────────
# Using a minimal item dict keeps these tests independent of search_listings.

_SAMPLE_ITEM = {
    "title": "Graphic Tee — Faded Bootleg Style",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge"],
    "size": "L",
    "condition": "good",
    "price": 24.0,
    "colors": ["black"],
    "platform": "depop",
}
_SAMPLE_OUTFIT = (
    "Pair with baggy dark wash jeans and chunky white sneakers. "
    "Layer a vintage denim jacket over the tee for a grunge-streetwear look."
)


def test_matching_query_returns_results():
    """A reasonable query against real data should find at least one listing."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0


def test_no_match_returns_empty_list():
    """A query that matches nothing should return [] without raising."""
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_price_filter_excludes_over_budget():
    """Every result must have price <= max_price."""
    max_price = 25.0
    results = search_listings("vintage", size=None, max_price=max_price)
    assert len(results) > 0, "Expected at least one vintage item under $25"
    for item in results:
        assert item["price"] <= max_price, (
            f"Item '{item['title']}' costs ${item['price']}, exceeds max_price={max_price}"
        )


def test_results_are_dicts_with_expected_keys():
    """Every returned item should be a dict containing the required listing fields."""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    required_keys = {"id", "title", "price", "platform", "category", "style_tags"}
    for item in results:
        assert isinstance(item, dict)
        missing = required_keys - item.keys()
        assert not missing, f"Result is missing keys: {missing}"


def test_empty_description_returns_empty_list():
    """Empty description should not crash and should return []."""
    results = search_listings("", size=None, max_price=None)
    assert results == []


def test_no_filters_with_matching_description():
    """Omitting size and max_price should still return keyword-matched results."""
    results = search_listings("denim jacket", size=None, max_price=None)
    assert len(results) > 0


def test_results_sorted_by_relevance():
    """Results with more keyword hits should appear before results with fewer."""
    results = search_listings("vintage grunge streetwear", size=None, max_price=None)
    assert len(results) >= 2
    # Spot-check: no item without any of those tags should appear before one that has all three
    # (Full scoring verification would require inspecting the score internals;
    #  this check just confirms we get multiple results and the first has relevant tags.)
    first_tags = set(results[0].get("style_tags", []))
    assert first_tags & {"vintage", "grunge", "streetwear"}, (
        f"Top result tags {first_tags!r} share no keywords with the query"
    )


# ── suggest_outfit tests ──────────────────────────────────────────────────────

def test_suggest_outfit_with_example_wardrobe():
    """suggest_outfit with a populated wardrobe should return a non-empty string."""
    items = search_listings("vintage graphic tee", size=None, max_price=50)
    assert items, "search_listings returned no results — check the dataset"
    result = suggest_outfit(items[0], get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_with_empty_wardrobe():
    """suggest_outfit with an empty wardrobe should return a non-empty string, not crash."""
    items = search_listings("vintage graphic tee", size=None, max_price=50)
    assert items, "search_listings returned no results — check the dataset"
    result = suggest_outfit(items[0], get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_with_malformed_item():
    """suggest_outfit with an empty dict should return a non-empty string, not raise."""
    result = suggest_outfit({}, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_never_returns_none():
    """suggest_outfit should never return None for any combination of inputs."""
    result = suggest_outfit({}, {"items": []})
    assert result is not None
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_suggest_outfit_wardrobe_items_mentioned():
    """When wardrobe has items, at least one item name should appear in the result.

    The deterministic fallback (used when the LLM is unavailable) explicitly
    names the first 1–3 wardrobe items, so this holds even without an API key.
    The LLM prompt also instructs the model to mention wardrobe pieces by name,
    so the same assertion covers the live API path.
    """
    items = search_listings("vintage graphic tee", size=None, max_price=50)
    assert items, "search_listings returned no results — check the dataset"
    wardrobe = get_example_wardrobe()
    result = suggest_outfit(items[0], wardrobe)
    wardrobe_names = [item["name"] for item in wardrobe.get("items", [])]
    assert any(name in result for name in wardrobe_names), (
        f"Expected at least one wardrobe item name in the result.\nGot: {result}"
    )


# ── create_fit_card tests ─────────────────────────────────────────────────────

def test_create_fit_card_valid_input_returns_nonempty():
    """Valid outfit + valid item should return a non-empty string."""
    result = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_create_fit_card_empty_outfit_returns_exact_error():
    """Empty outfit string must return the exact sentinel error string."""
    result = create_fit_card("", _SAMPLE_ITEM)
    assert result == "Could not generate caption — outfit suggestion was missing."


def test_create_fit_card_whitespace_outfit_returns_exact_error():
    """Whitespace-only outfit string must return the same exact error string."""
    result = create_fit_card("   ", _SAMPLE_ITEM)
    assert result == "Could not generate caption — outfit suggestion was missing."


def test_create_fit_card_malformed_item_returns_nonempty():
    """A valid outfit with an empty item dict should not raise and should return a string."""
    result = create_fit_card(_SAMPLE_OUTFIT, {})
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_create_fit_card_output_includes_title_or_price():
    """The caption should mention the item title or price somewhere in the output."""
    result = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    title = _SAMPLE_ITEM["title"]
    # Accept price in any common format ($24 or $24.00)
    price_fragment = f"${int(_SAMPLE_ITEM['price'])}"
    assert title in result or price_fragment in result, (
        f"Expected item title or price in caption.\nGot: {result}"
    )


# ── compare_price tests ───────────────────────────────────────────────────────

def test_compare_price_valid_assessment():
    """A real item in a well-populated category returns a non-empty assessment string."""
    items = search_listings("vintage graphic tee", size=None, max_price=None)
    assert items, "search_listings returned no results — check the dataset"
    result = compare_price(items[0])
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_compare_price_insufficient_comparables():
    """An item whose category has fewer than 3 other listings returns the sentinel."""
    rare_item = {"id": "fake-99", "price": 25.0, "category": "unicorn wear"}
    result = compare_price(rare_item)
    assert result == (
        "Not enough comparable listings were found to make a reliable price assessment."
    )


def test_compare_price_malformed_item():
    """An empty dict does not raise and returns the sentinel string."""
    result = compare_price({})
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_compare_price_output_contains_average_reasoning():
    """The assessment must mention both the item price and a comparable average."""
    items = search_listings("vintage graphic tee", size=None, max_price=None)
    assert items, "search_listings returned no results — check the dataset"
    item = items[0]
    result = compare_price(item)
    price_str = f"${item['price']:.2f}"
    assert price_str in result, f"Expected item price {price_str!r} in result.\nGot: {result}"
    assert "average" in result.lower(), f"Expected 'average' in result.\nGot: {result}"
