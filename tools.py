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
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Model used by the LLM-backed tools (suggest_outfit, create_fit_card).
_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _tokenize(text: str) -> set[str]:
    """Lowercase a string and split it into a set of word tokens."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


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

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()
    query_tokens = _tokenize(description)

    scored: list[tuple[int, dict]] = []
    for item in listings:
        # 1. Price filter (inclusive).
        if max_price is not None and item["price"] > max_price:
            continue

        # 2. Size filter — case-insensitive substring match so "M" matches
        #    "S/M" and "XL" matches "XL (oversized)".
        if size is not None and size.strip().lower() not in item["size"].lower():
            continue

        # 3. Score by keyword overlap across the item's searchable text.
        haystack = " ".join(
            [
                item["title"],
                item["description"],
                item["category"],
                " ".join(item["style_tags"]),
            ]
        )
        item_tokens = _tokenize(haystack)
        score = len(query_tokens & item_tokens)

        # 4. Drop listings with no relevant overlap.
        if score > 0:
            scored.append((score, item))

    # 5. Sort by score, highest first (stable — preserves dataset order on ties).
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


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

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item['title']} "
        f"(category: {new_item['category']}, "
        f"colors: {', '.join(new_item['colors'])}, "
        f"style: {', '.join(new_item['style_tags'])}, "
        f"condition: {new_item['condition']})"
    )

    items = wardrobe.get("items", [])
    if not items:
        # Empty wardrobe → general styling advice, not an error.
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            "They haven't entered their wardrobe yet. In 2-3 sentences, give "
            "general styling advice: what kinds of pieces pair well with it, "
            "what vibe it suits, and one concrete tip (a tuck, roll, or layer). "
            "Do not invent specific items they own."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {it['name']} ({it['category']}, "
            f"{', '.join(it['colors'])}; {', '.join(it['style_tags'])})"
            for it in items
        )
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific "
            "pieces named from their wardrobe above. Keep it to 2-4 sentences, "
            "name the pieces you're using, and include one concrete styling tip "
            "(a tuck, roll, or layer). Use only pieces from the list."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        suggestion = response.choices[0].message.content.strip()
        if suggestion:
            return suggestion
    except Exception:
        pass  # fall through to a deterministic fallback below

    # Fallback if the LLM is unavailable or returns nothing — keeps the
    # pipeline alive so create_fit_card still has something to work with.
    return (
        f"Style your {new_item['title'].lower()} around its "
        f"{', '.join(new_item['style_tags'][:2])} vibe — pair it with simple "
        "bottoms and let the piece stand out. Roll or tuck the hem for shape."
    )


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

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty / whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "Can't write a fit card without an outfit suggestion — "
            "try styling the item first."
        )

    prompt = (
        "Write a short, casual social media caption for a thrifted outfit "
        "(Instagram/TikTok OOTD voice — not a product description).\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']:.0f}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit: {outfit}\n\n"
        "Requirements:\n"
        "- 2-4 sentences, lowercase-casual and authentic\n"
        "- mention the item name, price, and platform naturally (once each)\n"
        "- capture the specific vibe of the outfit\n"
        "- emoji are fine but optional\n"
        "Return only the caption."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,  # high temp so repeated calls vary
        )
        caption = response.choices[0].message.content.strip()
        if caption:
            return caption
    except Exception:
        pass  # fall through to deterministic fallback below

    # Fallback caption if the LLM is unavailable — still postable.
    return (
        f"thrifted this {new_item['title'].lower()} off {new_item['platform']} "
        f"for ${new_item['price']:.0f} and i'm obsessed 🤍 full fit in stories"
    )
