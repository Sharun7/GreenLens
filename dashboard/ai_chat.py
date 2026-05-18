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
inside GreenLens — a satellite-verified green bond analysis platform.

Your role:
- Answer questions about green bonds, climate risk (PCRS scores), greenwashing, 
  pricing gaps, and ESG investing.
- Use the LIVE DATABASE CONTEXT provided in each message to give accurate, 
  data-driven answers referencing real bond IDs, scores, and countries.
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
    from data_ingestion.models import GreenBond, ClimateHazardData
    from risk_scoring.models import PCRScore
    from pricing_analysis.models import PricingGap
    from greenwash_detector.models import GreenwashFlag

    lines = []

    # ── Global stats ──
    total = GreenBond.objects.count()
    scored = PCRScore.objects.values("bond").distinct().count()
    mispriced = PricingGap.objects.filter(is_mispriced=True).count()
    flagged = GreenwashFlag.objects.filter(flag_raised=True).count()
    avg_pcrs = PCRScore.objects.aggregate(a=Avg("pcr_score"))["a"] or 0

    lines.append("=== GREENLENS LIVE DATABASE SUMMARY ===")
    lines.append(f"Total bonds: {total} | Scored: {scored} | Avg PCRS: {avg_pcrs:.1f}")
    lines.append(f"Mispriced: {mispriced} | Greenwash flags: {flagged}")
    lines.append("")

    # ── Specific bond lookup ──
    if intent.get("specific_bond"):
        try:
            bond = GreenBond.objects.get(bond_id__iexact=intent["specific_bond"])
            _append_bond_detail(lines, bond)
            return "\n".join(lines)
        except GreenBond.DoesNotExist:
            lines.append(f"Bond {intent['specific_bond']} not found in database.")

    # ── Build queryset ──
    qs = GreenBond.objects.prefetch_related("pcr_scores", "hazard_data",
                                            "pricing_gaps", "greenwash_flags")

    if intent["countries"]:
        qs = qs.filter(country__in=intent["countries"])
        lines.append(f"Filtering by countries: {', '.join(intent['countries'])}")

    if intent["category"]:
        qs = qs.filter(project_category=intent["category"])
        lines.append(f"Filtering by category: {intent['category']}")

    # Join with PCRScore for ordering
    bond_ids_with_scores = (
        PCRScore.objects
        .filter(bond__in=qs)
        .order_by("-pcr_score" if intent["want_high_risk"] else "pcr_score")
        .values_list("bond_id", flat=True)
        .distinct()[:20]
    )

    if intent["want_mispriced"]:
        mispriced_bond_ids = PricingGap.objects.filter(
            is_mispriced=True, bond__in=qs
        ).values_list("bond_id", flat=True)
        qs = qs.filter(id__in=mispriced_bond_ids)
        bond_ids_with_scores = list(mispriced_bond_ids)[:20]

    if intent["want_greenwash"]:
        flagged_bond_ids = GreenwashFlag.objects.filter(
            flag_raised=True, bond__in=qs
        ).values_list("bond_id", flat=True)
        qs = qs.filter(id__in=flagged_bond_ids)
        bond_ids_with_scores = list(flagged_bond_ids)[:20]

    # Fetch top N bonds
    limit = intent["limit"]
    if bond_ids_with_scores:
        # Preserve ordering
        bonds_map = {b.id: b for b in qs.filter(id__in=list(bond_ids_with_scores))}
        bonds = [bonds_map[bid] for bid in bond_ids_with_scores if bid in bonds_map][:limit]
    else:
        bonds = list(qs[:limit])

    lines.append(f"\n=== RELEVANT BONDS ({len(bonds)} shown) ===")
    for bond in bonds:
        _append_bond_detail(lines, bond)

    # ── Hazard-specific context ──
    if intent["hazard_field"] and intent["countries"]:
        hf = intent["hazard_field"]
        try:
            top_hazard = (
                ClimateHazardData.objects
                .filter(bond__country__in=intent["countries"])
                .order_by(f"-{hf}")
                .select_related("bond")[:3]
            )
            if top_hazard:
                lines.append(f"\n=== TOP BONDS BY {hf.upper()} ===")
                for h in top_hazard:
                    val = getattr(h, hf, None)
                    lines.append(f"  {h.bond.bond_id} ({h.bond.country}): {hf}={val:.2f}" if val else "")
        except Exception:
            pass

    return "\n".join(lines)


def _append_bond_detail(lines: list, bond) -> None:
    """Append detailed info for a single bond to the lines list."""
    from risk_scoring.models import PCRScore
    from pricing_analysis.models import PricingGap
    from greenwash_detector.models import GreenwashFlag

    # Latest PCRS
    score_obj = (PCRScore.objects.filter(bond=bond)
                 .order_by("-scored_at").first())
    pcrs = f"{score_obj.pcr_score:.1f}" if score_obj else "N/A"
    band = score_obj.risk_band if score_obj else "—"
    driver = score_obj.main_risk_driver if score_obj else "—"

    # Pricing gap
    pg = PricingGap.objects.filter(bond=bond).order_by("-computed_at").first()
    gap_str = f"{pg.pricing_gap_bps:+.0f} bps ({'MISPRICED' if pg.is_mispriced else 'fair'})" if pg else "N/A"

    # Greenwash
    gw = GreenwashFlag.objects.filter(bond=bond).order_by("-checked_at").first()
    gw_str = "⚠ FLAGGED" if (gw and gw.flag_raised) else "✓ Clear"

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
    try:
        model = _get_gemini_model()
    except EnvironmentError as e:
        return (
            "⚠️ AI assistant is not configured. "
            "Please set the `GEMINI_API_KEY` environment variable on Render. "
            f"Details: {e}"
        )

    # Build live database context
    try:
        intent = _parse_intent(user_message)
        db_context = _build_db_context(intent)
    except Exception as exc:
        logger.warning("DB context build failed: %s", exc)
        db_context = "⚠️ Database context unavailable — answering from general knowledge."

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
        return (
            "I encountered an error while processing your request. "
            "Please try again in a moment. If the problem persists, "
            "the Gemini API key may need to be refreshed."
        )
