"""
Investment Knowledge Base — Scored Risk Profiler & Strategic Asset Allocation.
Implements non-ML instant cold-start risk categorization, SEBI asset allocation glide paths,
equity/debt/gold splits, and Indian Income Tax (80C / 80CCD) optimizations.
"""

from __future__ import annotations

from core.facts import Fact, WorkingMemory
from core.rules import Remedy, Rule
from data.catalog import INVESTMENT_CATALOG


def _remedy_tax_tip(wm: WorkingMemory) -> list[Remedy]:
    income = float(wm.get_value("user.monthly_income", 0.0))
    return [
        Remedy(
            text="The NPS 80CCD(1B) tip is shown when the financial goal is 'Tax Saving'.",
            changes={"user.financial_goal": "Tax Saving"}
        ),
        Remedy(
            text=f"It is also shown at monthly income of ₹75,000 or more (income is ₹{income:,.0f} now).",
            changes={"user.monthly_income": 75000.0},
            alternative=True
        ),
    ]


def build_investment_rules() -> list[Rule]:
    """Generates production rules for the Investment Advisory Domain."""
    rules: list[Rule] = []

    # --------------------------------------------------------------------------
    # RULE 1: Core Scored Risk Profiling Engine
    # --------------------------------------------------------------------------
    def cond_profile_risk(wm: WorkingMemory) -> bool:
        return not wm.has_fact("investment.risk_category")

    def act_profile_risk(wm: WorkingMemory, r: Rule) -> list[Fact]:
        risk_tol = wm.get_value("user.risk_tolerance", "Medium")
        age = int(wm.get_value("user.age", 30))
        goal = wm.get_value("user.financial_goal", "Wealth Creation")

        # 1. Base Score
        base_scores = {"Low": 1.0, "Medium": 2.0, "High": 3.0}
        score = base_scores.get(risk_tol, 2.0)

        # 2. Age Horizon Adjustment (SEBI glide path)
        if age < 30:
            age_adj = 1.0
        elif age <= 45:
            age_adj = 0.5
        elif age <= 60:
            age_adj = 0.0
        else:
            age_adj = -1.0
        score += age_adj

        # 3. Goal Adjustment
        if goal == "Wealth Creation":
            goal_adj = 0.5
        elif goal == "Emergency Fund":
            goal_adj = -1.0
        elif goal == "Debt Free":
            goal_adj = -0.5      # paying down debt first: keep investing conservative
        elif goal == "Retirement Planning" and age > 50:
            goal_adj = -0.5
        else:
            goal_adj = 0.0
        score += goal_adj

        # Categorize
        if score <= 1.5:
            category = "Conservative"
            allocation = {"Equity": 20, "Debt / Fixed Income": 70, "Gold / Commodities": 10}
            products = INVESTMENT_CATALOG["conservative"]
            cf = 0.90
            headline = "Conservative Wealth Preservation (20% Equity / 70% Debt / 10% Gold)"
        elif score <= 2.5:
            category = "Moderate"
            allocation = {"Equity": 50, "Debt / Fixed Income": 40, "Gold / Commodities": 10}
            products = INVESTMENT_CATALOG["moderate"]
            cf = 0.85
            headline = "Moderate Balanced Growth (50% Equity / 40% Debt / 10% Gold)"
        else:
            category = "Aggressive"
            allocation = {"Equity": 75, "Debt / Fixed Income": 15, "Gold / Commodities": 10}
            products = INVESTMENT_CATALOG["aggressive"]
            cf = 0.90
            headline = "Aggressive Long-Term Compounding (75% Equity / 15% Debt / 10% Gold)"

        explanation = (
            f"Risk Index {score:.1f}/4.0 calculated from Base ({risk_tol}) "
            f"+ Age Offset ({age_adj:+.1f} for age {age}) "
            f"+ Milestone Offset ({goal_adj:+.1f} for '{goal}')."
        )

        return [
            Fact(name="investment.eligible", value=True, certainty=cf, domain="investment", source="inferred"),
            Fact(name="investment.risk_score", value=round(score, 2), certainty=cf, domain="investment", source="inferred"),
            Fact(name="investment.risk_category", value=category, certainty=cf, domain="investment", source="inferred"),
            Fact(name="investment.allocation", value=allocation, certainty=cf, domain="investment", source="inferred"),
            Fact(name="investment.headline", value=headline, certainty=cf, domain="investment", source="inferred"),
            Fact(name="investment.products", value=products, certainty=cf, domain="investment", source="inferred"),
            Fact(name="investment.explanation", value=explanation, certainty=cf, domain="investment", source="inferred")
        ]

    rules.append(Rule(
        rule_id="RULE_INV_01_SCORED_RISK_PROFILER",
        domain="investment",
        description="Cold-Start Scored Risk Profiler: Computes risk tolerance and macro allocation without requiring 80k historical records.",
        priority=200,
        conditions=[cond_profile_risk],
        action=act_profile_risk,
        cf_rule=0.90,
        condition_descriptions=["User profile inputs present (Risk Tolerance, Age, Financial Goal)"],
        consequence_fact_names=[
            "investment.eligible", "investment.risk_category", "investment.allocation",
            "investment.headline", "investment.products", "investment.explanation"
        ]
    ))

    # --------------------------------------------------------------------------
    # RULE 2: Tax Optimization Advisory (Section 80CCD(1B) NPS Benefit)
    # --------------------------------------------------------------------------
    def cond_tax_optimization(wm: WorkingMemory) -> bool:
        goal = wm.get_value("user.financial_goal", "")
        income = float(wm.get_value("user.monthly_income", 0.0))
        return (goal == "Tax Saving" or income >= 75000) and not wm.has_fact("investment.tax_tip")

    def act_tax_optimization(wm: WorkingMemory, r: Rule) -> list[Fact]:
        return [
            Fact(
                name="investment.tax_tip",
                value="Deploy ₹50,000 in NPS Tier-I to claim exclusive Sec 80CCD(1B) tax deduction beyond Section 80C ceiling.",
                certainty=0.95,
                domain="investment",
                source="inferred",
                explanation="Applicable for Indian Old Tax Regime taxpayers to reduce taxable slab liability."
            )
        ]

    rules.append(Rule(
        rule_id="RULE_INV_02_TAX_OPTIMIZATION_NPS",
        domain="investment",
        description="Section 80CCD(1B) Tax Shield: Suggests NPS additional ₹50k deduction for high earners or tax-focused goals.",
        priority=180,
        conditions=[cond_tax_optimization],
        action=act_tax_optimization,
        cf_rule=0.95,
        condition_descriptions=["Goal == 'Tax Saving' OR Monthly Income >= ₹75,000"],
        consequence_fact_names=["investment.tax_tip"],
        remedy=_remedy_tax_tip
    ))

    return rules
