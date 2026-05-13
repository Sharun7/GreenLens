# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""
Management command: python manage.py seed_risk_scenarios

Seeds the database with all 5 known failure scenarios and 3 legal risks
from the IIM Ahmedabad meeting answers.
"""
from django.core.management.base import BaseCommand
from risk_management.models import SystemFailureScenario, LegalRiskLog


FAILURE_SCENARIOS = [
    {
        "name": "Google Earth Engine API Down",
        "description": (
            "GEE occasionally goes into maintenance. When unavailable, "
            "greenwash detection completely stops and new bonds cannot be verified."
        ),
        "scenario_type": "api_failure",
        "probability": "medium",
        "severity": "high",
        "impact_description": (
            "Greenwash detection stops. New bonds cannot be verified. "
            "Dashboard shows stale data."
        ),
        "affected_modules": ["greenwash_detector"],
        "mitigation_strategy": (
            "Fallback hierarchy: "
            "1) Copernicus API fallback, "
            "2) Cached last known NDVI value, "
            "3) Flag bond as unverifiable with reason 'satellite_unavailable'."
        ),
        "mitigation_status": "mitigating",
        "has_fallback": True,
        "fallback_description": (
            "APIFailureHandler.handle_gee_failure() implements 3-level fallback: "
            "Copernicus → Cache → Unverifiable flag."
        ),
        "recovery_time_minutes": 60,
    },
    {
        "name": "Yahoo Finance API Rate Limit",
        "description": (
            "Yahoo Finance free tier has rate limits. When exceeded, "
            "pricing gap analysis stops and live data becomes stale."
        ),
        "scenario_type": "api_failure",
        "probability": "high",
        "severity": "medium",
        "impact_description": (
            "Pricing gap analysis stops. Mispriced bond detection fails. "
            "Live data becomes stale."
        ),
        "affected_modules": ["pricing_analysis"],
        "mitigation_strategy": (
            "Use last known prices with timestamp. "
            "Upgrade to paid financial data API (Alpha Vantage, Quandl). "
            "Multiple provider fallback."
        ),
        "mitigation_status": "identified",
        "has_fallback": True,
        "fallback_description": (
            "APIFailureHandler.handle_yahoo_finance_failure() returns "
            "last known prices with staleness warning."
        ),
        "recovery_time_minutes": 30,
    },
    {
        "name": "Model Drift — Climate Pattern Shift",
        "description": (
            "Model trained in 2024 used in 2028. Climate patterns shift. "
            "Predictions become increasingly wrong. "
            "Real example: Kerala 2018 floods were unprecedented — "
            "pre-2018 model would under-estimate Kerala flood risk."
        ),
        "scenario_type": "model_drift",
        "probability": "high",
        "severity": "high",
        "impact_description": (
            "PCRS scores increasingly inaccurate. "
            "Users make wrong investment decisions based on stale model."
        ),
        "affected_modules": ["risk_scoring"],
        "mitigation_strategy": (
            "Automated drift detection: monthly model performance check. "
            "Compare recent predictions against actual climate events. "
            "Alert team when accuracy drops below threshold. "
            "Flag dashboard: 'Scores under review — model updating'."
        ),
        "mitigation_status": "mitigating",
        "has_fallback": False,
        "fallback_description": (
            "ModelDriftDetector.check_pcrs_drift() runs monthly. "
            "Creates ModelDriftAlert when drift > 15%."
        ),
        "recovery_time_minutes": 2880,  # 48 hours for retraining
    },
    {
        "name": "Data Poisoning — Fake Project Location",
        "description": (
            "Bond issuer discloses fake project location. "
            "Provides low-risk area coordinates. "
            "Actual project is in high-risk area. "
            "GreenLens assigns low PCRS score. Investor is misled."
        ),
        "scenario_type": "data_poisoning",
        "probability": "low",
        "severity": "critical",
        "impact_description": (
            "Investor buys bond with artificially low risk score. "
            "Actual project faces high climate risk. "
            "Financial loss and reputational damage to GreenLens."
        ),
        "affected_modules": ["data_ingestion", "risk_scoring", "greenwash_detector"],
        "mitigation_strategy": (
            "Cross-check multiple location sources. "
            "NLP analysis of bond prospectus to extract location claims. "
            "Third-party registry verification. "
            "Location confidence indicator in UI."
        ),
        "mitigation_status": "identified",
        "has_fallback": False,
        "fallback_description": (
            "Location confidence indicator shows 'Country-level estimate' "
            "when precise coordinates unavailable."
        ),
        "recovery_time_minutes": None,
    },
    {
        "name": "Cloud Infrastructure Failure",
        "description": (
            "Render.com or hosting provider outage. "
            "Complete system unavailability."
        ),
        "scenario_type": "infrastructure",
        "probability": "low",
        "severity": "critical",
        "impact_description": (
            "Complete system down. All users affected. "
            "No bond data accessible."
        ),
        "affected_modules": [
            "data_ingestion", "risk_scoring", "pricing_analysis",
            "greenwash_detector", "dashboard",
        ],
        "mitigation_strategy": (
            "Multi-region deployment. "
            "Automated daily database snapshots. "
            "Disaster recovery plan with 4-hour RTO (Recovery Time Objective)."
        ),
        "mitigation_status": "identified",
        "has_fallback": False,
        "fallback_description": "Daily database backups. 4-hour RTO.",
        "recovery_time_minutes": 240,  # 4 hours RTO
    },
]


LEGAL_RISKS = [
    {
        "risk_type": "investment_advice",
        "description": (
            "User makes investment decision based on GreenLens score. "
            "Loss occurs. 'GreenLens mislead me' lawsuit filed. "
            "SEBI India, FCA UK, SEC US — investment advice requires registration."
        ),
        "severity": "high",
        "mitigation_action": (
            "Prominent disclaimer on every page: "
            "'GreenLens provides research analytics only. "
            "This is NOT financial advice, investment recommendation, or certified ESG rating. "
            "All investment decisions should be made with qualified financial advisors. "
            "GreenLens accepts no liability for investment losses.' "
            "Position as research tool, not financial advisor."
        ),
        "mitigation_status": "mitigating",
        "compliance_requirement": "SEBI, FCA, SEC investment advice regulations",
        "legal_review_required": True,
    },
    {
        "risk_type": "defamation",
        "description": (
            "Company X has a genuine green project. "
            "GreenLens flags it as 'Greenwash'. "
            "Company reputation is damaged. "
            "Defamation lawsuit filed. "
            "This is the most serious legal risk."
        ),
        "severity": "critical",
        "mitigation_action": (
            "Never say 'Confirmed Greenwash' — always 'Potential inconsistency'. "
            "Always show confidence score. "
            "Low confidence → 'Insufficient data', not 'Greenwash confirmed'. "
            "Always recommend independent verification. "
            "Publish methodology transparently. "
            "Provide appeal process for issuers to dispute flags. "
            "4-tier classification: Green/Yellow/Red/Grey."
        ),
        "mitigation_status": "mitigating",
        "compliance_requirement": "Defamation law (UK, EU, India)",
        "legal_review_required": True,
    },
    {
        "risk_type": "gdpr",
        "description": (
            "European users' data collected without GDPR compliance. "
            "Maximum fine: €20 million or 4% annual turnover. "
            "Currently low risk (anonymous usage), but if user accounts added, "
            "GDPR compliance becomes mandatory."
        ),
        "severity": "medium",
        "mitigation_action": (
            "Current: Anonymous usage — no personal data collected. Low risk. "
            "Future (when user accounts added): "
            "Privacy policy, cookie consent, data deletion rights, "
            "data processing agreements, EU data residency."
        ),
        "mitigation_status": "monitoring",
        "compliance_requirement": "EU GDPR Article 6, 13, 17",
        "compliance_deadline": None,
        "legal_review_required": False,
    },
]


class Command(BaseCommand):
    help = "Seed database with known failure scenarios and legal risks from IIM Ahmedabad meeting"

    def handle(self, *args, **options):
        self.stdout.write("Seeding failure scenarios...")

        created_scenarios = 0
        for data in FAILURE_SCENARIOS:
            _, created = SystemFailureScenario.objects.get_or_create(
                name=data["name"],
                defaults=data,
            )
            if created:
                created_scenarios += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ {created_scenarios} new failure scenarios seeded "
                f"({len(FAILURE_SCENARIOS)} total)"
            )
        )

        self.stdout.write("Seeding legal risks...")

        created_legal = 0
        for data in LEGAL_RISKS:
            _, created = LegalRiskLog.objects.get_or_create(
                risk_type=data["risk_type"],
                defaults=data,
            )
            if created:
                created_legal += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ {created_legal} new legal risks seeded "
                f"({len(LEGAL_RISKS)} total)"
            )
        )

        self.stdout.write(self.style.SUCCESS("\n✓ Category 14 risk data seeded successfully!"))
