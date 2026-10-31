"""
Financial Health Index (FHI) Composite Scoring Engine.
Implements a two-layer normalized ensemble with protective override ceilings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FinancialHealthBreakdown:
    """Detailed multi-attribute scoring analysis."""
    composite_score: float         # 0 to 100 scale
    unclamped_raw_score: float     # Before protective override ceilings
    solvency_score: float          # 0 to 100 (FOIR / debt capacity)
    coverage_score: float          # 0 to 100 (Insurance protection)
    liquidity_score: float         # 0 to 100 (Emergency buffer)
    credit_score_normalized: float # 0 to 100 (CIBIL rating)
    tier_badge: str                # OPTIMAL | STABLE | VULNERABLE | DISTRESSED
    active_overrides: list[str]    # Protective floors that triggered clamping
    radar_metrics: dict[str, float]# Normalized axes for spider/radar chart


class FinancialHealthScorer:
    """Calculates composite financial health and applies protective ceilings."""

    WEIGHT_SOLVENCY = 0.30
    WEIGHT_COVERAGE = 0.25
    WEIGHT_LIQUIDITY = 0.25
    WEIGHT_CREDIT = 0.20

    @classmethod
    def evaluate(cls, profile_data: dict[str, Any], module_verdicts: dict[str, Any]) -> FinancialHealthBreakdown:
        income = float(profile_data.get("monthly_income", 0.0))
        emis = float(profile_data.get("existing_emis", 0.0))
        credit_score = int(profile_data.get("credit_score", 650))
        dependents = int(profile_data.get("dependents", 0))
        employment = str(profile_data.get("employment_type", "Salaried"))

        # 1. Solvency Score (Debt-to-Income / FOIR)
        foir = (emis / income) if income > 0 else 1.0
        if foir <= 0.15:
            solvency = 100.0
        elif foir <= 0.30:
            solvency = 85.0
        elif foir <= 0.45:
            solvency = 65.0
        elif foir <= 0.55:
            solvency = 40.0
        else:
            solvency = 15.0

        # 2. Coverage Score (Insurance sufficiency)
        insurance_data = module_verdicts.get("insurance", {})
        has_term = insurance_data.get("eligible", False) and "Term Life" in insurance_data.get("headline", "")
        has_health = insurance_data.get("eligible", False) and "Health" in insurance_data.get("headline", "")

        if has_term and has_health:
            coverage = 95.0
        elif has_health and dependents == 0:
            coverage = 85.0
        elif has_health:
            coverage = 60.0
        elif has_term:
            coverage = 50.0
        else:
            coverage = 20.0

        # 3. Liquidity & Emergency Buffer
        disposable_income = max(0.0, income - emis)
        savings_rate = (disposable_income / income) if income > 0 else 0.0
        if savings_rate >= 0.50:
            liquidity = 95.0
        elif savings_rate >= 0.35:
            liquidity = 80.0
        elif savings_rate >= 0.20:
            liquidity = 65.0
        elif savings_rate >= 0.10:
            liquidity = 45.0
        else:
            liquidity = 20.0

        # 4. Credit Discipline Score (Normalized from 300-900 CIBIL)
        if credit_score >= 780:
            credit_norm = 100.0
        elif credit_score >= 730:
            credit_norm = 85.0
        elif credit_score >= 680:
            credit_norm = 65.0
        elif credit_score >= 620:
            credit_norm = 45.0
        else:
            credit_norm = 20.0

        # Raw Weighted Ensemble
        raw_score = (
            solvency * cls.WEIGHT_SOLVENCY +
            coverage * cls.WEIGHT_COVERAGE +
            liquidity * cls.WEIGHT_LIQUIDITY +
            credit_norm * cls.WEIGHT_CREDIT
        )

        # 5. Protective Override Ceilings (Defensive Clamping)
        active_overrides: list[str] = []
        final_score = raw_score

        # Floor 1: Severe Debt Burden (FOIR > 55%)
        if foir > 0.55:
            if final_score > 45.0:
                final_score = 45.0
            active_overrides.append("CRITICAL_DEBT_BURDEN_CEILING (FOIR > 55% clamps FHI to <= 45)")

        # Floor 2: Poor Credit Standing (CIBIL < 620)
        if credit_score < 620:
            if final_score > 40.0:
                final_score = 40.0
            active_overrides.append("SUBPRIME_CREDIT_CEILING (CIBIL < 620 clamps FHI to <= 40)")

        # Floor 3: Family Protection Void (Dependents > 0 and no term life)
        if dependents > 0 and not has_term:
            if final_score > 55.0:
                final_score = 55.0
            active_overrides.append("UNPROTECTED_FAMILY_CEILING (Dependents with 0 life insurance clamps FHI to <= 55)")

        # Floor 4: Student or Unemployed status
        if employment in {"Student", "Unemployed"}:
            if final_score > 35.0:
                final_score = 35.0
            active_overrides.append("INCOME_DEPENDENCE_CEILING (Non-earning status clamps FHI to <= 35)")

        final_score = round(max(0.0, min(100.0, final_score)), 1)

        # Risk Tier Classification
        if final_score >= 80.0:
            tier_badge = "OPTIMAL / RESILIENT"
        elif final_score >= 60.0:
            tier_badge = "STABLE / GROWTH READY"
        elif final_score >= 40.0:
            tier_badge = "VULNERABLE / ACTION NEEDED"
        else:
            tier_badge = "DISTRESSED / HIGH RISK"

        radar_metrics = {
            "Solvency & Debt Control": solvency,
            "Protection & Insurance": coverage,
            "Cashflow & Liquidity": liquidity,
            "Credit Standing": credit_norm
        }

        return FinancialHealthBreakdown(
            composite_score=final_score,
            unclamped_raw_score=round(raw_score, 1),
            solvency_score=solvency,
            coverage_score=coverage,
            liquidity_score=liquidity,
            credit_score_normalized=credit_norm,
            tier_badge=tier_badge,
            active_overrides=active_overrides,
            radar_metrics=radar_metrics
        )
