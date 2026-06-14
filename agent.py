"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        "fallback_attempts": [],     # filters relaxed during retry ("removed size filter", etc.)
        "fallback_message": None,    # human-readable note shown when a retry succeeds
    }


# ── query parser ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.
    No LLM — deterministic regex only.

    Handles:
        max_price: "under $30", "under 30", "below $45", "less than $25", "$30"
        size:      "size M", "size 8", "size S/M"

    Returns a dict with keys: description (str), size (str|None), max_price (float|None).
    """
    text = query.strip()
    size = None
    max_price = None

    # 1. Extract size phrase (e.g., "size M", "size 8", "size S/M")
    size_match = re.search(
        r'\bsize\s+([A-Za-z0-9]+(?:/[A-Za-z0-9]+)?)\b', text, re.IGNORECASE
    )
    if size_match:
        size = size_match.group(1)
        text = text[:size_match.start()] + text[size_match.end():]

    # 2. Keyword-led budget phrase: "under/below/less than" + optional "$" + number
    #    No trailing \b — the dollar sign between \s+ and \d+ breaks that assertion.
    budget_match = re.search(
        r'\b(?:under|below|less\s+than)\s+(?:\$)?(\d+(?:\.\d+)?)',
        text, re.IGNORECASE
    )
    if budget_match:
        max_price = float(budget_match.group(1))
        text = text[:budget_match.start()] + text[budget_match.end():]
    else:
        # 3. Fallback: bare dollar amount ("$30")
        dollar_match = re.search(r'\$(\d+(?:\.\d+)?)', text)
        if dollar_match:
            max_price = float(dollar_match.group(1))
            text = text[:dollar_match.start()] + text[dollar_match.end():]

    description = re.sub(r'\s+', ' ', text).strip().strip(',').strip()
    return {"description": description, "size": size, "max_price": max_price}


# ── helpers ───────────────────────────────────────────────────────────────────

def _keyword_score(item: dict, keywords: list[str]) -> int:
    """Count how many keywords from the query appear in the item's searchable text."""
    if not keywords:
        return 0
    text = " ".join([
        item.get("title", ""),
        item.get("description", ""),
        " ".join(item.get("style_tags", [])),
    ]).lower()
    return sum(1 for kw in keywords if kw in text)


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)

    # Step 2 — parse the query into description, size, max_price
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size = parsed["size"]
    max_price = parsed["max_price"]

    # Step 3 — search; retry with progressively relaxed filters if needed
    results = search_listings(description, size, max_price)
    session["search_results"] = results

    keywords = description.lower().split()

    if not results:
        # Retry 1: remove size filter (keep price)
        if size is not None:
            results = search_listings(description, None, max_price)
            session["fallback_attempts"].append("removed size filter")
            if results:
                session["search_results"] = results
                session["fallback_message"] = (
                    "No exact matches were found, so I removed the size filter "
                    "and found a similar item."
                )

        # Retry 2: remove price filter (size already None from retry 1 or never set)
        if not results and max_price is not None:
            results = search_listings(description, None, None)
            session["fallback_attempts"].append("removed price filter")
            if results:
                session["search_results"] = results
                if size is not None:
                    session["fallback_message"] = (
                        "No exact matches were found, so I removed the size and price "
                        "filters and found a similar item."
                    )
                else:
                    session["fallback_message"] = (
                        "No exact matches were found, so I removed the price filter "
                        "and found a similar item."
                    )

    elif max_price is not None and keywords:
        # Quality check: if the top result is a partial keyword match and removing
        # the price filter would surface a fully-matching item, prefer the better result.
        current_score = _keyword_score(results[0], keywords)
        if current_score < len(keywords):
            better = search_listings(description, size, None)
            if better and _keyword_score(better[0], keywords) > current_score:
                results = better
                session["fallback_attempts"].append("removed price filter")
                session["search_results"] = results
                session["fallback_message"] = (
                    "No items fully matched your search under your budget, so I removed "
                    "the price filter and found a closer match."
                )

    if not results:
        session["error"] = (
            "No listings matched your search, even after relaxing the size and "
            "price filters. Try a broader description."
        )
        return session

    # Step 4 — select the top result
    session["selected_item"] = results[0]

    # Step 5 — suggest an outfit
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6 — generate the caption
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
