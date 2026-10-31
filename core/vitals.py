"""
Presentation-ready vitals derived from one AdvisoryExecutionResult.

The web UI renders these instead of recomputing FHI, loan limits or life cover in
JavaScript, so the dashboard, the rule trace, the PDF dossier and the REST API always
agree: every number here is read from the inference result or from one shared formula.
"""

from __future__ import annotations

from typing import Any

FOIR_SAFE_PCT = 35.0
FOIR_LIMIT_PCT = 50.0
RESERVE_MONTHS = 6
# Monthly expenses are not collected, so the reserve target assumes 65% of income
# (never below a Rs 15,000 floor). It is a planning target, not a measured runway.
EXPENSE_RATIO = 0.65
EXPENSE_FLOOR = 15000.0


def foir_pct(income: float, emis: float) -> float:
    return (emis / income) * 100.0 if income > 0 else 100.0


def stress_scenario(income: float, emis: float, rate_hike_bps: float, income_drop_pct: float) -> dict[str, Any]:
    """Macro shock on cashflow. Single implementation behind /api/stress-test."""
    stressed_income = max(1.0, income * (1.0 - income_drop_pct / 100.0))
    emi_multiplier = 1.0 + (rate_hike_bps / 10000.0) * 4.0   # ~4-year average remaining tenor
    stressed_emis = emis * emi_multiplier
    stressed_foir = stressed_emis / stressed_income
    return {
        "stressed_income": round(stressed_income, 2),
        "stressed_emis": round(stressed_emis, 2),
        "stressed_foir": round(stressed_foir * 100, 2),
        "leftover_cashflow": round(max(0.0, stressed_income - stressed_emis), 2),
        "emi_multiplier": round(emi_multiplier, 4),
        "insolvent": stressed_foir > FOIR_LIMIT_PCT / 100.0,
    }


def _foir_status(pct: float) -> str:
    if pct <= FOIR_SAFE_PCT:
        return "safe"
    if pct <= FOIR_LIMIT_PCT:
        return "moderate"
    return "critical"


def _summary(tier_badge: str, foir: float, overrides: list) -> dict[str, str]:
    if tier_badge.startswith("OPTIMAL"):
        return {"headline": "Strong Financial Health",
                "body": f"Debt takes {foir:.1f}% of income and the rule base found no protective ceilings to apply."}
    if tier_badge.startswith("STABLE"):
        return {"headline": "Stable, Ready to Grow",
                "body": "Liabilities are manageable. The next gains are in liquid reserves and long-term allocation."}
    if tier_badge.startswith("VULNERABLE"):
        return {"headline": "Action Needed",
                "body": f"Debt takes {foir:.1f}% of income"
                        + (" and a protective ceiling is limiting the score." if overrides else ".")
                        + " Address the flagged items before taking on new credit."}
    return {"headline": "High Risk",
            "body": "Debt, credit standing or income status is severely limiting the score. "
                    "Reducing liabilities comes before any new borrowing."}


def build_vitals(result) -> dict[str, Any]:
    """Assemble the dashboard payload from an AdvisoryExecutionResult."""
    p = result.profile
    income = float(p["monthly_income"])
    emis = float(p["existing_emis"])
    fhi = result.fhi
    loan = result.domains["loan"]
    ins = result.domains["insurance"]
    foir = foir_pct(income, emis)

    # Borrowing power: exactly what the loan rules concluded.
    if loan.eligible:
        borrowing = {
            "state": "eligible",
            "max_amount": loan.details.get("max_amount", 0.0),
            "interest_rate": loan.details.get("interest_rate"),
            "note": loan.headline,
        }
    else:
        borrowing = {"state": "not_eligible", "max_amount": 0.0, "interest_rate": None, "note": loan.headline}

    # Life cover: only if the HLV rule fired (it requires dependents).
    term_cover = float(ins.details.get("term_cover") or 0.0)
    cover = {
        "recommended": term_cover > 0,
        "amount": term_cover,
        "annual_income_multiple": round(term_cover / (income * 12), 1) if term_cover > 0 and income > 0 else None,
    }

    monthly_cost = max(EXPENSE_FLOOR, income * EXPENSE_RATIO)
    return {
        "foir": {"pct": round(foir, 1), "status": _foir_status(foir), "limit_pct": FOIR_LIMIT_PCT},
        "borrowing": borrowing,
        "life_cover": cover,
        "emergency_reserve": {
            "months": RESERVE_MONTHS,
            "target_amount": round(monthly_cost * RESERVE_MONTHS, 2),
            "assumed_monthly_expenses": round(monthly_cost, 2),
            "is_estimate": True,
        },
        "fhi": {
            "score": fhi.composite_score,
            "tier": fhi.tier_badge,
            "overrides": fhi.active_overrides,
        },
        "summary": _summary(fhi.tier_badge, foir, fhi.active_overrides),
    }
