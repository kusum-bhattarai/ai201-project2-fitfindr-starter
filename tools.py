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

MODEL = "llama-3.3-70b-versatile"


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

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Keywords from the description, ignoring noise/stop words and short tokens.
    stop_words = {
        "a", "an", "the", "for", "in", "of", "to", "and", "or", "with",
        "looking", "want", "need", "find", "some", "any", "im", "i",
        "under", "size", "my",
    }
    keywords = [
        w for w in re.findall(r"[a-z0-9]+", description.lower())
        if w not in stop_words and len(w) > 1
    ]

    scored = []
    for listing in listings:
        # Price filter (inclusive).
        if max_price is not None and listing["price"] > max_price:
            continue
        # Size filter — case-insensitive substring match (so "M" matches "S/M").
        if size is not None and size.strip().lower() not in listing["size"].lower():
            continue

        # Build a searchable text blob from the listing's text fields.
        haystack = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
            listing["category"],
            listing["brand"] or "",
        ]).lower()

        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            scored.append((score, listing))

    # Highest score first; stable order preserves dataset order within a tier.
    scored.sort(key=lambda pair: pair[0], reverse=True)
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
        f"style: {', '.join(new_item['style_tags'])}, "
        f"colors: {', '.join(new_item['colors'])}, "
        f"size: {new_item['size']})"
    )

    items = wardrobe.get("items", [])

    if not items:
        # Empty-wardrobe branch: general styling advice, no named pieces.
        prompt = (
            f"A shopper is considering this secondhand piece:\n{item_desc}\n\n"
            "They haven't told you what's in their closet yet. Suggest one or two "
            "ways to style this item in general terms — what kinds of pieces pair "
            "well with it, what vibe/aesthetic it suits, and one concrete styling "
            "tip. Keep it to 2-4 sentences, friendly and specific. Do not invent "
            "items they own."
        )
    else:
        # Format the wardrobe so the LLM can name specific pieces.
        wardrobe_lines = "\n".join(
            f"- {it['name']} ({it['category']}; {', '.join(it['style_tags'])})"
            for it in items
        )
        prompt = (
            f"A shopper is considering this secondhand piece:\n{item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest one or two complete outfits that combine the new piece with "
            "SPECIFIC items from their wardrobe, naming the wardrobe pieces you use. "
            "Add one concrete styling tip (how to cuff, tuck, layer, etc.). "
            "Keep it to 2-4 sentences, friendly and specific."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a sharp, encouraging personal stylist.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        # Graceful fallback — never propagate the exception to the agent.
        return (
            f"Couldn't reach the styling assistant ({exc}). As a starting point, "
            f"{new_item['title']} works well with simple, neutral basics that let "
            "the piece stand out."
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
    # Guard: no outfit means nothing to caption.
    if not outfit or not outfit.strip():
        return "Can't write a fit card without an outfit suggestion."

    prompt = (
        "Write a short, shareable social media caption (an OOTD / fit-card post) "
        "for this thrifted find.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']:.0f}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit it's styled in: {outfit}\n\n"
        "Rules:\n"
        "- 2 to 4 sentences, casual and authentic like a real OOTD post, NOT a "
        "product description.\n"
        "- Mention the item name, price, and platform naturally, once each.\n"
        "- Capture the outfit's vibe in specific terms.\n"
        "- Lowercase/relaxed tone and an emoji or two are welcome.\n"
        "Return only the caption."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You write fun, authentic thrift-haul captions.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,  # higher temp so repeated calls vary
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        # Graceful fallback — a simple templated caption instead of crashing.
        return (
            f"thrifted this {new_item['title'].lower()} off {new_item['platform']} "
            f"for ${new_item['price']:.0f} ✨ (caption generator offline: {exc})"
        )
