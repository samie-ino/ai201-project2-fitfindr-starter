# FitFindr 🛍️

FitFindr is a thrift-shopping assistant. You describe what you're after in plain
language ("vintage graphic tee under $30, size M"); it searches a mock
secondhand-listings dataset, picks the best match, styles it against your
wardrobe, and writes a short, shareable caption for the find. It runs as a small
Gradio web app backed by a deterministic planning loop and three tools.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Mac/Linux  (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
```

Add your Groq API key to a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python app.py
```

Open the URL printed in your terminal (usually http://localhost:7860 — check the
output, the port can differ). Enter a query, pick a wardrobe, and hit **Find it**.

### Run the tests

```bash
pytest tests/
```

17 tests cover each tool, each failure mode, query parsing, and the planning
loop's branch behavior.

---

## How it works

```
User query + wardrobe → run_agent (planning loop) → 3 tools → session dict → UI
```

The agent is **not** a free-form "decide what to do next" loop. It's a fixed
three-stage pipeline with exactly one branch point — the search result. Every
piece of state lives in a single `session` dict that the loop reads from and
writes to between tool calls; the tools never call each other.

### Tool inventory

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| **search_listings** | `description: str`, `size: str \| None`, `max_price: float \| None` | `list[dict]` — matching listings sorted best-first; `[]` if none match | Filter + rank the mock dataset. The only tool that touches listings data; fully deterministic (no LLM). |
| **suggest_outfit** | `new_item: dict` (a listing), `wardrobe: dict` (`{"items": [...]}`) | `str` — 1–2 outfit ideas naming the user's pieces, with a styling tip | Style the selected item against the user's wardrobe via the Groq LLM. |
| **create_fit_card** | `outfit: str`, `new_item: dict` | `str` — a 2–4 sentence casual social caption | Turn the outfit into a shareable OOTD post. Higher LLM temperature so repeated calls vary. |

**search_listings details.** `description` is tokenized and matched
case-insensitively against each listing's `title`, `description`, `category`,
and `style_tags`; a listing's score is the count of overlapping tokens. `size`
is a case-insensitive substring match (so `"M"` matches `"S/M"` and `"XL"`
matches `"XL (oversized)"`). `max_price` is an inclusive ceiling. Listings that
pass the size/price filters but score 0 on keyword overlap are dropped; the rest
are returned highest-score-first (ties keep dataset order).

Each returned listing dict contains: `id`, `title`, `description`, `category`,
`style_tags` (list), `size`, `condition`, `price` (float), `colors` (list),
`brand`, `platform`.

### The planning loop

`run_agent(query, wardrobe)` in [agent.py](agent.py) runs these steps:

1. **Initialize** a fresh `session` dict (`_new_session`).
2. **Parse** the query into `description` / `size` / `max_price` with simple
   rules (regex for price phrases like "under $30"; "size X" or a standalone
   size word for size; the remaining text is the description). Stored in
   `session["parsed"]`.
3. **Search** — call `search_listings` with the parsed params; store results in
   `session["search_results"]`. **This is the only branch:**
   - **Empty results →** set `session["error"]` to an actionable message and
     `return` immediately. The agent does **not** call `suggest_outfit` with
     empty input.
   - **Has results →** continue.
4. **Select** `session["search_results"][0]` (top-ranked) into
   `session["selected_item"]`.
5. **Suggest outfit** — `suggest_outfit(selected_item, wardrobe)` →
   `session["outfit_suggestion"]`.
6. **Create fit card** — `create_fit_card(outfit_suggestion, selected_item)` →
   `session["fit_card"]`.
7. **Return** the session.

The agent behaves differently depending on the data: an impossible query stops
at step 3 with only an error set, while a matching query runs all three tools.
That conditional branch — not a fixed call sequence — is what makes it a
planning loop.

### State management

A single `session` dict is the source of truth for one interaction. The loop
writes each tool's output into a named field and reads it back as the next tool's
input — state flows strictly forward, and nothing is re-prompted or hardcoded
between steps.

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | `_new_session` | parse step |
| `parsed` | parse step | `search_listings` |
| `search_results` | after search | branch check, item selection |
| `selected_item` | selection step | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | `_new_session` | `suggest_outfit` |
| `outfit_suggestion` | after suggest | `create_fit_card` |
| `fit_card` | after create | UI |
| `error` | any early exit | caller checks **first** |

The same `selected_item` object that comes out of `search_results[0]` is the
exact dict passed into both `suggest_outfit` and `create_fit_card`
(`session["selected_item"] is session["search_results"][0]` is `True`), and the
string `suggest_outfit` returns is exactly what `create_fit_card` receives.

### Error handling

Each tool has a defined failure mode and recovers without raising. Concrete
examples from testing (full transcript in [docs/failure_modes.md](docs/failure_modes.md)):

| Tool | Failure mode | Behavior |
|------|--------------|----------|
| search_listings | No results match | Returns `[]`; the loop sets a specific `error` and stops before the LLM tools. |
| suggest_outfit | Empty wardrobe | Returns general styling advice instead of inventing items; not treated as an error. |
| create_fit_card | Empty `outfit` string | Returns a descriptive error string, never crashes. |

**Concrete example — no-results path.** Query
`"designer ballgown size XXS under $5"` parses to
`{description: "designer ballgown", size: "XXS", max_price: 5.0}`.
`search_listings` returns `[]`, and the agent responds:

> No listings found for 'designer ballgown', size XXS, under $5. Try raising your
> max price, dropping the size filter, or using broader keywords.

`session["fit_card"]` stays `None` and `suggest_outfit` is never called —
verified by `tests/test_agent.py::test_no_results_sets_error_and_stops`.

Additionally, the two LLM-backed tools wrap their API call in a try/except and
fall back to a deterministic string, so a single network/API hiccup degrades
gracefully instead of crashing the run.

---

## AI usage

AI assistance on this project was **light** — used to scaffold a couple of
functions from specs I had already written in [planning.md](planning.md), with
review and edits before anything was kept. Two specific instances:

1. **`search_listings` implementation.** I gave the AI tool my Tool 1 spec block
   from planning.md (the parameter list, the return-field description, and the
   "return `[]`, never raise" failure rule) plus the function stub from
   `tools.py`. It produced a filter-then-score function. Before keeping it I
   checked it against my spec: it needed to filter on all three parameters,
   return `[]` (not `None`) when nothing matched, and use `load_listings()`
   rather than re-reading the file. I tightened the size match to be a
   case-insensitive substring (so `"M"` matches `"S/M"`) and confirmed score-0
   listings were dropped, then tested it on three queries.

2. **The planning loop (`run_agent`).** I gave the AI tool my Planning Loop and
   State Management sections plus the architecture diagram from planning.md, and
   the `run_agent`/`_new_session` stubs. It produced the step sequence. The one
   thing I verified carefully was the branch: the empty-results case had to
   `return` *before* `suggest_outfit` ran. I confirmed that against the diagram
   and locked it in with a test (`test_no_results_sets_error_and_stops`). The
   query parser I wrote by hand on top of that.

---

## Spec reflection

The biggest payoff from writing planning.md first was that the failure paths
were already decided before any code existed — the "stop before `suggest_outfit`
when search is empty" rule came straight from the diagram, so the loop had one
clean branch instead of error handling bolted on later.

One place reality diverged from the spec: my planning.md walkthrough predicted
the bootleg graphic tee (`lst_006`, $24) as the top match, but the Y2K Baby Tee
(`lst_002`, $18) actually wins. Both score 3 on the keywords `vintage`/`graphic`/
`tee`, and on a tie `search_listings` keeps dataset order, so `lst_002` ranks
first. The behavior is correct — I updated the walkthrough to match. It's a
reminder that a spec predicts intent, and tests confirm what actually happens.

---

## Project layout

```
.
├── agent.py                 # planning loop + query parser (run_agent)
├── tools.py                 # the three tools
├── app.py                   # Gradio UI (handle_query)
├── planning.md              # spec, diagram, AI tool plan, walkthrough
├── data/
│   ├── listings.json        # mock secondhand listings
│   └── wardrobe_schema.json # wardrobe format + example/empty wardrobes
├── utils/data_loader.py     # load_listings / get_example_wardrobe / get_empty_wardrobe
├── tests/                   # pytest suite (tools + agent)
└── docs/failure_modes.md    # triggered failure-mode evidence
```
