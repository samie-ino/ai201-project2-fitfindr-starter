# FitFindr — Triggered Failure Modes (Milestone 5)

Each of the three failure modes was deliberately triggered from the terminal.
None raised a Python exception; each produced a specific, informative response.

## 1. search_listings returns zero results

**Trigger:**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```
**Output:**
```
[]
```
Returns an empty list — no exception.

**Full agent on the same impossible query:**
```bash
python -c "from agent import run_agent; from utils.data_loader import get_example_wardrobe; \
s = run_agent('designer ballgown size XXS under \$5', get_example_wardrobe()); \
print(s['error']); print(s['fit_card'])"
```
**Output:**
```
No listings found for 'designer ballgown', size XXS, under $5. Try raising your
max price, dropping the size filter, or using broader keywords.
None
```
The agent tells the user *what* failed and *what to try*, and never calls
suggest_outfit — `fit_card` stays `None`.

## 2. suggest_outfit with an empty wardrobe

**Trigger:**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```
**Output (example — varies per run):**
```
This Y2K-inspired baby tee is perfect for creating a playful, nostalgic look that
suits a casual, cottagecore vibe. It pairs well with high-waisted pants, flowy
skirts, or distressed denim for a relaxed, laid-back feel. To add some visual
interest, try tucking the tee into a flowy skirt or pants to create a defined
waistline and balance out the loose fit of the top.
```
Returns general styling advice — a useful non-empty string, no exception.

## 3. create_fit_card with an empty outfit string

**Trigger:**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```
**Output:**
```
Can't write a fit card without an outfit suggestion — try styling the item first.
```
Returns a descriptive error message string — not a Python exception.
