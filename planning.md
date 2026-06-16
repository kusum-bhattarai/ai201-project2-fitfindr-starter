# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40-item mock listings dataset for pieces matching a keyword description, optionally filtered by size and a price ceiling, and returns the matches ranked by keyword relevance. It is a pure local function — no LLM call.

**Input parameters:**
- `description` (str): free-text keywords describing the item, e.g. `"vintage graphic tee"`. Scored against each listing's title, description, style_tags, category, and brand.
- `size` (str | None): size to filter by, e.g. `"M"`. Case-insensitive substring match against the listing's `size` field (so `"M"` matches `"S/M"` and `"M"`). `None` skips size filtering.
- `max_price` (float | None): inclusive price ceiling. `None` skips price filtering.

**What it returns:**
A `list[dict]` of full listing dicts (`id, title, description, category, style_tags, size, condition, price, colors, brand, platform`), sorted by relevance score (highest first). Listings with a relevance score of 0 are dropped. Returns `[]` when nothing matches — never raises.

**What happens if it fails or returns nothing:**
Returns an empty list `[]`. The agent (not the tool) detects the empty list, sets a helpful error message in the session, and stops before calling `suggest_outfit` — it suggests loosening the size or raising the budget.

---

### Tool 2: suggest_outfit

**What it does:**
Given one thrifted item and the user's wardrobe, asks the Groq LLM (`llama-3.3-70b-versatile`) to propose 1–2 complete outfits, naming specific wardrobe pieces when available.

**Input parameters:**
- `new_item` (dict): a single listing dict (the top search result) — the item being styled.
- `wardrobe` (dict): a wardrobe dict shaped `{"items": [ {id, name, category, colors, style_tags, notes}, ... ]}`. May be empty.

**What it returns:**
A non-empty `str` of outfit suggestions. When the wardrobe has items, it names specific pieces (e.g. "pair with your wide-leg khaki trousers and chunky white sneakers"). When the wardrobe is empty, it returns general styling advice for the item instead (what kinds of pieces pair well, what vibe it suits).

**What happens if it fails or returns nothing:**
Empty wardrobe → general styling advice (handled explicitly, no crash). If the LLM call raises, it returns a short fallback styling string rather than propagating the exception.

---

### Tool 3: create_fit_card

**What it does:**
Turns an outfit suggestion plus the item into a short, casual, shareable social caption (an "OOTD" / fit card) using the Groq LLM at a higher temperature so repeated calls vary.

**Input parameters:**
- `outfit` (str): the suggestion string returned by `suggest_outfit`.
- `new_item` (dict): the listing dict, used to mention the item name, price, and platform naturally.

**What it returns:**
A 2–4 sentence `str` caption that mentions the item name, price, and platform once each and captures the outfit's vibe — different each time for different inputs (temperature ~0.9).

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, it returns a descriptive error string (e.g. "Can't write a fit card without an outfit suggestion.") instead of calling the LLM or raising. LLM errors fall back to a simple templated caption.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): ...
- `wardrobe` (dict): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): ...

**What it returns:**
<!-- Describe the return value -->

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is sequential but **conditional** — each step only runs if the previous step produced usable state. It is not a fixed call-all-three sequence; the search result decides whether the rest of the loop runs at all.

1. **Parse the query.** Extract `description`, `size`, and `max_price` from the raw query string with regex (see State Management). Store in `session["parsed"]`.
2. **Search.** Call `search_listings(**parsed)`; store the list in `session["search_results"]`.
   - **Branch — empty results:** if `search_results == []`, set `session["error"]` to a message that names what to try (loosen size / raise budget) and **return the session immediately**. `suggest_outfit` and `create_fit_card` are *not* called, and `fit_card` stays `None`. This is the branch that proves the loop responds to what it receives.
   - **Branch — has results:** set `session["selected_item"] = search_results[0]` (top-ranked match) and continue.
3. **Suggest outfit.** Call `suggest_outfit(selected_item, wardrobe)`; store in `session["outfit_suggestion"]`. (This tool internally branches on whether the wardrobe is empty.)
4. **Create fit card.** Call `create_fit_card(outfit_suggestion, selected_item)`; store in `session["fit_card"]`.
5. **Done.** Return the session. The loop is "done" when either `error` is set (early return) or `fit_card` is populated.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()` in `agent.py`) is the one source of truth for the interaction. Each step reads what it needs from the session and writes its output back, so the next step picks it up without the user re-entering anything:

- `query` (str) — the raw input.
- `parsed` (dict) — `{description, size, max_price}` extracted from the query. **Parsing approach:** regex — `max_price` from patterns like `under $30` / `$30` / `30 dollars`; `size` from `size M`, a standalone token like `size 8`, or a recognized size token (XS/S/M/L/XL or numeric); everything else becomes `description`. Chosen over an LLM parse for speed, determinism, and zero cost.
- `search_results` (list[dict]) — output of `search_listings`, read in the empty-vs-nonempty branch.
- `selected_item` (dict) — `search_results[0]`; the *exact same dict object* is passed into both `suggest_outfit` and `create_fit_card`, so no data is re-derived or re-entered between tools.
- `wardrobe` (dict) — passed in at session creation, read by `suggest_outfit`.
- `outfit_suggestion` (str) — output of `suggest_outfit`, fed directly into `create_fit_card`.
- `fit_card` (str) — final output.
- `error` (str | None) — `None` on success; set on early termination, checked first by callers (`app.py`).

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Tool returns `[]`. Loop sets `session["error"]` = e.g. *"No listings matched 'designer ballgown' in size XXS under $5. Try removing the size filter or raising your budget."* and returns early — does **not** call `suggest_outfit`. |
| suggest_outfit | Wardrobe is empty (`wardrobe["items"] == []`) | Tool detects the empty list and returns **general styling advice** for the item (vibe, what kinds of pieces pair well) instead of named-piece outfits. No crash, non-empty string. The loop continues normally. |
| create_fit_card | Outfit input is missing or incomplete (empty/whitespace string) | Tool guards up front and returns a descriptive error string (*"Can't write a fit card without an outfit suggestion."*) — no LLM call, no exception. |

---

## Architecture

```
User query + wardrobe choice  (app.py: handle_query)
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  run_agent()  — PLANNING LOOP                          SESSION (dict)       │
│                                                        ┌──────────────────┐ │
│  1. parse query (regex) ──────────────────────────────►│ parsed           │ │
│        │  {description, size, max_price}                │ {desc,size,price}│ │
│        ▼                                                │                  │ │
│  2. search_listings(description, size, max_price) ─────►│ search_results[] │ │
│        │                                                │                  │ │
│        ├─ results == []  ──► set error ───────────────►│ error = "..."    │ │
│        │                     RETURN EARLY  ───────────────────────────────┼─┐
│        │                     (suggest_outfit/create_fit_card NOT called)  │ │
│        │                                                │                  │ │
│        │  results not empty                             │                  │ │
│        ▼                                                │                  │ │
│     selected_item = search_results[0] ────────────────►│ selected_item    │ │
│        │                                                │                  │ │
│  3. suggest_outfit(selected_item, wardrobe) ──────────►│ outfit_suggestion│ │
│        │   └─ wardrobe empty → general styling advice   │                  │ │
│        ▼                                                │                  │ │
│  4. create_fit_card(outfit_suggestion, selected_item)─►│ fit_card         │ │
│        │   └─ outfit empty → error string (no LLM)      │                  │ │
│        ▼                                                └──────────────────┘ │
│     RETURN session  ◄─────────────────────────────────────── error path ────┼─┘
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  app.py maps session → 3 output panels (listing / outfit / fit card)
```

Tools 2 and 3 call the Groq LLM (`llama-3.3-70b-versatile`); `search_listings` is pure local filtering.

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
I'll use Claude (Claude Code) one tool at a time. For `search_listings` I'll give it the Tool 1 block above (inputs, scored return value, empty-list failure mode) plus the listing field list, and ask it to implement the function using `load_listings()` — no re-reading files. Before trusting it I'll confirm it (a) filters by all three params, (b) scores by keyword overlap and drops score-0 items, (c) returns `[]` rather than raising — then run the three pytest cases (results, empty, price filter). For `suggest_outfit` and `create_fit_card` I'll give Claude each tool block and require: a real Groq `llama-3.3-70b-versatile` call, the empty-wardrobe branch / empty-outfit guard respectively, and temperature ~0.9 on the fit card. I'll verify by running each tool on a hardcoded item and checking the failure branch returns a string, not a traceback.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the Architecture diagram, the Planning Loop section, and the State Management section together, and ask it to implement `run_agent()` to match the numbered branches. Before running I'll check that it (a) branches on `search_results == []` and returns early without calling the later tools, (b) reads/writes only through the `session` dict, and (c) passes the *same* `selected_item` object into both later tools. I'll verify with `python agent.py` (happy path populates `fit_card`; no-results path sets `error` and leaves `fit_card` None).

---

## A Complete Interaction (Step by Step)

**What FitFindr does (overview):** FitFindr is a multi-tool agent that takes a natural language thrifting request and runs it through a planning loop. It first triggers `search_listings` to find secondhand pieces matching the user's described item, size, and budget; the top match then triggers `suggest_outfit` to style it against the user's existing wardrobe, and that suggestion triggers `create_fit_card` to write a shareable caption. If `search_listings` finds nothing the loop stops early with a helpful message instead of calling the later tools, and the LLM-backed tools degrade gracefully (general styling advice for an empty wardrobe, an error string for a missing outfit) rather than crashing.

---

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse.** `run_agent` creates the session and parses the query with regex: `max_price = 30.0` (from "under $30"), `size = None` (no size given), `description = "looking for a vintage graphic tee"`. Stored in `session["parsed"]`.

**Step 2 — Search.** Calls `search_listings("looking for a vintage graphic tee", size=None, max_price=30.0)`. Listings are filtered to price ≤ 30, scored on keyword overlap; matches like *"Graphic Tee — 2003 Tour Bootleg Style"* ($24, depop) and *"Y2K Baby Tee — Butterfly Print"* ($18, depop) score highest. Returns a ranked list; the loop sees it's non-empty and sets `session["selected_item"]` to the top result (the bootleg graphic tee).

**Step 3 — Suggest outfit.** Calls `suggest_outfit(selected_item=<graphic tee>, wardrobe=<example wardrobe>)`. The wardrobe has items, so the LLM names specific pieces, e.g. *"Wear it with your baggy straight-leg jeans and chunky white sneakers; throw the vintage black denim jacket over it for a 90s grunge look."* Stored in `session["outfit_suggestion"]`.

**Step 4 — Fit card.** Calls `create_fit_card(outfit=<suggestion>, new_item=<graphic tee>)`. The LLM (temp ~0.9) returns something like *"thrifted this faded bootleg tee off depop for $24 and it was MADE for my baggy jeans 🖤 grunge szn fr."* Stored in `session["fit_card"]`.

**Final output to user:**
The Gradio UI shows three panels: the listing (title, price, platform, condition, size), the outfit suggestion, and the fit-card caption. On the no-results query, only the first panel shows the error message and the other two are empty.
