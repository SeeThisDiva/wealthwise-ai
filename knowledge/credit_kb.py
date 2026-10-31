"""
Credit Card Knowledge Base — Production Rules for Card Tiering & Reward Optimization.
Implements underwriting qualification gates, credit tiers (Super-Premium to Entry),
spend category reward prioritization, and secured FD-backed credit rebuilding.
"""

from __future__ import annotations

from core.facts import Fact, WorkingMemory
from core.rules import Rule
from data.catalog import CREDIT_CARD_CATALOG


def build_credit_rules() -> list[Rule]:
    """Generates production rules for the Credit Card Advisory Domain."""
    rules: list[Rule] = []

    # --------------------------------------------------------------------------
    # RULE 1: Unsecured Card Disqualification -> Secured FD Fallback
    # --------------------------------------------------------------------------
    def cond_unsecured_reject(wm: WorkingMemory) -> bool:
        score = int(wm.get_value("user.credit_score", 650))
        income = float(wm.get_value("user.monthly_income", 0.0))
        emis = float(wm.get_value("user.existing_emis", 0.0))
        emp = wm.get_value("user.employment_type", "Salaried")
        foir = (emis / income) if income > 0 else 1.0

        return (
            score < 650 or
            income < 15000 or
            foir > 0.50 or
            emp in {"Student", "Unemployed"}
        )

    def act_unsecured_reject(wm: WorkingMemory, r: Rule) -> list[Fact]:
        score = int(wm.get_value("user.credit_score", 650))
        income = float(wm.get_value("user.monthly_income", 0.0))
        return [
            Fact(name="credit_card.eligible", value=False, certainty=0.95, domain="credit", source="inferred"),
            Fact(name="credit_card.tier", value="Secured Rebuilder", certainty=0.95, domain="credit", source="inferred"),
            Fact(
                name="credit_card.headline",
                value="Secured Credit Card Recommended (Credit Score Repair)",
                certainty=0.95,
                domain="credit",
                source="inferred",
                explanation=f"Applicant does not satisfy unsecured credit card criteria (Score: {score}, Income: ₹{income:,.0f}). A secured card against FD rebuilds CIBIL."
            ),
            Fact(
                name="credit_card.products",
                value=CREDIT_CARD_CATALOG["entry_or_secured"],
                certainty=0.95,
                domain="credit",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_CARD_01_SECURED_FALLBACK",
        domain="credit",
        description="Subprime / High-Risk Guardrail: Routes applicants with score < 650 or high FOIR to secured FD cards.",
        priority=280,
        conditions=[cond_unsecured_reject],
        action=act_unsecured_reject,
        cf_rule=0.95,
        condition_descriptions=["Score < 650 OR Income < ₹15,000 OR FOIR > 50% OR Student/Unemployed"],
        consequence_fact_names=["credit_card.eligible", "credit_card.tier", "credit_card.headline", "credit_card.products"]
    ))

    # --------------------------------------------------------------------------
    # RULE 2: Super-Premium Luxury Card Tier
    # --------------------------------------------------------------------------
    def cond_super_premium(wm: WorkingMemory) -> bool:
        if wm.get_value("credit_card.eligible") is False:
            return False
        score = int(wm.get_value("user.credit_score", 0))
        income = float(wm.get_value("user.monthly_income", 0.0))
        return score >= 780 and income >= 150000

    def act_super_premium(wm: WorkingMemory, r: Rule) -> list[Fact]:
        spend_cat = wm.get_value("user.preferred_spend_category", "General")
        cards = list(CREDIT_CARD_CATALOG["super_premium"])

        # Prioritize card matching spend category
        if "Travel" in spend_cat or "Dining" in spend_cat:
            cards.sort(key=lambda c: "Infinia" in c.name, reverse=True)

        return [
            Fact(name="credit_card.eligible", value=True, certainty=0.95, domain="credit", source="inferred"),
            Fact(name="credit_card.tier", value="Super-Premium Luxury", certainty=0.95, domain="credit", source="inferred"),
            Fact(
                name="credit_card.headline",
                value="Eligible — Super-Premium Luxury Tier (Elite Rewards & Lounge)",
                certainty=0.95,
                domain="credit",
                source="inferred",
                explanation="High disposable income and excellent credit discipline qualify for institutional top-tier metal cards."
            ),
            Fact(name="credit_card.products", value=cards, certainty=0.95, domain="credit", source="inferred")
        ]

    rules.append(Rule(
        rule_id="RULE_CARD_02_SUPER_PREMIUM_TIER",
        domain="credit",
        description="Super-Premium Luxury Tier: Extended to applicants with CIBIL >= 780 and Monthly Income >= ₹1.5 Lakh.",
        priority=240,
        conditions=[cond_super_premium],
        action=act_super_premium,
        cf_rule=0.95,
        condition_descriptions=["CIBIL Score >= 780", "Monthly Income >= ₹150,000"],
        consequence_fact_names=["credit_card.eligible", "credit_card.tier", "credit_card.headline", "credit_card.products"]
    ))

    # --------------------------------------------------------------------------
    # RULE 3: Upper-Mid Tier
    # --------------------------------------------------------------------------
    def cond_upper_mid(wm: WorkingMemory) -> bool:
        if wm.get_value("credit_card.eligible") is False or wm.has_fact("credit_card.tier"):
            return False
        score = int(wm.get_value("user.credit_score", 0))
        income = float(wm.get_value("user.monthly_income", 0.0))
        return score >= 730 and income >= 75000

    def act_upper_mid(wm: WorkingMemory, r: Rule) -> list[Fact]:
        cards = list(CREDIT_CARD_CATALOG["upper_mid"])
        return [
            Fact(name="credit_card.eligible", value=True, certainty=0.90, domain="credit", source="inferred"),
            Fact(name="credit_card.tier", value="Upper-Mid Lifestyle", certainty=0.90, domain="credit", source="inferred"),
            Fact(
                name="credit_card.headline",
                value="Eligible — Upper-Mid Lifestyle Tier (Air Lounge & Utility Perks)",
                certainty=0.90,
                domain="credit",
                source="inferred",
                explanation="Strong credit history qualifies for premium travel and accelerated lifestyle reward cards."
            ),
            Fact(name="credit_card.products", value=cards, certainty=0.90, domain="credit", source="inferred")
        ]

    rules.append(Rule(
        rule_id="RULE_CARD_03_UPPER_MID_TIER",
        domain="credit",
        description="Upper-Mid Tier: CIBIL >= 730 and Monthly Income >= ₹75,000.",
        priority=220,
        conditions=[cond_upper_mid],
        action=act_upper_mid,
        cf_rule=0.90,
        condition_descriptions=["CIBIL Score >= 730", "Monthly Income >= ₹75,000"],
        consequence_fact_names=["credit_card.eligible", "credit_card.tier", "credit_card.headline", "credit_card.products"]
    ))

    # --------------------------------------------------------------------------
    # RULE 4: Mid & Entry Tier
    # --------------------------------------------------------------------------
    def cond_mid_tier(wm: WorkingMemory) -> bool:
        if wm.get_value("credit_card.eligible") is False or wm.has_fact("credit_card.tier"):
            return False
        score = int(wm.get_value("user.credit_score", 0))
        income = float(wm.get_value("user.monthly_income", 0.0))
        return score >= 650 and income >= 15000

    def act_mid_tier(wm: WorkingMemory, r: Rule) -> list[Fact]:
        spend_cat = wm.get_value("user.preferred_spend_category", "General")
        cards = list(CREDIT_CARD_CATALOG["mid"])

        # Prioritize cashback card for shopping
        if "Shopping" in spend_cat:
            cards.sort(key=lambda c: "Amazon" in c.name or "Millennia" in c.name, reverse=True)

        return [
            Fact(name="credit_card.eligible", value=True, certainty=0.85, domain="credit", source="inferred"),
            Fact(name="credit_card.tier", value="Digital Cashback & Shopping", certainty=0.85, domain="credit", source="inferred"),
            Fact(
                name="credit_card.headline",
                value="Eligible — Digital Cashback & Daily Spends Tier",
                certainty=0.85,
                domain="credit",
                source="inferred",
                explanation=f"Optimized for high-yield cashback on e-commerce, dining, and utility transactions aligned with '{spend_cat}'."
            ),
            Fact(name="credit_card.products", value=cards, certainty=0.85, domain="credit", source="inferred")
        ]

    rules.append(Rule(
        rule_id="RULE_CARD_04_MID_CASHBACK_TIER",
        domain="credit",
        description="Mid / Digital Spends Tier: CIBIL >= 650 with income >= ₹15,000, optimized for cashback.",
        priority=200,
        conditions=[cond_mid_tier],
        action=act_mid_tier,
        cf_rule=0.85,
        condition_descriptions=["CIBIL Score >= 650", "Monthly Income >= ₹15,000"],
        consequence_fact_names=["credit_card.eligible", "credit_card.tier", "credit_card.headline", "credit_card.products"]
    ))

    return rules
