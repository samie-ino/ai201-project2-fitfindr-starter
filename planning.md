# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

**What FitFindr does (in my own words):** FitFindr is a thrift-shopping assistant that takes one natural-language request and returns a ready-to-post find. It searches a mock secondhand-listings dataset for items matching the user's keywords, size, and price ceiling (`search_listings` runs first, triggered by the incoming query); if at least one listing matches, it picks the top result and asks an LLM to style that item against the user's wardrobe (`suggest_outfit`), then turns that styling into a short, casual social caption (`create_fit_card`). When `search_listings` returns nothing, the agent stops immediately, tells the user how to loosen their query, and never calls the styling or caption tools with empty input.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Filters and ranks the mock listings dataset (loaded via `load_listings()`) against the user's keywords, optional size, and optional price ceiling, returning the best matches first. It is the only tool that touches the listings data, and it is deterministic (no LLM call).

**Input parameters:**
- `description` (str): Keywords describing the desired item, e.g. `"vintage graphic tee"`. Tokenized and matched (case-insensitive) against each listing's `title`, `description`, `style_tags`, and `category`.
- `size` (str | None): Size to filter by, e.g. `"M"`. Matching is case-insensitive and substring-based so `"M"` matches `"S/M"` and `"XL (oversized)"` is matched by `"XL"`. `None` skips size filtering.
- `max_price` (float | None): Inclusive price ceiling, e.g. `30.0`. A listing passes if `listing["price"] <= max_price`. `None` skips price filtering.

**What it returns:**
A `list[dict]` of full listing dicts, sorted by relevance score (highest first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Listings that pass the size/price filters but score 0 on keyword overlap are dropped. Returns `[]` when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
Returns an empty list `[]` (no exception). The planning loop treats `[]` as a hard stop: it sets `session["error"]` to an actionable message and returns early **without** calling `suggest_outfit`. The message names what to relax — e.g. *"No matches for 'designer ballgown' under $5 in size XXS. Try raising your max price, removing the size filter, or using broader keywords like 'dress'."*

---

### Tool 2: suggest_outfit

**What it does:**
Given the selected listing and the user's wardrobe, calls the LLM (Groq) to write 1–2 concrete outfit suggestions that pair the new item with named pieces the user already owns, including a small styling tip (tuck, roll, layer).

**Input parameters:**
- `new_item` (dict): A single listing dict (the top `search_listings` result). The prompt uses its `title`, `category`, `colors`, `style_tags`, and `condition`.
- `wardrobe` (dict): A wardrobe dict shaped like `{"items": [ {id, name, category, colors, style_tags, notes}, ... ]}` (the schema in `data/wardrobe_schema.json`). May be empty (`{"items": []}`) and must be handled gracefully.

**What it returns:**
A non-empty `str` of natural-language styling advice, e.g. *"Pair this with your baggy straight-leg jeans and chunky white sneakers for a 90s streetwear look — tuck the front hem for shape."* When `wardrobe["items"]` is empty, it returns general styling advice for the item (what vibe/pieces pair well) instead of referencing nonexistent wardrobe pieces. Never returns an empty string.

**What happens if it fails or returns nothing:**
- Empty wardrobe → returns general styling advice (not an error); the loop continues to `create_fit_card`.
- LLM/network failure → catches the exception and returns a short fallback styling string built from the item's `style_tags` so the pipeline still produces a fit card; the loop continues.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion into a short, shareable OOTD-style caption (Instagram/TikTok voice) for the thrifted find. Uses the LLM at a higher temperature so repeated calls read differently.

**Input parameters:**
- `outfit` (str): The styling string returned by `suggest_outfit()`.
- `new_item` (dict): The selected listing dict. The caption pulls `title`, `price`, and `platform` from it and works them in naturally (once each).

**What it returns:**
A `str` of 2–4 sentences in a casual, authentic voice — e.g. *"thrifted this faded band tee off depop for $22 and it was made for my wide-legs 🖤 full look in my stories"*. Mentions item name, price, and platform once each and captures the outfit vibe in specific terms.

**What happens if it fails or returns nothing:**
- If `outfit` is empty or whitespace-only, it returns a descriptive error string (e.g. *"Can't build a fit card without an outfit suggestion."*) rather than raising.
- LLM/network failure → returns a plain-text fallback caption assembled from the item's `title`, `price`, and `platform` so the user still gets something postable.

---

### Additional Tools (if any)

None for the core build. If added later (stretch), a `parse_query(query) -> {description, size, max_price}` LLM helper would be documented here with the same four fields. For now query parsing lives inside the planning loop (see below), not as a separate tool.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed pipeline with one early-exit branch — it does not free-form "decide"; the branch points are explicit and data-driven.

1. **Initialize** — `session = _new_session(query, wardrobe)`.
2. **Parse the query** — extract `description`, `size`, and `max_price` from the raw query and store them in `session["parsed"]`. Approach: lightweight rules — regex for price (`under $30`, `$30`, `30 dollars` → `max_price=30.0`) and for size (a token list `XS/S/M/L/XL` plus `size <token>`); the remaining cleaned text becomes `description`. If a field isn't found it stays `None`.
3. **Call `search_listings`** with the parsed params; store the list in `session["search_results"]`.
   - **Branch (error):** `if not session["search_results"]:` set `session["error"]` to an actionable "no results" message and `return session` immediately. **Do not** call `suggest_outfit`.
   - **Branch (success):** continue.
4. **Select item** — `session["selected_item"] = session["search_results"][0]` (top-ranked result).
5. **Call `suggest_outfit(selected_item, wardrobe)`** — store the string in `session["outfit_suggestion"]`. Empty wardrobe is not an error (tool returns general advice); the loop proceeds.
6. **Call `create_fit_card(outfit_suggestion, selected_item)`** — store the string in `session["fit_card"]`.
7. **Done** — `return session`. The loop knows it's finished when `fit_card` is set with no error, or earlier when `error` is set. Each step is reached only if the prior step produced usable output.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session`) is the one source of truth for the whole run; tools never call each other directly — the loop reads from and writes to `session` between calls.

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | `_new_session` | parse step |
| `parsed` (`{description, size, max_price}`) | parse step | `search_listings` call |
| `search_results` (list[dict]) | after `search_listings` | error check, item selection |
| `selected_item` (dict) | item-selection step | `suggest_outfit`, `create_fit_card` |
| `wardrobe` (dict) | `_new_session` | `suggest_outfit` |
| `outfit_suggestion` (str) | after `suggest_outfit` | `create_fit_card` |
| `fit_card` (str) | after `create_fit_card` | returned to caller / UI |
| `error` (str \| None) | any early-exit point | caller checks **first** |

Contract for the caller: check `session["error"]` first. If it's not `None`, the run ended early and `outfit_suggestion`/`fit_card` are `None`. State flows strictly forward: the output one tool writes is the named input the loop hands to the next.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` and return early (no downstream calls). Message names the exact filters used and what to relax — e.g. *"No matches for 'designer ballgown' under $5 in size XXS. Try raising your max price, dropping the size filter, or broader keywords like 'dress'."* Offers nothing fabricated. |
| suggest_outfit | Wardrobe is empty | Not treated as an error. Tool returns general styling advice for the item ("this faded tee leans grunge — pair it with baggy denim and chunky sneakers; layer a flannel for cooler days"). Pipeline continues to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | If `outfit` is empty/whitespace, return a descriptive string — *"Can't write a fit card without an outfit suggestion — try styling the item first."* — instead of raising. On LLM failure, return a plain fallback caption from the item's title/price/platform so the user still gets something usable. |

Cross-cutting: any LLM/network exception in Tools 2–3 is caught and converted to a graceful fallback string so a single API hiccup never crashes the run or returns an empty UI.

---

## Architecture

```
                    User query  +  wardrobe
                          │
                          ▼
            ┌─────────────────────────────────────────────────────────┐
            │                   PLANNING LOOP (run_agent)               │
            │                                                           │
            │   _new_session(query, wardrobe) ──► session dict ◄────────┤  (state read/write
            │            │                                              │   throughout)
            │            ▼                                              │
            │   parse query ──► session["parsed"] = {description,       │
            │            │                            size, max_price}  │
            │            ▼                                              │
            │   search_listings(description, size, max_price)           │
            │            │                                              │
            │            ├── results == []                              │
            │            │      └─►[ERROR] session["error"]=            │
            │            │              "No listings found, try…"       │
            │            │              return session ─────────────────┼──► (early return)
            │            │                                              │
            │            │   results == [item, ...]                     │
            │            ▼                                              │
            │   session["search_results"] = results                    │
            │   session["selected_item"]  = results[0]                 │
            │            │                                              │
            │            ▼                                              │
            │   suggest_outfit(selected_item, wardrobe)                 │
            │            │   (empty wardrobe → general advice, no error)│
            │            ▼                                              │
            │   session["outfit_suggestion"] = "..."                   │
            │            │                                              │
            │            ▼                                              │
            │   create_fit_card(outfit_suggestion, selected_item)      │
            │            │                                              │
            │            ▼                                              │
            │   session["fit_card"] = "..."                            │
            └────────────┼──────────────────────────────────────────────┘
                         ▼
                  return session  ──►  UI shows selected_item + outfit + fit_card
                                       (or session["error"] if set)
```

Data flow summary: the **session dict** is shared state read and written between every step. `search_listings` output (`results[0]`) becomes `suggest_outfit`'s `new_item`; `suggest_outfit`'s string becomes `create_fit_card`'s `outfit`. The single error branch lives on the `search_listings` empty-result check and terminates the run before any LLM tool is called.

---

## AI Tool Plan

**Tool of choice:** Claude (Claude Code / chat). For each piece I paste the relevant planning.md section verbatim as the spec, plus the function stub from `tools.py`/`agent.py` so generated code keeps the exact signature.

**Milestone 3 — Individual tool implementations:**
- **`search_listings`** — Input to Claude: the **Tool 1** block above (inputs, return fields, empty-result rule) + the `search_listings` stub from `tools.py`. Expected output: a function that loads data via `load_listings()`, filters by `max_price` and case-insensitive substring `size`, scores by keyword overlap across title/description/style_tags/category, drops score-0 rows, and returns results sorted high→low. Verify before trusting: read the diff to confirm it (a) filters on all three params, (b) returns `[]` not `None` on no match, (c) uses `load_listings()` rather than re-reading the file; then run 3 queries — `"vintage graphic tee"/M/30` (expect lst_006-type hits), `"designer ballgown"/XXS/5` (expect `[]`), `"denim"/None/None` (expect several).
- **`suggest_outfit`** — Input: the **Tool 2** block + stub. Expected: a function that branches on empty `wardrobe["items"]`, formats wardrobe items into the prompt, calls Groq, returns a non-empty string, and try/except-falls-back on API error. Verify: run once with `get_example_wardrobe()` (output should name real wardrobe pieces) and once with `get_empty_wardrobe()` (output should give general advice, not invent items), and confirm neither returns `""`.
- **`create_fit_card`** — Input: the **Tool 3** block + stub. Expected: guards empty `outfit`, prompts for a 2–4 sentence casual caption mentioning name/price/platform once each, higher temperature. Verify: feed a real outfit string and check the caption contains the price and platform and reads casually; feed `""` and confirm it returns the descriptive error string, not a crash.

**Milestone 4 — Planning loop and state management:**
- **`run_agent`** — Input to Claude: the **Planning Loop**, **State Management**, and **Architecture** (diagram) sections + the `run_agent`/`_new_session` stubs from `agent.py`. Expected: code that parses the query into `session["parsed"]`, calls the three tools in order, writes each result to the named session field, and returns early with `session["error"]` set when `search_results` is empty. Verify before trusting: walk the generated code against the diagram branch-by-branch (does the empty-results path `return` before `suggest_outfit`?); then run the two CLI cases in `agent.py` — the graphic-tee happy path (expect populated `selected_item`/`outfit_suggestion`/`fit_card`, `error is None`) and the `"designer ballgown size XXS under $5"` path (expect `error` set, the other fields `None`).

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse + Search.**
The loop initializes the session, then parses the query into `{"description": "vintage graphic tee", "size": None, "max_price": 30.0}` (no explicit size given → `None`). It calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. This filters out anything over $30, scores the rest on keyword overlap (`vintage`/`graphic`/`tee`), and returns matches sorted best-first. The top result is `lst_002` ("Y2K Baby Tee — Butterfly Print", $18, depop) — its `title`+`style_tags` hit all three query tokens for a score of 3, and it precedes the equally-scored `lst_006` ("Graphic Tee — 2003 Tour Bootleg Style", $24) because ties keep dataset order. `session["search_results"]` is non-empty, so the loop continues.

**Step 2 — Select + Suggest outfit.**
The loop sets `session["selected_item"] = search_results[0]` (the $18 Y2K baby tee). It calls `suggest_outfit(new_item=<lst_002>, wardrobe=<example wardrobe>)`. The LLM sees the tee's tags (y2k, vintage, graphic tee) and the user's real pieces and returns something like: *"Pair the Y2K baby tee with your baggy straight-leg jeans and chunky white sneakers for a casual streetwear look — tuck the tee for a defined waist. Or layer it under your vintage black denim jacket with the wide-leg khaki trousers and combat boots."* Stored in `session["outfit_suggestion"]`.

**Step 3 — Fit card.**
The loop calls `create_fit_card(outfit=<suggestion>, new_item=<lst_002>)`. The LLM returns a casual caption mentioning the title, the $18 price, and depop once each: *"just scored this adorable y2k baby tee on depop for $18 and i'm obsessed 💖 paired it with my baggy jeans + chunky sneakers for a laid-back streetwear vibe. full fit in stories."* Stored in `session["fit_card"]`. The loop returns the session.

**Final output to user:**
The UI shows the picked listing ("Y2K Baby Tee — Butterfly Print — $18, depop, excellent condition"), the outfit suggestion from Step 2, and the shareable fit-card caption from Step 3. `session["error"]` is `None`. (Had `search_listings` returned `[]` in Step 1 — e.g. "designer ballgown size XXS under $5" — the user would instead see only the error message telling them what to relax, and Steps 2–3 would never run.)
