# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1.

"""
dashboard/ai_chat.py — GreenLens AI Chat Assistant powered by Google Gemini.

Architecture:
  1. Parse user question to extract intent (country, risk type, category, etc.)
  2. Query the real PostgreSQL database for relevant bonds
  3. Build a rich context prompt with live data
  4. Call Gemini 1.5 Flash and stream the response
"""

import json
import logging
import os
import re

import google.generativeai as genai
from django.db.models import Avg, Count, Q

logger = logging.getLogger(__name__)

# ── Gemini setup ──────────────────────────────────────────────────────────────

def _get_gemini_model():
    """Initialise and return a Gemini GenerativeModel."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=genai.GenerationConfig(
            temperature=0.4,
            top_p=0.95,
            max_output_tokens=1024,
        ),
        system_instruction=_SYSTEM_PROMPT,
    )


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """
You are GreenLens AI, an expert climate risk intelligence assistant embedded 
inside GreenLens, a climate-risk research prototype.

Your role:
- Answer questions about green bonds, climate risk (PCRS scores), greenwashing, 
  pricing gaps, and ESG investing.
- Use only the STORED DATABASE CONTEXT provided in each message. Registry rows may
    be aggregate-derived, scores may use demo inputs, and spreads may be estimated.
- Never present a score as validated loss prediction or an unverified record as satellite-verified.
- Be concise but insightful. Use bullet points. Highlight key numbers.
- Always mention: PCRS score, main risk driver, and any greenwash/mispricing flag.
- If asked about a specific bond, give full details.
- If asked generally (e.g. "show high-risk bonds in Asia"), summarise the top 3-5.
- Use climate finance terminology correctly (PCRS, NDVI, SHAP, bps, etc.)
- End responses with a relevant follow-up question to help the user explore more.
- Never hallucinate bond data — only use what is provided in the database context.
- Format numbers cleanly: PCRS scores to 1 decimal, bps to nearest whole number.
- Keep responses under 300 words unless the user asks for detail.

Your tone: professional, data-driven, slightly conversational — like a Bloomberg 
terminal that can talk.
""".strip()


# ── Intent parsing ────────────────────────────────────────────────────────────

_REGION_MAP = {
    "southeast asia": ["Vietnam", "Thailand", "Indonesia", "Philippines", "Malaysia",
                       "Singapore", "Myanmar", "Cambodia", "Laos"],
    "south asia":     ["India", "Bangladesh", "Pakistan", "Sri Lanka", "Nepal"],
    "east asia":      ["China", "Japan", "South Korea", "Taiwan"],
    "europe":         ["Germany", "France", "United Kingdom", "Netherlands", "Sweden",
                       "Italy", "Spain", "Poland", "Denmark", "Norway", "Finland",
                       "Belgium", "Austria", "Switzerland"],
    "latin america":  ["Brazil", "Mexico", "Chile", "Colombia", "Argentina", "Peru"],
    "africa":         ["South Africa", "Kenya", "Nigeria", "Morocco", "Egypt"],
    "middle east":    ["Saudi Arabia", "UAE", "Qatar", "Jordan", "Egypt"],
    "north america":  ["United States", "Canada"],
}

_HAZARD_KEYWORDS = {
    "flood":    "flood_risk_index",
    "flooding": "flood_risk_index",
    "heat":     "heat_stress_index",
    "drought":  "drought_spei",
    "cyclone":  "cyclone_risk_index",
    "monsoon":  "monsoon_risk_index",
}

_CATEGORY_KEYWORDS = {
    "solar":          "solar",
    "wind":           "wind",
    "water":          "water",
    "reforestation":  "reforestation",
    "forest":         "reforestation",
    "transport":      "transport",
    "building":       "building",
    "green building": "building",
}


def _parse_intent(question: str) -> dict:
    """Extract structured intent from a natural language question."""
    q = question.lower()
    intent = {
        "countries":    [],
        "hazard_field": None,
        "category":     None,
        "want_high_risk":    "high risk" in q or "risky" in q or "dangerous" in q,
        "want_mispriced":    "mispric" in q or "undervalue" in q or "overvalue" in q,
        "want_greenwash":    "greenwash" in q or "flag" in q or "satellite" in q,
        "want_low_risk":     "safe" in q or "low risk" in q or "safest" in q,
        "specific_bond":     None,
        "limit":        5,
    }

    # Region → country list
    for region, countries in _REGION_MAP.items():
        if region in q:
            intent["countries"].extend(countries)

    # Direct country mention (capitalised word not already captured)
    # Look for known countries by checking title-case words
    words = question.split()
    for i, w in enumerate(words):
        clean = w.strip(".,?!")
        # Two-word countries
        if i + 1 < len(words):
            two = clean + " " + words[i + 1].strip(".,?!")
            for countries in _REGION_MAP.values():
                for c in countries:
                    if two.lower() == c.lower() and c not in intent["countries"]:
                        intent["countries"].append(c)
        for countries in _REGION_MAP.values():
            for c in countries:
                if clean.lower() == c.lower() and c not in intent["countries"]:
                    intent["countries"].append(c)

    # Hazard type
    for kw, field in _HAZARD_KEYWORDS.items():
        if kw in q:
            intent["hazard_field"] = field
            break

    # Project category
    for kw, cat in _CATEGORY_KEYWORDS.items():
        if kw in q:
            intent["category"] = cat
            break

    # Specific bond ID pattern (e.g. VNM_Water_2021)
    bond_match = re.search(r'\b([A-Z]{2,4}_[A-Za-z]+_\d{4})\b', question)
    if bond_match:
        intent["specific_bond"] = bond_match.group(1)

    return intent


# ── Database context builder ──────────────────────────────────────────────────

def _build_db_context(intent: dict) -> str:
    """Query the real database and return a formatted context string."""
    from dashboard.workbench import annotated_bonds, observed_satellite

    query = annotated_bonds()
    stats = query.aggregate(total=Count("pk"), scored=Count("current_score"), average=Avg("current_score"))
    lines = [
        "Stored research snapshot (not live market data or validated loss predictions).",
        f"Registry records: {stats['total']} | Scored: {stats['scored']} | Average PCRS: {stats['average'] or 0:.1f}",
        "PCRS is a physical climate risk research score, not a probability of default. Demo and estimated inputs may apply.",
    ]
    if intent.get("specific_bond"):
        query = query.filter(bond_id__iexact=intent["specific_bond"])
    if intent.get("countries"):
        query = query.filter(country__in=intent["countries"])
    if intent.get("category"):
        query = query.filter(project_category=intent["category"])
    if intent.get("want_mispriced"):
        query = query.filter(price_flag=True)
    query = query.order_by("-current_score" if intent.get("want_high_risk") else "current_score", "bond_id")
    if intent.get("want_greenwash"):
        query = query.filter(satellite_flag=True, satellite_status="verifiable")
        bonds = [bond for bond in query[:500] if observed_satellite(
            bond.satellite_source, bond.satellite_status, bond.satellite_model,
        )][:intent["limit"]]
    else:
        bonds = list(query[:intent["limit"]])
    lines.append(f"Matching records shown: {len(bonds)}")
    for bond in bonds:
        _append_bond_detail(lines, bond)
    if not bonds:
        lines.append("No matching records with the requested evidence are available.")
    return "\n".join(lines)


def _append_bond_detail(lines: list, bond) -> None:
    """Append detailed info for a single bond to the lines list."""
    from risk_scoring.models import PCRScore
    from pricing_analysis.models import PricingGap
    from greenwash_detector.models import GreenwashFlag
    from dashboard.workbench import observed_satellite

    # Latest PCRS
    score_obj = (PCRScore.objects.filter(bond=bond)
                 .order_by("-scored_at").first())
    pcrs = f"{score_obj.score:.1f}" if score_obj else "N/A"
    band = score_obj.risk_band if score_obj else "—"
    driver = score_obj.main_risk_driver.get("label", "Unavailable") if score_obj else "Unavailable"

    # Pricing gap
    pg = PricingGap.objects.filter(bond=bond).order_by("-checked_at").first()
    gap_str = f"{pg.gap_bps:+.0f} bps ({'stored market source' if pg.is_live else 'estimated spread'})" if pg else "N/A"

    # Greenwash
    gw = GreenwashFlag.objects.filter(bond=bond).order_by("-checked_at").first()
    observed = bool(gw and observed_satellite(gw.raw_ee_metadata, gw.verification_status, gw.model_version))
    gw_str = "Observed inconsistency: review required" if observed and gw.is_inconsistent else "Observed screen, not proof of project completion" if observed else "Unverifiable"

    lines.append(
        f"\n• {bond.bond_id} | {bond.issuer_name} | {bond.country}"
        f"\n  Category: {bond.project_category} | Issued: {bond.issuance_date} "
        f"| {bond.amount_millions}M {bond.currency}"
        f"\n  PCRS: {pcrs} ({band}) | Main driver: {driver}"
        f"\n  Pricing gap: {gap_str}"
        f"\n  Satellite: {gw_str}"
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def get_ai_response(user_message: str, chat_history: list | None = None) -> str:
    """
    Main function called by the Django view.

    Args:
        user_message: The user's question.
        chat_history: List of {"role": "user"|"model", "parts": [str]} dicts.

    Returns:
        The assistant's response as a string.
    """
    # Build live database context
    try:
        intent = _parse_intent(user_message)
        db_context = _build_db_context(intent)
    except Exception as exc:
        logger.warning("DB context build failed: %s", exc)
        return "Stored research data is temporarily unavailable. No bond-specific answer can be verified."

    try:
        model = _get_gemini_model()
    except EnvironmentError:
        return "Local data lookup (external AI is not configured).\n\n" + db_context

    # Compose the full message with context
    full_message = f"""
{db_context}

=== USER QUESTION ===
{user_message}
""".strip()

    # Build conversation history for Gemini
    history = []
    if chat_history:
        for msg in chat_history[-6:]:  # last 3 exchanges max
            history.append({
                "role": msg.get("role", "user"),
                "parts": [msg.get("content", "")],
            })

    try:
        chat = model.start_chat(history=history)
        response = chat.send_message(full_message)
        return response.text
    except Exception as exc:
        logger.error("Gemini API error: %s", exc)
        return "Local data lookup (external AI is unavailable).\n\n" + db_context
