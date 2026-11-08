"""World benchmark data: what outreach normally returns, by industry.

Static, cited, versioned world data — the first layer of the "start from the
world's records" thesis. Every figure carries its sources and vintage, and
industry coverage is honest: where no industry-specific study is on file the
lookup falls back to the general-B2B band and says so in `coverage`, instead
of inventing precision.

Sources (all free, published benchmark studies):
- Woodpecker 2026 cold-email study (20M+ emails): reply rate fell 5.1%
  (2024) to 3.43% (2026); driven by inbox saturation and Gmail/Outlook
  tightening.
- Instantly 2026 B2B benchmarks: good = 5-10%, top performers 15%+ on
  focused campaigns.
- SalesHive 2025-2026: average 3-5%, top quartile 5.5%+, elite above 10%.
- Belkins 2026 study: strict cold (net-new, no warm-up) averaged 0.45%.
- MailerLite 2025 (opt-in): average open 43.46% (2024: 42.35%).
- Hubspot/GetResponse-cited B2B opt-in: open ~39.5%, click ~3%.

Vintage: 2025-2026. Figures are ranges, never single "averages", because
published studies disagree on methodology (strict-cold vs opted-in).
"""
from __future__ import annotations

MODULE_VERSION = 1
VINTAGE = "2025-2026"

COLD_OUTBOUND_GENERAL: dict[str, object] = {
    # Typical B2B cold-outbound reply band. Low end covers strict-cold
    # reality (Belkins 0.45%); high end covers solid campaigns (5%+).
    "reply_low_pct": 1.0,
    "reply_high_pct": 5.0,
    "elite_pct": 10.0,
    "coverage": "general B2B (no industry-specific cold study on file)",
    "sources": [
        "Woodpecker 2026 cold-email study (20M+ emails)",
        "Instantly 2026 B2B cold-email benchmarks",
        "SalesHive B2B benchmarks 2025-2026",
        "Belkins 2026 strict-cold study (floor reference)",
    ],
    "vintage": VINTAGE,
}

# Opt-in email benchmarks by industry. Only industries with a published
# industry figure get their own row; everything else maps to "general".
OPTIN_BY_INDUSTRY: dict[str, dict[str, object]] = {
    "general": {
        "open_low_pct": 39.5,
        "open_high_pct": 43.5,
        "click_low_pct": 2.0,
        "click_high_pct": 3.0,
        "coverage": "general B2B opt-in",
        "sources": [
            "MailerLite 2025 benchmarks (43.46% avg open)",
            "HubSpot-cited B2B open 39.5%",
            "GetResponse-cited B2B ~3% click-through",
        ],
        "vintage": VINTAGE,
    },
    "software": {
        "open_low_pct": 35.0,
        "open_high_pct": 45.0,
        "click_low_pct": 2.0,
        "click_high_pct": 3.0,
        "coverage": "B2B SaaS opt-in study",
        "sources": ["SalesHive SaaS email benchmarks 2025 (35-45% open)"],
        "vintage": VINTAGE,
    },
}

INDUSTRY_ALIASES: dict[str, str] = {
    "saas": "software",
    "software": "software",
    "tech": "software",
    "technology": "software",
    "it services": "software",
    "logistics": "general",
    "freight": "general",
    "freight forwarding": "general",
    "3pl": "general",
    "supply chain": "general",
    "transportation": "general",
    "consulting": "general",
    "agency": "general",
    "professional services": "general",
    "finance": "general",
    "fintech": "general",
    "healthcare": "general",
    "manufacturing": "general",
    "retail": "general",
    "ecommerce": "general",
    "real estate": "general",
    "education": "general",
}


def normalize_industry(text: object) -> str:
    """Map free-text industry to a benchmark key. Unknown -> 'general'."""
    if not text or not isinstance(text, str):
        return "general"
    cleaned = text.strip().lower()
    if cleaned in OPTIN_BY_INDUSTRY:
        return cleaned
    if cleaned in INDUSTRY_ALIASES:
        return INDUSTRY_ALIASES[cleaned]
    for alias, key in INDUSTRY_ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return key
    return "general"


def cold_reply_benchmark(industry: object = None) -> dict[str, object]:
    """Cold-outbound reply band for an industry.

    Only general-B2B cold studies are on file, so every industry resolves to
    the general band and `industry_matched` records whether the name was even
    recognised. The honesty is the feature: callers can show founders exactly
    how much the world knows about their niche (today: the general band).
    """
    key = normalize_industry(industry)
    out = dict(COLD_OUTBOUND_GENERAL)
    out["industry"] = industry if isinstance(industry, str) and industry.strip() else None
    out["industry_matched"] = key != "general" or (
        isinstance(industry, str) and industry.strip().lower() == "general"
    )
    return out


def optin_benchmark(industry: object = None) -> dict[str, object]:
    """Opt-in open/click band for an industry, with honest coverage flag."""
    key = normalize_industry(industry)
    row = OPTIN_BY_INDUSTRY.get(key, OPTIN_BY_INDUSTRY["general"])
    out = dict(row)
    out["industry"] = industry if isinstance(industry, str) and industry.strip() else None
    out["industry_matched"] = key in OPTIN_BY_INDUSTRY and key != "general"
    if key == "general":
        out["coverage"] = (
            f"{row['coverage']} applied to "
            f"{out['industry'] or 'this industry'} (no industry-specific study on file)"
        )
    return out


def expected_replies(sends: int, industry: object = None) -> dict[str, object]:
    """Estimate reply counts for a send volume from the world band.

    Pure arithmetic over the cited band: low = sends * low_pct, high = sends
    * high_pct, rounded down/up to whole replies. Zero/negative sends yield
    a zero range rather than an error, so callers can render it blindly.
    """
    bench = cold_reply_benchmark(industry)
    try:
        volume = max(0, int(sends))
    except (TypeError, ValueError):
        volume = 0
    low_pct = float(bench["reply_low_pct"])  # type: ignore[arg-type]
    high_pct = float(bench["reply_high_pct"])  # type: ignore[arg-type]
    low = int(volume * low_pct / 100)
    high = int(volume * high_pct / 100 + 0.999) if volume else 0
    return {
        "low": low,
        "high": high,
        "unit": "replies",
        "sends": volume,
        "basis": (
            f"world band {low_pct:g}-{high_pct:g}% cold reply "
            f"({bench['coverage']}; {VINTAGE})"
        ),
        "sources": bench["sources"],
    }
