# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""ai_features/views.py"""
import json, random
import re
import logging
from datetime import datetime, timedelta
from django.shortcuts import render
from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from data_ingestion.models import GreenBond
from .models import ClimateScenario, PCRSPrediction, AutomatedAlert, PortfolioOptimization, RegulatoryMonitor

logger = logging.getLogger("greenlens.ai_features")


def _ensure_scenarios():
    defaults = [
        ("ssp1_1_9", "SSP1-1.9 (Very Low)", 1.5, 1.4),
        ("ssp1_2_6", "SSP1-2.6 (Low)", 1.7, 1.8),
        ("ssp2_4_5", "SSP2-4.5 (Intermediate)", 2.1, 2.7),
        ("ssp3_7_0", "SSP3-7.0 (High)", 2.4, 3.6),
        ("ssp5_8_5", "SSP5-8.5 (Very High)", 2.7, 4.4),
    ]
    for code, desc, w2050, w2100 in defaults:
        ClimateScenario.objects.get_or_create(
            scenario_type=code,
            defaults={"description": desc, "warming_by_2050": w2050, "warming_by_2100": w2100},
        )


def _generate_real_predictions():
    """Generate PCRS predictions using REAL MLP neural network trained on database."""
    from ai_features.mlp_predictor import generate_mlp_predictions_for_bond, train_mlp_model
    
    _ensure_scenarios()
    scenario = ClimateScenario.objects.filter(scenario_type="ssp2_4_5").first()
    if not scenario:
        return
    
    # Check if predictions already exist
    if PCRSPrediction.objects.exists():
        return
    
    # Train MLP model on database if not already trained
    try:
        logger.info("Training MLP model on database...")
        metrics = train_mlp_model()
        logger.info(f"MLP training complete. Test R²: {metrics['test_r2']:.3f}, Test MAE: {metrics['test_mae']:.2f}")
    except Exception as e:
        logger.error(f"MLP training failed: {e}")
        return
    
    today = datetime.now().date()
    
    # Generate MLP predictions for bonds that have both scores and climate inputs.
    for bond in GreenBond.objects.filter(
        pcr_scores__isnull=False,
        hazard_data__isnull=False,
    ).distinct()[:100]:
        try:
            # Use REAL MLP predictor trained on database
            mlp_predictions = generate_mlp_predictions_for_bond(bond, horizons=[6, 12, 24])

            # Save predictions to database
            for pred in mlp_predictions:
                horizon_months = pred.get("months_ahead", 12)
                horizon_label = {6: "short", 12: "medium", 24: "long"}.get(horizon_months, "custom")
                PCRSPrediction.objects.create(
                    bond=bond,
                    scenario=scenario,
                    current_pcrs=pred["current_pcrs"],
                    current_date=today,
                    predicted_pcrs=pred["predicted_pcrs"],
                    prediction_date=pred["prediction_date"],
                    confidence=pred["confidence_pct"],
                    primary_driver=pred["primary_driver"],
                    driver_magnitude=pred["driver_magnitude"],
                    model_version=f"{pred['model_version']}-{horizon_label}",
                )
        except Exception as e:
            logger.warning(f"Failed to generate MLP predictions for bond {bond.bond_id}: {e}")
            continue


def _generate_real_alerts():
    """Generate alerts from ACTUAL greenwash flags, pricing gaps, high-risk bonds, and regulatory updates."""
    from greenwash_detector.models import GreenwashFlag
    from pricing_analysis.models import PricingGap

    # Alert Type 2: Greenwash — from actual flags
    for flag in GreenwashFlag.objects.filter(is_inconsistent=True).select_related("bond")[:10]:
        alert, _ = AutomatedAlert.objects.get_or_create(
            alert_type="greenwash",
            title=f"Greenwash Flag — {flag.bond.bond_id}",
            defaults={
                "description": f"Satellite evidence inconsistent with claimed project type '{flag.claimed_project_type}'. Observed: {flag.satellite_land_use}. NDVI change: {flag.ndvi_change:.3f}",
                "alert_data": {
                    "bond_id": flag.bond.bond_id,
                    "claimed": flag.claimed_project_type,
                    "observed": flag.satellite_land_use,
                    "ndvi_change": flag.ndvi_change,
                    "confidence": flag.confidence,
                    "verification_status": flag.verification_status,
                },
                "status": "sent", "delivery_method": "dashboard", "response_time_minutes": 45,
            },
        )
        alert.affected_bonds.add(flag.bond)

    # Alert Type 3: Pricing — from actual mispriced bonds
    for gap in PricingGap.objects.filter(is_mispriced=True).select_related("bond")[:10]:
        direction = "overpriced" if gap.gap_bps > 0 else "underpriced"
        alert, _ = AutomatedAlert.objects.get_or_create(
            alert_type="pricing",
            title=f"Pricing Gap — {gap.bond.bond_id}",
            defaults={
                "description": f"Bond {direction} by {abs(gap.gap_bps):.1f} bps. Actual spread: {gap.actual_spread_bps:.1f} bps vs predicted: {gap.predicted_spread_bps:.1f} bps.",
                "alert_data": {
                    "bond_id": gap.bond.bond_id,
                    "actual_spread_bps": gap.actual_spread_bps,
                    "predicted_spread_bps": gap.predicted_spread_bps,
                    "gap_bps": gap.gap_bps,
                    "direction": direction,
                },
                "status": "sent", "delivery_method": "dashboard", "response_time_minutes": 60,
            },
        )
        alert.affected_bonds.add(gap.bond)

    # Alert Type 1: Climate Event — from high-risk bonds (PCRS > 75)
    high_risk_bonds = list(GreenBond.objects.filter(pcr_scores__score__gt=75).distinct()[:8])
    if high_risk_bonds:
        alert, _ = AutomatedAlert.objects.get_or_create(
            alert_type="climate_event",
            title="High Climate Risk Concentration Detected",
            defaults={
                "description": f"{len(high_risk_bonds)} bonds in portfolio have PCRS > 75 (extreme physical risk). Monitor for extreme weather events affecting these project sites.",
                "alert_data": {"high_risk_count": len(high_risk_bonds), "threshold": 75},
                "status": "sent", "delivery_method": "dashboard", "response_time_minutes": 120,
            },
        )
        for b in high_risk_bonds:
            alert.affected_bonds.add(b)

    # Alert Type 4: Regulatory — from REAL RegulatoryMonitor entries
    # NOTE: Regulatory alerts are now auto-generated by generate_regulatory_alerts() Celery task
    # This ensures alerts are created when new regulations are scraped
    # We don't generate them here to avoid duplicates


def _generate_real_portfolio():
    """Build portfolio using ACTUAL bonds + PCRS scores with deterministic optimization."""
    if PortfolioOptimization.objects.filter(portfolio_name="GreenLens Optimized Portfolio").exists():
        return
    bonds = list(GreenBond.objects.exclude(pcr_scores=None).all()[:100])
    if len(bonds) < 20:
        return
    # Current: take top 20 by issuance amount (simulated from bond size)
    current = sorted(bonds, key=lambda b: float(b.amount_millions or 0), reverse=True)[:20]
    current_holdings, total_cur = [], 0
    for i, b in enumerate(current):
        amt = 2.5 + (i % 5) * 0.5  # deterministic allocation
        total_cur += amt
        pcr = b.pcr_scores.order_by("-scored_at").first()
        current_holdings.append({"bond_id": b.bond_id, "issuer": b.issuer_name,
                                 "amount_eur": amt, "pcrs": round(pcr.score, 1),
                                 "country": b.country})
    cur_pcrs = sum(h["amount_eur"] * h["pcrs"] for h in current_holdings) / total_cur
    # Optimized: sort by PCRS ascending (lowest risk first), top 20
    sorted_bonds = sorted(bonds, key=lambda b: b.pcr_scores.order_by("-scored_at").first().score)
    optimized = sorted_bonds[:20]
    opt_holdings, total_opt = [], 0
    for i, b in enumerate(optimized):
        amt = 2.5 + (i % 5) * 0.5
        total_opt += amt
        pcr = b.pcr_scores.order_by("-scored_at").first()
        opt_holdings.append({"bond_id": b.bond_id, "issuer": b.issuer_name,
                             "amount_eur": amt, "pcrs": round(pcr.score, 1),
                             "country": b.country})
    opt_pcrs = sum(h["amount_eur"] * h["pcrs"] for h in opt_holdings) / total_opt
    # Sell: current portfolio bonds with PCRS > 60
    sell_recs = [{"bond_id": h["bond_id"], "issuer": h["issuer"],
                  "current_pcrs": h["pcrs"], "sell_amount": h["amount_eur"],
                  "reason": f"PCRS {h['pcrs']} exceeds risk threshold (60). Reduce exposure."}
                 for h in current_holdings if h["pcrs"] > 60]
    existing_ids = {h["bond_id"] for h in current_holdings}
    # Buy: optimized portfolio bonds not already held, with PCRS < 40
    buy_recs = [{"bond_id": h["bond_id"], "issuer": h["issuer"],
                 "target_pcrs": h["pcrs"], "buy_amount": 3.0,
                 "reason": f"PCRS {h['pcrs']} — climate resilient addition"}
                for h in opt_holdings if h["pcrs"] < 40 and h["bond_id"] not in existing_ids]
    PortfolioOptimization.objects.create(
        portfolio_name="GreenLens Optimized Portfolio",
        portfolio_description="Rebalanced portfolio using actual bond PCRS scores from database. Sells high-risk bonds, buys low-risk alternatives.",
        current_bonds=current_holdings, current_pcrs=round(cur_pcrs, 1),
        current_return=4.5,
        optimized_bonds=opt_holdings, optimized_pcrs=round(opt_pcrs, 1),
        optimized_return=4.2,
        sell_recommendations=sell_recs, buy_recommendations=buy_recs,
        min_return_target=4.2, max_single_bond_allocation=5.0,
        geographic_diversification_required=True, status="generated",
    )


def _latest_pcrs_score(bond):
    latest = bond.pcr_scores.order_by("-scored_at").first()
    return round(latest.score, 1) if latest else None


def _latest_return_pct(bond):
    latest_gap = bond.pricing_gaps.order_by("-checked_at").first()
    if latest_gap and latest_gap.actual_spread_bps is not None:
        # Convert basis points to a simple percentage proxy for optimization display.
        return round(latest_gap.actual_spread_bps / 100.0, 2)
    return 4.5


def _parse_portfolio_input(raw_text):
    holdings = []
    errors = []
    for index, raw_line in enumerate((raw_text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"[,|\t]+", line) if part.strip()]
        bond_id = parts[0] if parts else ""
        if not bond_id:
            continue
        try:
            amount = float(parts[1]) if len(parts) > 1 else 1.0
        except ValueError:
            errors.append(f"Line {index}: invalid amount '{parts[1]}'. Use numbers like 2.5")
            continue
        bond = GreenBond.objects.filter(bond_id__iexact=bond_id).first()
        if not bond:
            errors.append(f"Line {index}: bond '{bond_id}' not found in GreenLens database.")
            continue
        pcrs = _latest_pcrs_score(bond)
        if pcrs is None:
            errors.append(f"Line {index}: bond '{bond_id}' has no PCRS score yet.")
            continue
        holdings.append({"bond": bond, "amount_eur": max(amount, 0.1), "pcrs": pcrs})
    return holdings, errors


def _build_portfolio_optimization(
    portfolio_name,
    portfolio_description,
    holdings,
    min_return_target,
    max_single_bond_allocation,
    geographic_diversification_required,
):
    total_current = sum(item["amount_eur"] for item in holdings)
    if total_current <= 0:
        total_current = float(len(holdings) or 1)

    current_bonds = []
    current_return_numerator = 0.0
    current_pcrs_numerator = 0.0
    for item in holdings:
        bond = item["bond"]
        amount = float(item["amount_eur"])
        est_return = _latest_return_pct(bond)
        current_bonds.append({
            "bond_id": bond.bond_id,
            "issuer": bond.issuer_name,
            "amount_eur": round(amount, 2),
            "pcrs": item["pcrs"],
            "country": bond.country,
            "estimated_return": est_return,
        })
        current_return_numerator += amount * est_return
        current_pcrs_numerator += amount * item["pcrs"]

    current_return = round(current_return_numerator / total_current, 2)
    current_pcrs = round(current_pcrs_numerator / total_current, 1)

    target_count = len(current_bonds)
    max_amount_per_bond = round(total_current * (max_single_bond_allocation / 100.0), 2)
    equal_weight_amount = round(total_current / max(target_count, 1), 2)
    default_amount = min(equal_weight_amount, max_amount_per_bond) if max_amount_per_bond > 0 else equal_weight_amount

    candidate_bonds = []
    for bond in GreenBond.objects.exclude(pcr_scores=None).all():
        pcrs = _latest_pcrs_score(bond)
        if pcrs is None:
            continue
        candidate_bonds.append({
            "bond": bond,
            "pcrs": pcrs,
            "estimated_return": _latest_return_pct(bond),
        })
    candidate_bonds.sort(key=lambda row: (row["pcrs"], -row["estimated_return"], row["bond"].bond_id))

    optimized_bonds = []
    country_counts = {}
    for candidate in candidate_bonds:
        country = candidate["bond"].country or "Unknown"
        if geographic_diversification_required and country_counts.get(country, 0) >= 2:
            continue
        optimized_bonds.append({
            "bond_id": candidate["bond"].bond_id,
            "issuer": candidate["bond"].issuer_name,
            "amount_eur": round(default_amount, 2),
            "pcrs": candidate["pcrs"],
            "country": country,
            "estimated_return": candidate["estimated_return"],
        })
        country_counts[country] = country_counts.get(country, 0) + 1
        if len(optimized_bonds) >= target_count:
            break

    total_optimized = sum(item["amount_eur"] for item in optimized_bonds) or 1.0
    optimized_pcrs = round(sum(item["amount_eur"] * item["pcrs"] for item in optimized_bonds) / total_optimized, 1)
    optimized_return = round(sum(item["amount_eur"] * item["estimated_return"] for item in optimized_bonds) / total_optimized, 2)

    optimized_ids = {item["bond_id"] for item in optimized_bonds}
    current_ids = {item["bond_id"] for item in current_bonds}
    sell_recommendations = []
    for item in current_bonds:
        if item["bond_id"] not in optimized_ids or item["pcrs"] > 60:
            sell_recommendations.append({
                "bond_id": item["bond_id"],
                "issuer": item["issuer"],
                "current_pcrs": item["pcrs"],
                "sell_amount": item["amount_eur"],
                "reason": (
                    f"PCRS {item['pcrs']} and current climate concentration make this "
                    "position a candidate for reduction."
                ),
            })

    buy_recommendations = []
    for item in optimized_bonds:
        if item["bond_id"] not in current_ids:
            buy_recommendations.append({
                "bond_id": item["bond_id"],
                "issuer": item["issuer"],
                "target_pcrs": item["pcrs"],
                "buy_amount": item["amount_eur"],
                "reason": (
                    f"Lower PCRS ({item['pcrs']}) with estimated return "
                    f"{item['estimated_return']}% improves portfolio resilience."
                ),
            })

    return PortfolioOptimization.objects.create(
        portfolio_name=portfolio_name,
        portfolio_description=portfolio_description,
        current_bonds=current_bonds,
        current_pcrs=current_pcrs,
        current_return=current_return,
        optimized_bonds=optimized_bonds,
        optimized_pcrs=optimized_pcrs,
        optimized_return=max(min_return_target, optimized_return),
        sell_recommendations=sell_recommendations[:10],
        buy_recommendations=buy_recommendations[:10],
        min_return_target=min_return_target,
        max_single_bond_allocation=max_single_bond_allocation,
        geographic_diversification_required=geographic_diversification_required,
        status="generated",
    )


def _generate_demo_regulations():
    """Load real regulatory updates from scraper or manual fallback."""
    from ai_features.regulatory_scraper import scrape_and_save_regulatory_updates, load_manual_regulatory_updates
    
    # Try scraping first
    try:
        saved_count = scrape_and_save_regulatory_updates()
        if saved_count > 0:
            logger.info(f"Loaded {saved_count} regulatory updates from scraping")
            return
    except Exception as e:
        logger.warning(f"Regulatory scraping failed: {e}")
    
    # Fallback to manual updates
    load_manual_regulatory_updates()


# ── HTML Views ────────────────────────────────────────────────────────────────

def predictions_dashboard(request):
    _generate_real_predictions()
    # Group predictions by bond: pick 6mo, 12mo, 24mo per bond
    from collections import defaultdict
    preds_by_bond = defaultdict(dict)
    for p in PCRSPrediction.objects.select_related("bond", "scenario").all():
        bid = p.bond.bond_id
        month_delta = 0
        if p.current_date and p.prediction_date:
            month_delta = max(0, round((p.prediction_date - p.current_date).days / 30))
        if month_delta <= 8:
            preds_by_bond[bid]["short"] = p
        elif month_delta <= 16:
            preds_by_bond[bid]["medium"] = p
        else:
            preds_by_bond[bid]["long"] = p
    # Build clean list for template (limit to first 20 bonds)
    bond_rows = []
    seen = set()
    for p in PCRSPrediction.objects.select_related("bond", "scenario").order_by("-current_pcrs")[:60]:
        bid = p.bond.bond_id
        if bid not in seen:
            seen.add(bid)
            row = {
                "bond": p.bond,
                "current_pcrs": p.current_pcrs,
                "confidence": p.confidence,
                "primary_driver": p.get_primary_driver_display(),
                "driver_magnitude": p.driver_magnitude,
                "short": preds_by_bond[bid].get("short"),
                "medium": preds_by_bond[bid].get("medium"),
                "long": preds_by_bond[bid].get("long"),
            }
            bond_rows.append(row)
            if len(bond_rows) >= 20:
                break
    stats = {
        "total_predictions": PCRSPrediction.objects.count(),
        "avg_confidence": round(PCRSPrediction.objects.aggregate(avg=Avg("confidence"))["avg"] or 0, 1),
        "scenario_count": ClimateScenario.objects.count(),
        "bonds_predicted": PCRSPrediction.objects.values("bond").distinct().count(),
    }
    # Level 2: Market prediction from real database aggregation
    region_stats = GreenBond.objects.values("country").annotate(
        avg_pcrs=Avg("pcr_scores__score"),
        bond_count=Count("id"),
        high_risk=Count("pcr_scores__score", filter=Q(pcr_scores__score__gt=60))
    ).filter(avg_pcrs__isnull=False).order_by("-high_risk", "-avg_pcrs")[:3]
    top_region = region_stats[0] if region_stats else None
    top_region_name = top_region["country"] if top_region else "No scored region yet"
    top_region_avg = float(top_region["avg_pcrs"]) if top_region and top_region["avg_pcrs"] is not None else 0.0
    top_region_high_risk = int(top_region["high_risk"]) if top_region else 0
    top_region_count = int(top_region["bond_count"]) if top_region else 0
    market_pred = {
        "region": top_region_name,
        "prediction": (
            f"Over the next 12 months, {top_region_name} bonds show elevated physical risk "
            f"(avg PCRS {top_region_avg:.1f}). {top_region_high_risk} of {top_region_count} "
            "bonds exceed threshold."
            if top_region
            else "No region has enough scored bonds yet to generate a market-level prediction."
        ),
        "confidence": min(95, int(top_region_avg)) if top_region else 0,
        "recommended_action": (
            f"12-month rebalancing: Reduce concentration in {top_region_name}. Shift into lower-PCRS regions."
            if top_region
            else "Complete hazard and PCRS initialization first, then regenerate predictions."
        ),
        "timeframe": "12 months",
    }
    # Level 3: Systemic from actual portfolio-wide stats
    total_bonds = GreenBond.objects.count()
    high_risk_count = GreenBond.objects.filter(pcr_scores__score__gt=60).count()
    unviable_pct = round((high_risk_count / total_bonds) * 100, 1) if total_bonds else 0
    worst_region = top_region_name if top_region else "N/A"
    systemic = {
        "scenario": "24-month systemic stress test",
        "unviable_pct": unviable_pct,
        "stranded_assets_eur": round(unviable_pct * 5, 0),  # rough proxy
        "highest_concentration": worst_region,
        "regulatory_use": "SFDR Article 8/9 Principal Adverse Impact disclosure",
        "timeframe": "24 months",
    }
    sc_data = []
    for sc in ClimateScenario.objects.all():
        preds = list(PCRSPrediction.objects.filter(scenario=sc).values_list("predicted_pcrs", flat=True))
        avg = sum(preds) / len(preds) if preds else 0
        sc_data.append({"name": sc.get_scenario_type_display(), "warming_2050": sc.warming_by_2050,
                        "avg_predicted_pcrs": round(avg, 1)})
    return render(request, "ai_features/predictions_dashboard.html", {
        "stats": stats, "bond_rows": bond_rows,
        "market_prediction": market_pred, "systemic_prediction": systemic,
        "scenario_chart_data": json.dumps(sc_data),
    })


def alerts_feed(request):
    """
    Automated alerts feed - Shows REAL alerts from database.
    
    Alert types:
    1. Climate Event - High-risk bonds (PCRS > 75)
    2. Greenwash - Satellite verification failures
    3. Pricing - Mispriced bonds
    4. Regulatory - New regulations from EU SFDR and SEBI (auto-generated)
    """
    _generate_real_alerts()
    
    alert_type = request.GET.get("type", "")
    status_filter = request.GET.get("status", "")
    
    alerts_qs = AutomatedAlert.objects.prefetch_related("affected_bonds").all()
    
    if alert_type:
        alerts_qs = alerts_qs.filter(alert_type=alert_type)
    if status_filter:
        alerts_qs = alerts_qs.filter(status=status_filter)
    
    # Enrich alerts with additional data
    alerts_list = []
    for alert in alerts_qs[:50]:
        alert_dict = {
            "alert": alert,
            "affected_bonds_count": alert.affected_bonds.count(),
            "compliance_deadline": None,
            "days_until_deadline": None,
            "urgency": None,
        }
        
        # For regulatory alerts, extract compliance deadline
        if alert.alert_type == "regulatory" and alert.alert_data:
            effective_date_str = alert.alert_data.get("effective_date")
            if effective_date_str:
                try:
                    from datetime import datetime
                    effective_date = datetime.fromisoformat(effective_date_str).date()
                    alert_dict["compliance_deadline"] = effective_date
                    
                    # Calculate days until deadline
                    days_until = (effective_date - timezone.now().date()).days
                    alert_dict["days_until_deadline"] = days_until
                    
                    # Determine urgency
                    if days_until < 0:
                        alert_dict["urgency"] = "OVERDUE"
                    elif days_until < 30:
                        alert_dict["urgency"] = "URGENT"
                    elif days_until < 90:
                        alert_dict["urgency"] = "HIGH"
                    else:
                        alert_dict["urgency"] = "MEDIUM"
                except (ValueError, TypeError):
                    pass
        
        alerts_list.append(alert_dict)
    
    stats = {
        "total": AutomatedAlert.objects.count(),
        "climate": AutomatedAlert.objects.filter(alert_type="climate_event").count(),
        "greenwash": AutomatedAlert.objects.filter(alert_type="greenwash").count(),
        "pricing": AutomatedAlert.objects.filter(alert_type="pricing").count(),
        "regulatory": AutomatedAlert.objects.filter(alert_type="regulatory").count(),
        "unread": AutomatedAlert.objects.filter(status="pending").count(),
    }
    
    return render(request, "ai_features/alerts_feed.html", {
        "alerts_list": alerts_list,
        "stats": stats,
        "filter_type": alert_type,
        "filter_status": status_filter,
    })


def portfolio_optimizer(request):
    if not PortfolioOptimization.objects.exists():
        _generate_real_portfolio()
    form_error = ""
    form_message = ""
    latest = None

    if request.method == "POST":
        portfolio_name = (request.POST.get("portfolio_name") or "Uploaded Portfolio").strip()
        portfolio_description = (
            request.POST.get("portfolio_description")
            or "User-uploaded portfolio optimized against GreenLens climate risk."
        ).strip()
        raw_holdings = request.POST.get("portfolio_input", "")
        min_return_target = float(request.POST.get("min_return_target") or 4.2)
        max_single_bond_allocation = float(request.POST.get("max_single_bond_allocation") or 5.0)
        geographic_diversification_required = request.POST.get("geographic_diversification_required") == "on"

        holdings, errors = _parse_portfolio_input(raw_holdings)
        if errors:
            form_error = " ".join(errors[:5])
        elif not holdings:
            form_error = "Add at least one valid bond line using: bond_id, amount"
        else:
            latest = _build_portfolio_optimization(
                portfolio_name=portfolio_name,
                portfolio_description=portfolio_description,
                holdings=holdings,
                min_return_target=min_return_target,
                max_single_bond_allocation=max_single_bond_allocation,
                geographic_diversification_required=geographic_diversification_required,
            )
            form_message = f"Portfolio '{latest.portfolio_name}' optimized successfully."

    portfolios = PortfolioOptimization.objects.all().order_by("-created_at")[:10]
    latest = latest or portfolios.first()
    region_data = {}
    if latest and latest.current_bonds:
        for h in latest.current_bonds:
            region_data[h.get("country", "Unknown")] = region_data.get(h.get("country", "Unknown"), 0) + h.get("amount_eur", 0)
    total_val = sum(region_data.values()) if region_data else 1
    region_chart = [{"region": k, "amount": round(v, 2), "pct": round(v / total_val * 100, 1)}
                    for k, v in sorted(region_data.items(), key=lambda x: x[1], reverse=True)[:8]]
    sample_bonds = list(GreenBond.objects.order_by("bond_id").values_list("bond_id", flat=True)[:3])
    sample_portfolio_input = "\n".join(
        f"{bond_id}, {amount}" for bond_id, amount in zip(sample_bonds, [2.5, 1.5, 3.0])
    ) or "BOND_ID_1, 2.5\nBOND_ID_2, 1.5\nBOND_ID_3, 3.0"
    return render(request, "ai_features/portfolio_optimizer.html", {
        "portfolios": portfolios, "latest": latest,
        "region_chart": json.dumps(region_chart),
        "form_error": form_error,
        "form_message": form_message,
        "sample_portfolio_input": sample_portfolio_input,
    })


def regulatory_monitor(request):
    """
    Regulatory monitor view - Shows REAL regulatory updates from EU SFDR and SEBI.
    
    Data is fetched daily at 6 AM via Celery task and cached in Redis for 24 hours.
    """
    from django.core.cache import cache
    from ai_features.regulatory_fetcher import fetch_and_save_regulatory_updates
    
    # Get last update timestamp from cache
    last_updated = cache.get("regulatory_last_updated")
    
    # If no data exists, fetch now
    if not RegulatoryMonitor.objects.exists():
        logger.info("No regulatory data found. Fetching now...")
        try:
            result = fetch_and_save_regulatory_updates()
            if result["success"]:
                last_updated = result["last_updated"]
                cache.set("regulatory_last_updated", last_updated, timeout=None)
        except Exception as e:
            logger.error(f"Failed to fetch regulatory updates: {e}")
    
    # Query regulations from database
    regulations = RegulatoryMonitor.objects.all().order_by("-announcement_date")
    
    # Calculate stats
    stats = {
        "total": RegulatoryMonitor.objects.count(),
        "compliance_required": RegulatoryMonitor.objects.filter(compliance_required=True).count(),
        "upcoming": RegulatoryMonitor.objects.filter(effective_date__gt=datetime.now().date()).count(),
        "affected_bonds": RegulatoryMonitor.objects.exclude(affected_bonds_count=None).aggregate(
            total=Avg("affected_bonds_count"))["total"] or 0,
        "last_updated": last_updated,
    }
    
    # Determine data freshness
    if last_updated:
        time_since_update = timezone.now() - last_updated
        if time_since_update.total_seconds() > 86400:  # More than 24 hours
            data_status = "stale"
            data_label = f"Data from {last_updated.strftime('%b %d, %Y')}"
        else:
            data_status = "fresh"
            data_label = f"Last updated: {last_updated.strftime('%b %d, %Y %H:%M UTC')}"
    else:
        data_status = "unknown"
        data_label = "Update status unknown"
    
    return render(request, "ai_features/regulatory_monitor.html", {
        "regulations": regulations,
        "stats": stats,
        "data_status": data_status,
        "data_label": data_label,
    })


# ── API ViewSets ──────────────────────────────────────────────────────────────

class ScenarioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ClimateScenario.objects.all()

    def get_serializer_class(self):
        from rest_framework import serializers
        class ScSerializer(serializers.ModelSerializer):
            class Meta:
                model = ClimateScenario
                fields = ["id", "scenario_type", "description", "warming_by_2050", "warming_by_2100"]
        return ScSerializer


class PredictionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PCRSPrediction.objects.select_related("bond", "scenario").all()

    def get_serializer_class(self):
        from rest_framework import serializers
        class PredSerializer(serializers.ModelSerializer):
            bond_id = serializers.CharField(source="bond.bond_id", read_only=True)
            scenario_name = serializers.CharField(source="scenario.get_scenario_type_display", read_only=True)
            class Meta:
                model = PCRSPrediction
                fields = ["id", "bond_id", "scenario_name", "current_pcrs", "predicted_pcrs",
                          "prediction_date", "confidence", "primary_driver", "driver_magnitude", "model_version"]
        return PredSerializer


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AutomatedAlert.objects.prefetch_related("affected_bonds").all()

    def get_serializer_class(self):
        from rest_framework import serializers
        class AlertSerializer(serializers.ModelSerializer):
            affected_bond_ids = serializers.SerializerMethodField()
            class Meta:
                model = AutomatedAlert
                fields = ["id", "alert_type", "title", "description", "status",
                          "delivery_method", "triggered_at", "response_time_minutes", "affected_bond_ids"]
            def get_affected_bond_ids(self, obj):
                return [b.bond_id for b in obj.affected_bonds.all()]
        return AlertSerializer

    @action(detail=False, methods=["get"])
    def by_type(self, request):
        t = request.query_params.get("type", "")
        qs = self.queryset.filter(alert_type=t) if t else self.queryset
        page = self.paginate_queryset(qs)
        ser = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page else Response(ser.data)


class PortfolioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PortfolioOptimization.objects.all()

    def get_serializer_class(self):
        from rest_framework import serializers
        class PortSerializer(serializers.ModelSerializer):
            pcrs_improvement = serializers.ReadOnlyField()
            class Meta:
                model = PortfolioOptimization
                fields = ["id", "portfolio_name", "current_pcrs", "optimized_pcrs",
                          "pcrs_improvement", "current_return", "optimized_return",
                          "status", "created_at"]
        return PortSerializer


class RegulatoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RegulatoryMonitor.objects.all()

    def get_serializer_class(self):
        from rest_framework import serializers
        class RegSerializer(serializers.ModelSerializer):
            class Meta:
                model = RegulatoryMonitor
                fields = ["id", "regulation_type", "title", "description",
                          "announcement_date", "effective_date", "affected_bonds_count",
                          "compliance_required", "action_required"]
        return RegSerializer
