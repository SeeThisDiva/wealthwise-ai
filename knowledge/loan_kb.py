"""
Loan Knowledge Base — Production Rules for Lending & Debt Capacity.
Implements RBI statutory FOIR ceilings, reverse-EMI sizing, credit score banding,
and secured fallbacks.
"""

from __future__ import annotations

import math

from core.facts import Fact, WorkingMemory
from core.rules import Remedy, Rule
from data.catalog import LOAN_CATALOG

LOAN_OUTPUTS = ["loan.eligible", "loan.rejection_reason", "loan.products"]


def _foir_ceiling(wm: WorkingMemory) -> float:
    return 0.50 if wm.get_value("user.employment_type", "Salaried") == "Salaried" else 0.45


def _remedy_non_earning(wm: WorkingMemory) -> list[Remedy]:
    emp = wm.get_value("user.employment_type", "")
    return [Remedy(
        text=f"Unsecured credit needs a verifiable regular income, and '{emp}' does not qualify. "
             f"Salaried or self-employed income is required first.",
        changes={"user.employment_type": "Salaried"}
    )]


def _remedy_age(wm: WorkingMemory) -> list[Remedy]:
    age = int(wm.get_value("user.age", 30))
    emp = wm.get_value("user.employment_type", "Salaried")
    hi = 60 if emp == "Salaried" else 65
    return [Remedy(
        text=f"Age {age} is outside the 21-{hi} underwriting window for {emp} applicants. "
             f"This cannot be changed; a co-applicant inside the window or a secured loan is the usual route.",
        fixable=False
    )]


def _remedy_min_income(wm: WorkingMemory) -> list[Remedy]:
    income = float(wm.get_value("user.monthly_income", 0.0))
    emp = wm.get_value("user.employment_type", "Salaried")
    threshold = 15000 if emp == "Salaried" else 20000
    return [Remedy(
        text=f"Raise verifiable monthly income from ₹{income:,.0f} to at least ₹{threshold:,.0f} "
             f"(minimum for {emp} applicants).",
        changes={"user.monthly_income": float(threshold)}
    )]


def _remedy_credit_score(wm: WorkingMemory) -> list[Remedy]:
    score = int(wm.get_value("user.credit_score", 650))
    return [Remedy(
        text=f"Improve the CIBIL credit score by +{650 - score} points (from {score} to at least 650) "
             f"by clearing overdue payments and keeping utilisation low; an FD-backed secured card helps rebuild it.",
        changes={"user.credit_score": 650}
    )]


def _remedy_capacity(wm: WorkingMemory) -> list[Remedy]:
    income = float(wm.get_value("user.monthly_income", 0.0))
    emis = float(wm.get_value("user.existing_emis", 0.0))
    ceiling = _foir_ceiling(wm)
    foir = (emis / income) if income > 0 else 1.0
    # RULE_LOAN_05 needs (income * ceiling) - emis > 500
    max_emis = max(0.0, math.floor(income * ceiling - 501))
    cut = max(0.0, emis - max_emis)
    income_needed = math.ceil((emis + 501) / ceiling)
    return [
        Remedy(
            text=f"Existing EMIs of ₹{emis:,.0f} are {foir * 100:.1f}% of income, leaving under ₹500/month of "
                 f"room below the {int(ceiling * 100)}% FOIR ceiling. Pay off or consolidate loans to cut EMIs "
                 f"by at least ₹{cut:,.0f}/month (to ₹{max_emis:,.0f} or less).",
            changes={"user.existing_emis": max_emis}
        ),
        Remedy(
            text=f"Alternatively, raise verifiable household income to about ₹{income_needed:,.0f}/month "
                 f"(for example with a co-borrower).",
            changes={"user.monthly_income": float(income_needed)},
            alternative=True
        ),
    ]


def build_loan_rules() -> list[Rule]:
    """Generates the production rules for the Loan Advisory Domain."""
    rules: list[Rule] = []

    # --------------------------------------------------------------------------
    # RULE 1: Disqualification for non-earning status
    # --------------------------------------------------------------------------
    def cond_non_earning(wm: WorkingMemory) -> bool:
        emp = wm.get_value("user.employment_type", "")
        return emp in {"Student", "Unemployed"}

    def act_non_earning(wm: WorkingMemory, r: Rule) -> list[Fact]:
        return [
            Fact(
                name="loan.eligible",
                value=False,
                certainty=1.0,
                domain="loan",
                source="inferred",
                explanation="Statutory rejection: Applicant has no independent verifiable regular income source."
            ),
            Fact(
                name="loan.rejection_reason",
                value="Non-earning employment status (Student/Unemployed).",
                certainty=1.0,
                domain="loan",
                source="inferred"
            ),
            Fact(
                name="loan.products",
                value=LOAN_CATALOG["secured_fallback"],
                certainty=0.85,
                domain="loan",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_LOAN_01_NON_EARNING_DISQUALIFICATION",
        domain="loan",
        description="RBI Regulatory Guardrail: Students and Unemployed individuals cannot be extended unsecured debt.",
        priority=300,
        conditions=[cond_non_earning],
        action=act_non_earning,
        cf_rule=1.0,
        condition_descriptions=["Employment type must be Salaried, Self-Employed, or Business Owner"],
        consequence_fact_names=["loan.eligible", "loan.rejection_reason", "loan.products"],
        produces={"loan.eligible": False},
        remedy=_remedy_non_earning
    ))

    # --------------------------------------------------------------------------
    # RULE 2: Age Gatekeeper
    # --------------------------------------------------------------------------
    def cond_age_invalid(wm: WorkingMemory) -> bool:
        age = int(wm.get_value("user.age", 30))
        emp = wm.get_value("user.employment_type", "Salaried")
        if emp == "Salaried" and (age < 21 or age > 60):
            return True
        if emp in {"Self-Employed", "Business Owner"} and (age < 21 or age > 65):
            return True
        return False

    def act_age_invalid(wm: WorkingMemory, r: Rule) -> list[Fact]:
        age = wm.get_value("user.age")
        return [
            Fact(
                name="loan.eligible",
                value=False,
                certainty=1.0,
                domain="loan",
                source="inferred",
                explanation=f"Age criterion failure: Applicant age ({age}) outside statutory lending bracket."
            ),
            Fact(
                name="loan.rejection_reason",
                value="Applicant age must be 21–60 (Salaried) or 21–65 (Business).",
                certainty=1.0,
                domain="loan",
                source="inferred"
            ),
            Fact(
                name="loan.products",
                value=LOAN_CATALOG["secured_fallback"],
                certainty=0.80,
                domain="loan",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_LOAN_02_AGE_GATEKEEPER",
        domain="loan",
        description="Institutional Underwriting Gate: Age must be 21-60 for salaried or 21-65 for self-employed.",
        priority=290,
        conditions=[cond_age_invalid],
        action=act_age_invalid,
        cf_rule=1.0,
        condition_descriptions=["Age between 21 and 60 (Salaried) or 21 and 65 (Self-Employed)"],
        consequence_fact_names=["loan.eligible", "loan.rejection_reason", "loan.products"],
        produces={"loan.eligible": False},
        remedy=_remedy_age
    ))

    # --------------------------------------------------------------------------
    # RULE 3: Minimum Income Gatekeeper
    # --------------------------------------------------------------------------
    def cond_low_income(wm: WorkingMemory) -> bool:
        if wm.get_value("loan.eligible") is False:
            return False
        income = float(wm.get_value("user.monthly_income", 0.0))
        emp = wm.get_value("user.employment_type", "Salaried")
        threshold = 15000 if emp == "Salaried" else 20000
        return income < threshold

    def act_low_income(wm: WorkingMemory, r: Rule) -> list[Fact]:
        income = wm.get_value("user.monthly_income")
        return [
            Fact(
                name="loan.eligible",
                value=False,
                certainty=1.0,
                domain="loan",
                source="inferred",
                explanation=f"Income requirement unmet: Monthly income ₹{income:,.0f} below baseline cutoff."
            ),
            Fact(
                name="loan.rejection_reason",
                value="Monthly income below minimum institutional threshold (₹15,000 salaried / ₹20,000 business).",
                certainty=1.0,
                domain="loan",
                source="inferred"
            ),
            Fact(
                name="loan.products",
                value=LOAN_CATALOG["secured_fallback"],
                certainty=0.80,
                domain="loan",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_LOAN_03_MIN_INCOME_GATE",
        domain="loan",
        description="Minimum Verifiable Income Gate: ₹15,000 for salaried or ₹20,000 for self-employed.",
        priority=280,
        conditions=[cond_low_income],
        action=act_low_income,
        cf_rule=1.0,
        condition_descriptions=["Monthly income >= ₹15,000 (salaried) or >= ₹20,000 (self-employed)"],
        consequence_fact_names=["loan.eligible", "loan.rejection_reason", "loan.products"],
        produces={"loan.eligible": False},
        remedy=_remedy_min_income
    ))

    # --------------------------------------------------------------------------
    # RULE 4: Severe Subprime Credit Score (< 650)
    # --------------------------------------------------------------------------
    def cond_subprime_credit(wm: WorkingMemory) -> bool:
        if wm.get_value("loan.eligible") is False:
            return False
        credit_score = int(wm.get_value("user.credit_score", 650))
        return credit_score < 650

    def act_subprime_credit(wm: WorkingMemory, r: Rule) -> list[Fact]:
        credit_score = wm.get_value("user.credit_score")
        return [
            Fact(
                name="loan.eligible",
                value=False,
                certainty=0.95,
                domain="loan",
                source="inferred",
                explanation=f"Credit history impairment: CIBIL score ({credit_score}) below 650 minimum threshold."
            ),
            Fact(
                name="loan.rejection_reason",
                value=f"CIBIL score ({credit_score}) indicates past default/delinquency risk.",
                certainty=0.95,
                domain="loan",
                source="inferred"
            ),
            Fact(
                name="loan.products",
                value=LOAN_CATALOG["secured_fallback"],
                certainty=0.90,
                domain="loan",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_LOAN_04_SUBPRIME_CREDIT_DISQUALIFIER",
        domain="loan",
        description="CIBIL Impairment Gate: Credit score < 650 fails underwriting, routes to secured asset lending.",
        priority=270,
        conditions=[cond_subprime_credit],
        action=act_subprime_credit,
        cf_rule=0.95,
        condition_descriptions=["CIBIL Credit Score >= 650"],
        consequence_fact_names=["loan.eligible", "loan.rejection_reason", "loan.products"],
        produces={"loan.eligible": False},
        remedy=_remedy_credit_score
    ))

    # --------------------------------------------------------------------------
    # RULE 5: Primary Affordability & Reverse-EMI Sizing Engine
    # --------------------------------------------------------------------------
    def cond_eligible_for_sizing(wm: WorkingMemory) -> bool:
        if wm.get_value("loan.eligible") is False:
            return False
        score = int(wm.get_value("user.credit_score", 0))
        income = float(wm.get_value("user.monthly_income", 0.0))
        emis = float(wm.get_value("user.existing_emis", 0.0))
        emp = wm.get_value("user.employment_type", "Salaried")

        foir_ceiling = 0.50 if emp == "Salaried" else 0.45
        capacity = (income * foir_ceiling) - emis
        return score >= 650 and capacity > 500

    def act_size_loan(wm: WorkingMemory, r: Rule) -> list[Fact]:
        score = int(wm.get_value("user.credit_score", 700))
        income = float(wm.get_value("user.monthly_income", 50000))
        emis = float(wm.get_value("user.existing_emis", 0.0))
        dependents = int(wm.get_value("user.dependents", 0))
        emp = wm.get_value("user.employment_type", "Salaried")

        foir_ceiling = 0.50 if emp == "Salaried" else 0.45
        emi_capacity = (income * foir_ceiling) - emis

        # Determine tier and interest rate
        if score >= 750:
            tier = "excellent"
            annual_rate = 0.1099
            rate_str = "10.99% p.a. (Prime Tier 1)"
            cf = 0.95
            products = LOAN_CATALOG["excellent"]
        elif score >= 700:
            tier = "good"
            annual_rate = 0.1299
            rate_str = "12.99% p.a. (Standard Tier 2)"
            cf = 0.85
            products = LOAN_CATALOG["good"]
        else:
            tier = "fair"
            annual_rate = 0.1599
            rate_str = "15.99% p.a. (Emerging Tier 3)"
            cf = 0.70
            products = LOAN_CATALOG["fair"]

        # Reverse EMI formula for n = 60 months tenure
        n = 60
        r_monthly = annual_rate / 12.0
        # P = EMI * [ (1+r)^n - 1 ] / [ r * (1+r)^n ]
        comp = (1.0 + r_monthly) ** n
        principal = emi_capacity * (comp - 1.0) / (r_monthly * comp)

        # Apply 10% safety buffer if 3+ dependents
        if dependents >= 3:
            principal *= 0.90

        max_loan = round(principal / 1000.0) * 1000.0  # Round to nearest thousand

        return [
            Fact(name="loan.eligible", value=True, certainty=cf, domain="loan", source="inferred"),
            Fact(name="loan.tier", value=tier, certainty=cf, domain="loan", source="inferred"),
            Fact(name="loan.interest_rate", value=rate_str, certainty=cf, domain="loan", source="inferred"),
            Fact(name="loan.emi_capacity", value=round(emi_capacity, 2), certainty=cf, domain="loan", source="inferred"),
            Fact(name="loan.max_amount", value=max_loan, certainty=cf, domain="loan", source="inferred"),
            Fact(name="loan.products", value=products, certainty=cf, domain="loan", source="inferred"),
            Fact(
                name="loan.headline",
                value=f"Eligible — Personal Loan up to ₹{max_loan:,.0f} @ {rate_str}",
                certainty=cf,
                domain="loan",
                source="inferred",
                explanation=f"Approved under FOIR {int(foir_ceiling*100)}% ceiling with monthly EMI capacity of ₹{emi_capacity:,.0f} over 60-month tenure."
            )
        ]

    rules.append(Rule(
        rule_id="RULE_LOAN_05_AFFORDABILITY_SIZING",
        domain="loan",
        description="Core Underwriting Engine: Calculates max loan capacity via reverse-EMI formula across 60-month tenure.",
        priority=200,
        conditions=[cond_eligible_for_sizing],
        action=act_size_loan,
        cf_rule=0.95,
        condition_descriptions=[
            "CIBIL Score >= 650",
            "Available monthly debt capacity (after FOIR obligations) > ₹500"
        ],
        consequence_fact_names=[
            "loan.eligible", "loan.tier", "loan.interest_rate", "loan.max_amount",
            "loan.products", "loan.headline", "loan.emi_capacity"
        ],
        produces={"loan.eligible": True},
        remedy=_remedy_capacity
    ))

    return rules
