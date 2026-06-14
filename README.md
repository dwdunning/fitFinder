# FitFindr

A multi-tool AI agent for secondhand outfit discovery. Built for CodePath AI201.

---

## Project Overview

FitFindr takes a natural-language shopping request and runs it through a three-step planning loop: it searches a dataset of 40 mock secondhand listings for items that match the user's description, size, and budget; asks an LLM to suggest a complete outfit by pairing the top result with the user's existing wardrobe; and generates a short social-media-style caption for the look. The whole interaction is surfaced through a Gradio interface with three output panels.

The agent is designed to fail gracefully at every step. If no listings match, the loop stops immediately. If the wardrobe is empty, the outfit tool still returns useful general styling advice. If the LLM is unavailable, each tool falls back to a deterministic response built from the item data.

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Filters the mock listings dataset against the user's description, optional size, and optional price ceiling.

**Inputs:**
- `description` (str) — natural language description of what the user wants. Split into lowercase keywords and matched against each listing's `title`, `description`, and `style_tags` fields. Listings are scored by how many keywords match, then returned highest-score-first.
- `size` (str | None) — size string to filter by. Matching is case-insensitive and uses substring containment so that `"M"` matches `"S/M"` or `"M/L"`. Pass `None` to skip size filtering.
- `max_price` (float | None) — maximum price in USD. Listings where `price > max_price` are excluded. Pass `None` to skip price filtering.

**Output:** A list of listing dicts, each containing `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`. Returns `[]` if nothing matches.

**Failure handling:** Always returns a list — never raises an exception for empty results. An empty list is the signal to the planning loop to stop early.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Given a listing the user is considering buying and their existing wardrobe, suggests a complete outfit. Calls Groq (`llama-3.3-70b-versatile`, temperature 0.3) with a prompt that includes the item details and wardrobe item names.

**Inputs:**
- `new_item` (dict) — a listing dict from `search_listings`. All fields are accessed with `.get()` so a malformed or empty dict does not crash the function.
- `wardrobe` (dict) — a wardrobe dict with an `items` key containing a list of wardrobe item dicts (as returned by `get_example_wardrobe()` or `get_empty_wardrobe()`). Accessed via `wardrobe.get("items", [])`.

**Output:** A non-empty string describing an outfit. When the wardrobe has items, the string names specific pieces by their `name` field. When the wardrobe is empty, it returns general styling advice based on the item's category and style tags.

**Failure handling:** If the LLM call fails (missing API key, network error, empty response), the function returns a deterministic fallback built from the wardrobe item names and the item title. The fallback is computed before the LLM call so it is always available. The function never returns `None` or an empty string.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Generates a short social-media-style outfit caption (1–3 sentences) from the outfit suggestion and the listing details. Calls Groq (`llama-3.3-70b-versatile`, temperature 0.8) with a prompt that specifies a casual, authentic OOTD tone.

**Inputs:**
- `outfit` (str) — the outfit suggestion string from `suggest_outfit`. If this is `None`, empty, or whitespace-only, the function returns an error string immediately and never calls the LLM.
- `new_item` (dict) — the listing dict for the item being featured. Used to include the title, price, and platform in the caption. All fields accessed with `.get()`.

**Output:** A short caption string that naturally mentions the item title, price, and platform. Higher temperature than `suggest_outfit` so repeated calls on the same item produce varied captions.

**Failure handling:** Guards against empty `outfit` input first — returns `"Could not generate caption — outfit suggestion was missing."` without touching the LLM. If the LLM call fails, returns a deterministic fallback caption that includes the item title, price, and platform.

---

## Planning Loop

The agent runs a sequential, conditional loop. Each step checks its result before the next step is called.

```
1.  Initialize session dict with _new_session(query, wardrobe)
2.  Parse query with _parse_query() → description, size, max_price
3.  Store parsed values in session["parsed"]
4.  Call search_listings(description, size, max_price)
5.  Store results in session["search_results"]
6.  If results is [] →
        session["error"] = "No listings matched..."
        return session   ← stops here; does not call suggest_outfit or create_fit_card
7.  session["selected_item"] = results[0]
8.  Call suggest_outfit(selected_item, wardrobe)
9.  session["outfit_suggestion"] = returned string
10. Call create_fit_card(outfit_suggestion, selected_item)
11. session["fit_card"] = returned caption
12. Return session
```

**When search returns no results:** The agent sets `session["error"]` to a helpful message and returns the session immediately. `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` all remain `None`. The caller can check `session["error"]` to distinguish this case from a successful run.

**Query parsing** (`_parse_query`) is deterministic — no LLM. It uses regex to extract:
- Budget phrases: `"under $30"`, `"under 30"`, `"below $45"`, `"less than $25"`, or a bare `"$30"`
- Size phrases: `"size M"`, `"size 8"`, `"size S/M"`

After extracting size and price, the remaining text becomes the `description` passed to `search_listings`.

---

## State Management

The agent maintains a single session dict across the full interaction:

```python
session = {
    "query": "",             # original user message
    "parsed": {},            # {"description": str, "size": str|None, "max_price": float|None}
    "search_results": [],    # list of listing dicts from search_listings
    "selected_item": None,   # single listing dict (first result)
    "wardrobe": {},          # user's wardrobe dict
    "outfit_suggestion": None,  # string from suggest_outfit
    "fit_card": None,        # caption string from create_fit_card
    "error": None,           # set if interaction ended early
}
```

Each tool reads its inputs from the session and writes its output back before the loop advances. This means tools can be called and tested independently by pre-populating the relevant keys. The `error` key being non-`None` is the signal that the interaction ended early — all downstream fields will be `None` in that case.

---

## Error Handling

### `search_listings` — no results

**Query:** `"designer ballgown size XXS under $5"`

The parser extracts `description="designer ballgown"`, `size="XXS"`, `max_price=5.0`. No listing in the dataset matches all three filters. `search_listings` returns `[]`.

**Agent response:** The loop sets `session["error"] = "No listings matched your search. Try a different description, remove the size filter, or raise your budget."` and returns the session without calling `suggest_outfit` or `create_fit_card`.

In the Gradio UI, the error message appears in the first output panel and the other two panels are empty.

---

### `suggest_outfit` — empty wardrobe

**Input:** any listing dict + `get_empty_wardrobe()` (which returns `{"items": []}`)

The function detects `wardrobe.get("items", [])` is empty and skips the wardrobe-specific prompt. If the LLM is available, it asks for general styling advice instead of naming specific pieces. If the LLM is unavailable, the deterministic fallback returns something like:

`"Y2K Baby Tee — Butterfly Print pairs well with simple basics and neutral footwear with a y2k aesthetic."`

The loop continues normally to `create_fit_card` — an empty wardrobe is not a stop condition.

---

### `create_fit_card` — empty outfit string

**Input:** `create_fit_card("", some_item)`

The guard fires before any LLM call:

```python
if not outfit or not outfit.strip():
    return "Could not generate caption — outfit suggestion was missing."
```

**Response:** `"Could not generate caption — outfit suggestion was missing."` — a non-empty string, no exception raised.

---

## Spec Reflection

**One way planning.md helped:** The Planning Loop section was written as explicit numbered pseudocode with a named early-stop condition (`state["error"]` + `return state`). This translated almost directly to the `run_agent()` implementation — the conditional structure was already decided before any code was written, which made it easy to verify the early-stop path in tests without needing to re-read the full agent.

**One place implementation differed from the original plan:** The initial `suggest_outfit` fallback was:

```python
f"Pair this {category} with complementary pieces in similar tones. Its {style_str} aesthetic..."
```

This produced grammatically broken output like `"Pair this tops with complementary pieces..."` because `category` in the dataset is a plural noun (`"tops"`, `"bottoms"`). The fallback was revised to use the item's `title` directly and name actual wardrobe items by their `name` field, which fixed the grammar and made the fallback meaningfully different from the LLM response rather than just a worse version of it.

---

## AI Usage

**Implementing `search_listings`:** I gave Claude the Tool 1 specification from `planning.md` — the input parameters, return value description, and failure mode — along with the `load_listings()` function signature and listing field list from `utils/data_loader.py`. Claude generated a keyword-scoring implementation that filters by price and size then ranks by match count. Before accepting it, I added three pytest tests (valid query, no-results query, price-filter correctness) and confirmed they passed against the real dataset. I also noticed the size matching used exact equality, which would miss `"S/M"` when searching for `"M"` — I changed it to a case-insensitive substring check.

**Implementing `run_agent`:** I gave Claude the Planning Loop section (including the numbered pseudocode), the State Management section (including the session dict definition), the Error Handling table, and the Architecture diagram from `planning.md`, plus the three function signatures from `tools.py`. Claude generated a `run_agent()` function that followed the loop structure. I verified the early-stop path by running a test with a low `max_price` that returns no results and confirming that `session["outfit_suggestion"]` and `session["fit_card"]` were still `None` after the call.

---

## Testing

In addition to the required tests, I used repeated validation runs and targeted failure-mode tests to verify that changes to matching logic, query parsing, and fallback behavior did not break previously working scenarios.

The project has **31 pytest tests** across two test files.

**`tests/test_tools.py` (17 tests)** covers each tool in isolation:
- `search_listings`: valid query returns results, no-match returns `[]`, price filter excludes over-budget items, results are dicts with expected keys, empty description returns `[]`, relevance ordering.
- `suggest_outfit`: non-empty return with example wardrobe, non-empty return with empty wardrobe, no crash on malformed `new_item`, never returns `None`, wardrobe item name appears in result.
- `create_fit_card`: valid input returns non-empty string, empty outfit returns exact error string, whitespace outfit returns same error string, malformed item does not crash, title or price appears in output.

**`tests/test_agent.py` (14 tests)** covers the parser and planning loop:
- `_parse_query`: six price format cases (`under $30`, `under 30`, `$30`, `below $45`, `less than $25`, no price), three size cases, three description-cleaning cases, one full multi-part query.
- `run_agent`: no-results path sets `session["error"]` and leaves `selected_item`, `outfit_suggestion`, and `fit_card` as `None`; a second no-results test confirms `search_results` is `[]` and `fit_card` is untouched.

Run all tests from the project root:

```bash
pytest tests/ -v
```


---

## Setup

```bash
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com).

Run the app:

```bash
python app.py
```

Then open the localhost URL shown in your terminal (usually `http://localhost:7860`).

Run all tests:

```bash
pytest tests/ -v
```
