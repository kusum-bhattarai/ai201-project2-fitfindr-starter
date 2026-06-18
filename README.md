# FitFindr 🛍️

FitFindr is a multi-tool AI agent that helps you shop secondhand and figure out how to wear what you find. You describe what you're after in plain language; the agent searches a dataset of mock listings, styles the best match against your existing wardrobe, and writes a shareable "fit card" caption for it — handling the messy cases (no matches, empty wardrobe, missing data) without crashing.

> Built for Project 2 (AI201). Planning and spec live in [`planning.md`](planning.md).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root (already gitignored):

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com) — same key as Project 1.

## Running

```bash
python app.py            # launches the Gradio UI (http://127.0.0.1:7860)
python agent.py          # CLI: runs a happy-path and a no-results interaction
pytest tests/            # runs the tool tests
```

In the UI, type a request (optionally with a size and price), pick **Example wardrobe** or **Empty wardrobe (new user)**, and hit **Find it**. The three panels show the top listing, an outfit idea, and the fit card.

---

## Tool Inventory

All three tools live in [`tools.py`](tools.py). The documented signatures below match the code exactly.

### `search_listings(description, size, max_price) -> list[dict]`
**Purpose:** Find secondhand pieces in the dataset that match the request. Pure local function — no LLM call.

| Input | Type | Meaning |
|---|---|---|
| `description` | `str` | Free-text keywords (e.g. `"vintage graphic tee"`), scored against each listing's title, description, style_tags, category, and brand. |
| `size` | `str \| None` | Size filter; case-insensitive **substring** match (so `"M"` matches `"S/M"` and `"M"`). `None` skips size filtering. |
| `max_price` | `float \| None` | Inclusive price ceiling. `None` skips price filtering. |

**Returns:** A `list[dict]` of full listing dicts (`id, title, description, category, style_tags, size, condition, price, colors, brand, platform`), ranked by keyword-overlap score (highest first). Listings scoring 0 are dropped. Returns `[]` when nothing matches — never raises.

### `suggest_outfit(new_item, wardrobe) -> str`
**Purpose:** Style the found item, naming specific wardrobe pieces when possible. Calls Groq `llama-3.3-70b-versatile`.

| Input | Type | Meaning |
|---|---|---|
| `new_item` | `dict` | A single listing dict (the top search result). |
| `wardrobe` | `dict` | `{"items": [{id, name, category, colors, style_tags, notes}, ...]}`. May be empty. |

**Returns:** A non-empty `str` with 1–2 outfit ideas. With a populated wardrobe it names specific pieces; with an empty wardrobe it returns general styling advice instead.

### `create_fit_card(outfit, new_item) -> str`
**Purpose:** Turn an outfit into a short, casual, shareable social caption. Calls Groq `llama-3.3-70b-versatile` at temperature `0.9` so repeated calls vary.

| Input | Type | Meaning |
|---|---|---|
| `outfit` | `str` | The suggestion string from `suggest_outfit`. |
| `new_item` | `dict` | The listing dict — used to mention item name, price, and platform once each. |

**Returns:** A 2–4 sentence `str` caption. If `outfit` is empty/whitespace, returns a descriptive error string instead of calling the LLM.

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in [`agent.py`](agent.py) is sequential but **conditional** — it is not a fixed "call all three tools" pipeline. The search result decides whether the rest of the loop runs at all.

1. **Parse** the raw query with regex into `{description, size, max_price}` (`_parse_query`). Example: `"vintage graphic tee under $30"` → `description="vintage graphic tee"`, `size=None`, `max_price=30.0`.
2. **Search** by calling `search_listings(**parsed)`.
3. **Branch on the result:**
   - **Empty list →** set `session["error"]` to a message naming what to try (loosen size / raise budget / broaden keywords) and **return early.** `suggest_outfit` and `create_fit_card` are never called; `fit_card` stays `None`.
   - **Non-empty →** set `selected_item = search_results[0]` (top-ranked) and continue.
4. **Suggest outfit** with `suggest_outfit(selected_item, wardrobe)`.
5. **Create fit card** with `create_fit_card(outfit_suggestion, selected_item)`.
6. **Return** the session.

The agent's behavior visibly changes with input: a matchable query runs all three tools; an impossible query stops after step 3. That early-return branch is the core of the planning loop.

---

## State Management

A single `session` dict (built by `_new_session()`) is the one source of truth for an interaction. Each step reads what it needs from the session and writes its output back, so the next step picks it up — the user never re-enters anything.

| Field | Set by | Used by |
|---|---|---|
| `query` | session init | parser |
| `parsed` | step 1 (`_parse_query`) | `search_listings` |
| `search_results` | step 2 | the empty/non-empty branch |
| `selected_item` | step 4 | **both** `suggest_outfit` and `create_fit_card` |
| `wardrobe` | session init | `suggest_outfit` |
| `outfit_suggestion` | step 5 | `create_fit_card` |
| `fit_card` | step 6 | final output |
| `error` | error branch | checked first by `app.py` |

The key state flow: the item `search_listings` ranks first is stored once as `selected_item` and that **exact same dict object** is passed into both later tools (`session["selected_item"] is session["search_results"][0]` is `True`). Nothing is re-derived or re-typed between tool calls.

**Query parsing choice:** regex, not an LLM. It's deterministic, instant, and free — and the inputs (a phrase, an optional size, an optional price) are regular enough that regex handles them reliably.

---

## Error Handling Strategy

Every tool owns its failure mode and returns a usable value instead of raising.

| Tool | Failure mode | Response |
|---|---|---|
| `search_listings` | No listing matches all constraints | Returns `[]`. The loop sets a specific `error` and stops before styling — it tells the user what to change. |
| `suggest_outfit` | Wardrobe is empty | Detects `wardrobe["items"] == []` and returns **general styling advice** (vibe + what pairs well) instead of named-piece outfits. Also wraps the LLM call in try/except with a fallback string. |
| `create_fit_card` | Outfit string is empty/whitespace | Guards up front and returns `"Can't write a fit card without an outfit suggestion."` — no LLM call, no exception. Also has a try/except fallback caption. |

**Concrete example (from testing):** running the agent on `"designer ballgown size XXS under $5"` produces:

```
error: No listings matched "designer ballgown" (size XXS, under $5).
       Try removing the size filter, raising your budget, or using broader keywords.
fit_card: None
```

`search_listings` returned `[]`, the loop's early-return branch fired, and `suggest_outfit`/`create_fit_card` were never called — exactly the intended graceful degradation. In the UI this shows as the message in the first panel with the other two panels blank.

---

## Spec Reflection

**One way the spec helped:** Writing the Planning Loop section in `planning.md` *before* coding forced me to define the empty-results branch as an explicit early return. Because the branch was already specified, `run_agent` came together as a direct translation of the numbered steps, and the "don't call later tools on empty results" requirement was built in from the start rather than patched in afterward.

**One way implementation diverged:** The original spec treated query parsing as something that "could use regex or the LLM." During implementation I committed fully to regex and added a dedicated `_parse_query` helper in `agent.py` (handling `under $X`, `$X`, `size M`, numeric `size 8`, and standalone size tokens). This kept the loop deterministic and free, and made parsing independently testable — a small expansion beyond the loose spec.

---

## AI Usage

**1. Implementing the three tools (Claude / Claude Code).** I gave Claude each tool's spec block from `planning.md` (inputs with types, return value, failure mode) one at a time and asked it to implement the function in `tools.py` using `load_listings()` for data. I verified each against the spec before trusting it — for `search_listings`, that it filtered by all three params, scored by keyword overlap, dropped score-0 results, and returned `[]` rather than raising. I **kept** the keyword-scoring approach but **tightened** it by adding a stop-word list so noise words ("looking", "for", "the") didn't inflate scores, and I set `create_fit_card`'s temperature to `0.9` after confirming lower values produced near-identical captions.

**2. Implementing the planning loop (Claude / Claude Code).** I gave Claude the Architecture diagram plus the Planning Loop and State Management sections and asked it to implement `run_agent()`. Before accepting it I checked that it branched on `search_results == []` with an early return, read/wrote only through the `session` dict, and passed the *same* `selected_item` object into both later tools. I **overrode** the error message to name the actual failed constraints (size and budget) instead of a generic "no results" string, so the message is actionable for the user.
