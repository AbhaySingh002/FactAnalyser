"""Deterministic normalization — numbers, units, currencies, periods, and entities."""

from __future__ import annotations

import re
from rapidfuzz import fuzz

from .. import db

# ── Named Thresholds & Constants ─────────────────────────────────────
ENTITY_SIMILARITY_THRESHOLD = 92.0
ATTRIBUTE_SIMILARITY_THRESHOLD = 0.90

CURRENCY_MAP = {
    "$": "USD",
    "usd": "USD",
    "us$": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "₹": "INR",
    "inr": "INR",
    "rs": "INR",
    "rs.": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "¥": "JPY",
    "jpy": "JPY",
    "cny": "CNY",
    "yuan": "CNY",
}

NUMBER_MULTIPLIERS = {
    "trillion": 1e12,
    "billion": 1e9,
    "bn": 1e9,
    "million": 1e6,
    "mn": 1e6,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "thousand": 1e3,
    "k": 1e3,
}

ENTITY_STRIP_SUFFIXES = [
    r"\bprivate\s+limited\b",
    r"\bpvt\.?\s*ltd\.?\b",
    r"\blimited\b",
    r"\bltd\.?\b",
    r"\bpvt\.?\b",
    r"\bincorporated\b",
    r"\binc\.?\b",
    r"\bcorporation\b",
    r"\bcorp\.?\b",
    r"\bcompany\b",
    r"\bco\.?\b",
    r"\bllc\.?\b",
    r"\bplc\.?\b",
]


# ── Numbers, Units & Currency ────────────────────────────────────────

def normalize_number_and_unit(raw: str | None, val_num: float | None = None) -> tuple[float | None, str | None, str | None]:
    """Returns (norm_value, norm_unit, currency).

    norm_unit is in {'pct', 'currency', 'count', 'date', 'text'}.
    """
    if not raw and val_num is None:
        return None, None, None

    raw_str = (raw or "").strip()
    raw_lower = raw_str.lower()

    # 1. Detect Currency
    currency = None
    for sym, canon in CURRENCY_MAP.items():
        if re.search(r"(?:^|[\s\d])" + re.escape(sym) + r"(?:[\s\d]|$)", raw_lower):
            currency = canon
            break

    # 2. Detect Percent
    is_pct = "%" in raw_str or bool(re.search(r"\b(?:percent|percentage|pct)\b", raw_lower))

    # 3. Parse Numeric Value
    multiplier = 1.0
    for word, mult in NUMBER_MULTIPLIERS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", raw_lower):
            multiplier = mult
            break

    norm_value = None
    if val_num is not None:
        # If val_num provided, apply multiplier if not already factored
        norm_value = float(val_num) * multiplier
    else:
        # Extract number from raw string
        match = re.search(r"[-+]?\b\d[\d,]*(?:\.\d+)?\b", raw_str)
        if match:
            clean_num = match.group(0).replace(",", "")
            try:
                norm_value = float(clean_num) * multiplier
            except ValueError:
                pass

    # 4. Determine norm_unit
    if is_pct:
        norm_unit = "pct"
    elif currency:
        norm_unit = "currency"
    elif norm_value is not None:
        norm_unit = "count"
    elif re.search(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", raw_str):
        norm_unit = "date"
    else:
        norm_unit = "text"

    return norm_value, norm_unit, currency


# ── Period Canonicalization ──────────────────────────────────────────

def normalize_period(period: str | None, raw: str = "") -> str | None:
    text = f"{period or ''} {raw}".strip()
    if not text:
        return None

    # Quarters: Q3 2023, Q3 FY23, 3Q2023, 3Q23, 2023 Q3
    q_match = (
        re.search(r"\bQ([1-4])\s*(?:FY)?\s*(\d{2,4})\b", text, re.IGNORECASE)
        or re.search(r"\b([1-4])Q\s*(?:FY)?\s*(\d{2,4})\b", text, re.IGNORECASE)
        or re.search(r"\b(\d{4})\s*[\-_/]?\s*Q([1-4])\b", text, re.IGNORECASE)
    )
    if q_match:
        g = q_match.groups()
        if len(g[0]) == 4:
            year, q = g[0], g[1]
        else:
            q, yr = g[0], g[1]
            year = f"20{yr}" if len(yr) == 2 else yr
        return f"{year}-Q{q}"

    # Year ended Mar 2023 / Year ended 31 March 2023
    ye_match = re.search(
        r"year\s+ended\s+(?:\d{1,2}\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if ye_match:
        return f"FY{ye_match.group(1)}"

    # Fiscal Year: FY23, FY 23, FY2023, FY 2023
    fy_match = re.search(r"\bFY\s*(\d{2,4})\b", text, re.IGNORECASE)
    if fy_match:
        yr = fy_match.group(1)
        year = f"20{yr}" if len(yr) == 2 else yr
        return f"FY{year}"

    # Plain 4-digit year: 2023
    y_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if y_match:
        return y_match.group(1)

    return period


# ── Entity Canonicalization ──────────────────────────────────────────

def clean_entity_name(name: str) -> str:
    cleaned = name.lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    for pat in ENTITY_STRIP_SUFFIXES:
        cleaned = re.sub(pat, " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def canonicalize_entity(entity: str | None) -> str | None:
    if not entity:
        return None
    cleaned = clean_entity_name(entity)
    if not cleaned:
        return entity.lower().strip()

    # 1. Alias lookup
    known = db.get_entity_alias(cleaned)
    if known:
        return known

    # 2. Fuzzy match vs existing canonical entities
    existing_canonicals = db.get_all_canonical_entities()
    best_match = None
    best_score = 0.0

    for cand in existing_canonicals:
        score = fuzz.token_sort_ratio(cleaned, cand)
        if score > best_score:
            best_score = score
            best_match = cand

    if best_score > ENTITY_SIMILARITY_THRESHOLD and best_match:
        db.set_entity_alias(cleaned, best_match)
        return best_match

    # 3. New canonical entity
    db.set_entity_alias(cleaned, cleaned)
    return cleaned


# ── Attribute Canonicalization ────────────────────────────────────────

def canonicalize_attribute(attribute: str | None, embed_fn) -> str | None:
    if not attribute:
        return None
    cleaned = re.sub(r"[^\w\s]", " ", attribute.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = attribute.lower().strip()

    # Embed and query pgvector cosine distance
    emb = embed_fn(cleaned)
    closest = db.find_closest_attribute(emb, threshold=ATTRIBUTE_SIMILARITY_THRESHOLD)
    if closest:
        return closest

    db.add_canonical_attribute(cleaned, emb)
    return cleaned


if __name__ == "__main__":
    # Runnable assert-based self-check
    assert normalize_number_and_unit("50 million")[0] == 5e7
    assert normalize_number_and_unit("20 crore")[0] == 2e8
    assert normalize_number_and_unit("1,234.5")[0] == 1234.5
    assert normalize_number_and_unit("$50 million")[2] == "USD"
    assert normalize_number_and_unit("₹ 20 crore")[2] == "INR"
    assert normalize_period("FY23") == "FY2023"
    assert normalize_period("year ended Mar 2023") == "FY2023"
    assert normalize_period("Q3 2023") == "2023-Q3"
    assert clean_entity_name("Apple Inc.") == "apple"
    assert clean_entity_name("Reliance Industries Limited") == "reliance industries"
    assert clean_entity_name("Tata Motors Pvt Ltd") == "tata motors"
    print("✓ normalize self-check passed")
