"""Deterministic normalization — numbers, units, currencies, periods, and entities.

CRITICAL DESIGN RULES:
1. Deterministic arithmetic: Zero LLM hallucinations for number scaling, currency mapping, or sign detection.
2. Financial negative number conventions: Parenthesized numbers `(1,234.50)` represent negative amounts `-1234.50`.
3. Acronym & Regulatory Authority Preservation: Never obliterate recognized entities like RBI, SEBI, SEC, IMF, MCA, ED.
4. Period alignment: Standardized formats (`FY2024`, `2024-Q3`, `H1-FY2024`, `9M-FY2024`) for accurate cross-document tie-outs.
"""

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
    "renminbi": "CNY",
    "chf": "CHF",
    "cad": "CAD",
    "aud": "AUD",
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
    "cr.": 1e7,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "thousand": 1e3,
    "k": 1e3,
}

KNOWN_ACRONYMS = {
    "rbi": "Reserve Bank of India",
    "sebi": "Securities and Exchange Board of India",
    "ed": "Enforcement Directorate",
    "mca": "Ministry of Corporate Affairs",
    "sec": "Securities and Exchange Commission",
    "imf": "International Monetary Fund",
    "cci": "Competition Commission of India",
    "irs": "Internal Revenue Service",
    "it": "Income Tax Department",
    "nclt": "National Company Law Tribunal",
    "nclat": "National Company Law Appellate Tribunal",
    "delhivery": "Delhivery Limited",
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
    r"\bholdings?\b",
    r"\bs\.?a\.?\b",
    r"\ba\.?g\.?\b",
    r"\bgmbh\b",
]


# ── Numbers, Units & Currency ────────────────────────────────────────

def normalize_number_and_unit(
    raw: str | None,
    val_num: float | None = None,
) -> tuple[float | None, str | None, str | None]:
    """Deterministically parse numbers, financial units, and currencies.

    Returns:
        (norm_value, norm_unit, currency)
        norm_unit is in {'pct', 'currency', 'count', 'bps', 'date', 'text'}.
    """
    if not raw and val_num is None:
        return None, None, None

    raw_str = (raw or "").strip()
    raw_lower = raw_str.lower()

    # 1. Detect Accounting Negative: (1,234.50) or (₹ 20 crore) or -1,234.50
    is_negative = False
    if re.search(r"\([^)]*[\d,]+[^)]*\)", raw_str):
        is_negative = True
    elif raw_str.strip().startswith("-") or "loss of" in raw_lower or "negative" in raw_lower:
        is_negative = True

    # 2. Detect Currency
    currency = None
    for sym, canon in CURRENCY_MAP.items():
        if re.search(r"(?:^|[\s\d\(])" + re.escape(sym) + r"(?:[\s\d\)]|$)", raw_lower):
            currency = canon
            break

    # 3. Detect Unit / Percent / Basis Points
    is_pct = "%" in raw_str or bool(re.search(r"\b(?:percent|percentage|pct)\b", raw_lower))
    is_bps = bool(re.search(r"\b(?:bps|basis\s+points)\b", raw_lower))

    # 4. Multiplier
    multiplier = 1.0
    for word, mult in NUMBER_MULTIPLIERS.items():
        if re.search(r"\b" + re.escape(word) + r"\b", raw_lower):
            multiplier = mult
            break

    norm_value = None
    if val_num is not None:
        # If val_num provided, apply multiplier if not already factored
        norm_value = float(val_num)
        if abs(norm_value) < 1000 and multiplier > 1.0:
            norm_value = norm_value * multiplier
        if is_negative and norm_value > 0:
            norm_value = -norm_value
    else:
        # Extract numeric magnitude from raw string
        match = re.search(r"[-+]?\b\d[\d,]*(?:\.\d+)?\b", raw_str)
        if match:
            clean_num = match.group(0).replace(",", "")
            try:
                base_f = float(clean_num)
                norm_value = base_f * multiplier
                if is_negative and norm_value > 0:
                    norm_value = -norm_value
            except ValueError:
                pass

    # 5. Determine norm_unit
    if is_bps:
        norm_unit = "bps"
    elif is_pct:
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
    """Canonicalize financial reporting periods to standard tokens."""
    text = f"{period or ''} {raw}".strip()
    if not text:
        return None

    # Quarters: Q3 2023, Q3 FY23, 3Q2023, 3Q23, 2023 Q3, Q3FY24
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

    # Half Years: H1 FY24, H2 2023, 1H2024
    h_match = re.search(r"\b(?:H([1-2])|([1-2])H)\s*(?:FY)?\s*(\d{2,4})\b", text, re.IGNORECASE)
    if h_match:
        h = h_match.group(1) or h_match.group(2)
        yr = h_match.group(3)
        year = f"20{yr}" if len(yr) == 2 else yr
        return f"H{h}-FY{year}"

    # Nine months ended: 9M FY24
    nine_m = re.search(r"\b(?:9M|nine\s+months)\s*(?:ended)?\s*(?:FY)?\s*(\d{2,4})\b", text, re.IGNORECASE)
    if nine_m:
        yr = nine_m.group(1)
        year = f"20{yr}" if len(yr) == 2 else yr
        return f"9M-FY{year}"

    # Year ended Mar 2023 / Year ended 31 March 2023 / Year ended March 31, 2023
    months_pat = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    ye_match = re.search(
        rf"year\s+ended\s+(?:(?:\d{{1,2}}\s+)?{months_pat}|{months_pat}(?:\s+\d{{1,2}})?)\s*\,?\s*(\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if ye_match:
        return f"FY{ye_match.group(1)}"

    # Multi-year spans: FY2023-24, 2023-24 -> FY2024 (Indian fiscal year ending 2024)
    fy_span = re.search(r"\b(?:FY)?\s*(\d{4})\s*[-–]\s*(\d{2,4})\b", text, re.IGNORECASE)
    if fy_span:
        end_yr = fy_span.group(2)
        if len(end_yr) == 2:
            start_century = fy_span.group(1)[:2]
            return f"FY{start_century}{end_yr}"
        return f"FY{end_yr}"

    # Fiscal Year: FY23, FY 23, FY2023, FY 2023, Fiscal 2023
    fy_match = re.search(r"\b(?:FY|Fiscal|Financial\s+Year)\s*(\d{2,4})\b", text, re.IGNORECASE)
    if fy_match:
        yr = fy_match.group(1)
        year = f"20{yr}" if len(yr) == 2 else yr
        return f"FY{year}"

    # Trailing Twelve Months (TTM)
    if re.search(r"\b(?:ttm|trailing\s+twelve\s+months)\b", text, re.IGNORECASE):
        y_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
        return f"TTM-{y_match.group(1)}" if y_match else "TTM"

    # Plain 4-digit year: 2023
    y_match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if y_match:
        return y_match.group(1)

    return period.strip() if period else None


# ── Entity Canonicalization ──────────────────────────────────────────

def clean_entity_name(name: str) -> str:
    """Normalize company/entity names while respecting known acronyms and suffixes."""
    cleaned = name.lower().strip()

    # Check known financial/legal acronyms first
    if cleaned in KNOWN_ACRONYMS:
        return KNOWN_ACRONYMS[cleaned]

    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    for pat in ENTITY_STRIP_SUFFIXES:
        sub = re.sub(pat, " ", cleaned, flags=re.IGNORECASE).strip()
        # Avoid stripping everything if company name is just "Limited"
        if len(sub) >= 2:
            cleaned = sub

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title() if cleaned else name.strip()


def canonicalize_entity(entity: str | None) -> str | None:
    """Resolve entity to canonical form via alias cache or fuzzy matching."""
    if not entity:
        return None
    cleaned = clean_entity_name(entity)
    if not cleaned:
        return entity.strip()

    # 1. Alias lookup in DB
    try:
        known = db.get_entity_alias(cleaned.lower())
        if known:
            return known

        # 2. Fuzzy match vs existing canonical entities
        existing_canonicals = db.get_all_canonical_entities()
        best_match = None
        best_score = 0.0

        for cand in existing_canonicals:
            score = fuzz.token_sort_ratio(cleaned.lower(), cand.lower())
            if score > best_score:
                best_score = score
                best_match = cand

        if best_score > ENTITY_SIMILARITY_THRESHOLD and best_match:
            db.set_entity_alias(cleaned.lower(), best_match)
            return best_match

        # 3. New canonical entity
        db.set_entity_alias(cleaned.lower(), cleaned)
        return cleaned
    except Exception:
        # Fallback if DB is offline during offline testing
        return cleaned


# ── Attribute Canonicalization ────────────────────────────────────────

def canonicalize_attribute(attribute: str | None, embed_fn=None) -> str | None:
    """Canonicalize financial metric or disclosure attribute."""
    if not attribute:
        return None
    cleaned = re.sub(r"[^\w\s]", " ", attribute.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = attribute.lower().strip()

    # Normalize common financial metric variations
    metric_replacements = {
        r"\brevenue from operations\b": "operating revenue",
        r"\btotal income\b": "total revenue",
        r"\bprofit after tax\b": "net income",
        r"\bpat\b": "net income",
        r"\bprofit before tax\b": "pbt",
        r"\bearnings before interest\b": "operating profit",
        r"\badjusted ebitda\b": "adjusted ebitda",
        r"\bebitda\b": "ebitda",
    }
    for pat, rep in metric_replacements.items():
        if re.search(pat, cleaned):
            cleaned = rep
            break

    if embed_fn:
        try:
            emb = embed_fn(cleaned)
            closest = db.find_closest_attribute(emb, threshold=ATTRIBUTE_SIMILARITY_THRESHOLD)
            if closest:
                return closest
            db.add_canonical_attribute(cleaned, emb)
        except Exception:
            pass

    return cleaned


if __name__ == "__main__":
    # Test financial negative parentheses
    val, unit, curr = normalize_number_and_unit("(1,234.50)")
    assert val == -1234.50, f"Expected -1234.50, got {val}"

    val_cr, unit_cr, curr_cr = normalize_number_and_unit("(₹ 20 crore)")
    assert val_cr == -200000000.0, f"Expected -2e8, got {val_cr}"
    assert curr_cr == "INR"

    # Test numbers and multipliers
    assert normalize_number_and_unit("50 million")[0] == 5e7
    assert normalize_number_and_unit("20 crore")[0] == 2e8
    assert normalize_number_and_unit("1,234.5")[0] == 1234.5
    assert normalize_number_and_unit("$50 million")[2] == "USD"
    assert normalize_number_and_unit("₹ 20 crore")[2] == "INR"

    # Test period normalization
    assert normalize_period("FY23") == "FY2023"
    assert normalize_period("year ended Mar 2023") == "FY2023"
    assert normalize_period("Q3 2023") == "2023-Q3"
    assert normalize_period("2023-24") == "FY2024"
    assert normalize_period("H1 FY24") == "H1-FY2024"
    assert normalize_period("9M ended FY24") == "9M-FY2024"

    # Test clean entity
    assert clean_entity_name("Apple Inc.") == "Apple"
    assert clean_entity_name("Reliance Industries Limited") == "Reliance Industries"
    assert clean_entity_name("Tata Motors Pvt Ltd") == "Tata Motors"
    assert clean_entity_name("rbi") == "Reserve Bank of India"
    assert clean_entity_name("SEBI") == "Securities and Exchange Board of India"
    print("✓ All normalize self-checks passed successfully!")
