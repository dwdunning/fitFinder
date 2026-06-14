"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.
    """
    listings = load_listings()
    keywords = description.lower().split()

    scored = []
    for listing in listings:
        # Price filter
        if max_price is not None and listing.get("price", 0) > max_price:
            continue

        # Size filter — case-insensitive substring check to tolerate format variation
        if size is not None:
            listing_size = listing.get("size", "")
            if size.lower() not in listing_size.lower():
                continue

        # Keyword scoring across title, description, and style_tags
        if not keywords:
            continue

        searchable = " ".join([
            listing.get("title", ""),
            listing.get("description", ""),
            " ".join(listing.get("style_tags", [])),
        ]).lower()

        score = sum(1 for kw in keywords if kw in searchable)
        if score == 0:
            continue

        scored.append((score, listing))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    """
    wardrobe_items = wardrobe.get("items", [])

    title = new_item.get("title", "This piece")
    category = new_item.get("category", "item")
    style_tags = new_item.get("style_tags", [])
    colors = new_item.get("colors", [])

    style_str = ", ".join(style_tags) if style_tags else "versatile"
    color_str = ", ".join(colors) if colors else "neutral"

    if wardrobe_items:
        # Build a deterministic fallback that names actual wardrobe pieces
        names = [item.get("name", "") for item in wardrobe_items[:3] if item.get("name")]
        if len(names) == 0:
            fallback = f"{title} works well with simple basics and neutral footwear."
        elif len(names) == 1:
            fallback = f"Try pairing {title} with your {names[0]} for a complete look."
        elif len(names) == 2:
            fallback = (
                f"Try pairing {title} with your {names[0]} and {names[1]} "
                f"for a complete look."
            )
        else:
            fallback = (
                f"Try pairing {title} with your {names[0]}, {names[1]}, "
                f"and {names[2]} for a complete look."
            )

        wardrobe_lines = "\n".join(
            f"- {item.get('name', 'unknown item')}"
            for item in wardrobe_items
        )
        prompt = (
            f"I'm considering buying this secondhand item:\n"
            f"Name: {title}\n"
            f"Category: {category}\n"
            f"Style: {style_str}\n"
            f"Colors: {color_str}\n\n"
            f"My wardrobe includes:\n{wardrobe_lines}\n\n"
            f"Suggest a complete outfit using this new item paired with specific pieces "
            f"from my wardrobe above. Mention the wardrobe pieces by name. "
            f"Keep your response to 2-3 sentences."
        )
    else:
        style_note = f" with a {style_tags[0]} aesthetic" if style_tags else ""
        fallback = f"{title} pairs well with simple basics and neutral footwear{style_note}."

        prompt = (
            f"I'm considering buying this secondhand item:\n"
            f"Name: {title}\n"
            f"Category: {category}\n"
            f"Style: {style_str}\n"
            f"Colors: {color_str}\n\n"
            f"I don't have my wardrobe listed yet. Give me general styling advice: "
            f"what types of clothing and shoes pair well with this piece and what vibe it suits. "
            f"Keep your response to 2-3 sentences."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        return result if result else fallback
    except Exception:
        return fallback


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    """
    # Guard first — return exact error string before any LLM call
    if not outfit or not outfit.strip():
        return "Could not generate caption — outfit suggestion was missing."

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    platform = new_item.get("platform", "a resale platform")
    condition = new_item.get("condition", "")
    style_tags = new_item.get("style_tags", [])
    colors = new_item.get("colors", [])

    price_str = f"${price:.2f}" if price is not None else "a great price"
    style_str = ", ".join(style_tags) if style_tags else "versatile"
    color_str = ", ".join(colors) if colors else "various"
    vibe = style_tags[0] if style_tags else "thrifted"

    # Deterministic fallback includes title, price, and platform when available
    fallback = (
        f"Found this {vibe} gem — {title} for {price_str} on {platform}. "
        f"{outfit.strip()}"
    )

    prompt = (
        f"Write a short Instagram/TikTok caption (1-3 sentences) for this thrifted outfit.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Condition: {condition}\n"
        f"Style: {style_str}\n"
        f"Colors: {color_str}\n\n"
        f"Outfit:\n{outfit}\n\n"
        f"Guidelines:\n"
        f"- Sound casual and authentic, like a real OOTD post\n"
        f"- Mention the item name ({title}), price ({price_str}), and platform ({platform}) "
        f"naturally, once each\n"
        f"- Reference the outfit vibe\n"
        f"- No bullet points, headers, or structured formatting\n"
        f"- 1-3 sentences total"
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.8,
        )
        result = response.choices[0].message.content.strip()
        return result if result else fallback
    except Exception:
        return fallback
