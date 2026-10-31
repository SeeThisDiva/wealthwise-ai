"""
Master Advisory Orchestrator & Knowledge Integration Engine.
Coordinates Working Memory intake, rule registration, forward chaining inference,
composite health scoring, and SHA-256 fingerprinting.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from core.engine import InferenceEngine
from core.facts import Fact, WorkingMemory
from core.rules import RuleFiringTrace
from core.scoring import FinancialHealthBreakdown, FinancialHealthScorer
from core.security import (
    ALLOWED_EMPLOYMENT,
    ALLOWED_GOALS,
    ALLOWED_RISK,
    EvidenceFingerprint,
    SecureUserProfileInput,
)
from data.catalog import Product
from knowledge.credit_kb import build_credit_rules
from knowledge.insurance_kb import build_insurance_rules
from knowledge.investment_kb import build_investment_rules
from knowledge.loan_kb import build_loan_rules


@dataclass
class DomainRecommendation:
    module: str
    eligible: bool
    headline: str
    certainty: float
    confidence_label: str
    details: dict[str, Any]
    products: list[Product]
    rule_traces: list[str]


@dataclass
class AdvisoryExecutionResult:
    profile: dict[str, Any]
    fhi: FinancialHealthBreakdown
    domains: dict[str, DomainRecommendation]
    firing_history: list[RuleFiringTrace]
    audit_record: dict[str, Any]
    working_memory_snapshot: dict[str, Any]


class WealthExpertAdvisor:
    """Flagship Neuro-Symbolic Advisory System Orchestrator."""

    def __init__(self):
        self.engine = InferenceEngine()
        self._load_all_knowledge_bases()
        self.engine.counterfactual_space = {
            "user.risk_tolerance": list(ALLOWED_RISK),
            "user.financial_goal": list(ALLOWED_GOALS),
            "user.employment_type": list(ALLOWED_EMPLOYMENT),
            "user.dependents": [0, 1, 2, 3],
        }
        # self.engine only records the most recent run (for seek_goal / CLI use);
        # every analyze() call reasons on its own private engine and working memory.
        self._lock = threading.Lock()

    def _load_all_knowledge_bases(self) -> None:
        """Loads and compiles production rule bases across all financial disciplines."""
        self.engine.register_rules(build_loan_rules())
        self.engine.register_rules(build_insurance_rules())
        self.engine.register_rules(build_investment_rules())
        self.engine.register_rules(build_credit_rules())

    def analyze(
        self,
        profile: SecureUserProfileInput,
        *,
        record_session: bool = True,
    ) -> AdvisoryExecutionResult:
        """
        Executes end-to-end symbolic reasoning over the intake profile:
        1. Populates Working Memory with verified facts.
        2. Executes Forward Chaining Match-Resolve-Act loop.
        3. Computes two-layer composite Financial Health Index (FHI).
        4. Calculates the SHA-256 fingerprint of the profile and results.
        """
        # 1. Initialize a private Working Memory and engine for this request. The rule base is
        # shared read-only, so concurrent requests cannot see each other's facts.
        wm = WorkingMemory()
        engine = self._new_engine(wm)

        # Assert initial facts from profile
        profile_dict = profile.model_dump()
        for key, val in profile_dict.items():
            wm.assert_fact(Fact(
                name=f"user.{key}",
                value=val,
                certainty=1.0,
                domain="profile",
                source="initial",
                explanation=f"Direct client assertion: {key} = {val}"
            ))

        # 2. Run Forward Chaining
        firing_history = engine.forward_chain(max_cycles=50)

        if record_session:
            with self._lock:
                self.engine.wm = wm
                self.engine.firing_history = firing_history

        # 3. Extract Domain Verdicts
        # 3.1 Loan
        loan_eligible = wm.get_value("loan.eligible", False)
        loan_cf = wm.get_certainty("loan.eligible", 0.0)
        loan_headline = wm.get_value("loan.headline", "Loan Eligibility Evaluation Complete")
        if not loan_eligible and wm.has_fact("loan.rejection_reason"):
            loan_headline = f"Unsecured Loan Not Recommended: {wm.get_value('loan.rejection_reason')}"
        loan_products = wm.get_value("loan.products", [])
        loan_traces = [t.description for t in firing_history if t.domain == "loan"]

        loan_rec = DomainRecommendation(
            module="Loan & Debt Capacity",
            eligible=loan_eligible,
            headline=loan_headline,
            certainty=loan_cf,
            confidence_label=self._cf_label(loan_cf),
            details={
                "max_amount": wm.get_value("loan.max_amount", 0.0),
                "interest_rate": wm.get_value("loan.interest_rate", "N/A"),
                "emi_capacity": wm.get_value("loan.emi_capacity", 0.0),
                "tier": wm.get_value("loan.tier", "subprime")
            },
            products=loan_products,
            rule_traces=loan_traces
        )

        # 3.2 Insurance
        ins_eligible = wm.get_value("insurance.eligible", True)
        ins_cf = wm.get_certainty("insurance.eligible", 0.95)
        ins_headline = wm.get_value("insurance.headline", "Comprehensive Protection Recommended")
        ins_products = wm.get_value("insurance.products", [])
        ins_traces = [t.description for t in firing_history if t.domain == "insurance"]

        ins_rec = DomainRecommendation(
            module="Protection & Insurance",
            eligible=ins_eligible,
            headline=ins_headline,
            certainty=ins_cf,
            confidence_label=self._cf_label(ins_cf),
            details={
                "term_cover": wm.get_value("insurance.term_cover_amount", 0.0),
                "health_sum_insured": wm.get_value("insurance.health_sum_insured", 0.0),
                "has_child_plan": wm.get_value("insurance.child_edu_recommended", False)
            },
            products=ins_products,
            rule_traces=ins_traces
        )

        # 3.3 Investment
        inv_eligible = wm.get_value("investment.eligible", True)
        inv_cf = wm.get_certainty("investment.eligible", 0.90)
        inv_headline = wm.get_value("investment.headline", "Strategic Asset Allocation")
        inv_products = wm.get_value("investment.products", [])
        inv_traces = [t.description for t in firing_history if t.domain == "investment"]

        inv_rec = DomainRecommendation(
            module="Wealth & Asset Allocation",
            eligible=inv_eligible,
            headline=inv_headline,
            certainty=inv_cf,
            confidence_label=self._cf_label(inv_cf),
            details={
                "risk_category": wm.get_value("investment.risk_category", "Moderate"),
                "risk_score": wm.get_value("investment.risk_score", 2.0),
                "allocation": wm.get_value("investment.allocation", {}),
                "tax_tip": wm.get_value("investment.tax_tip", "")
            },
            products=inv_products,
            rule_traces=inv_traces
        )

        # 3.4 Credit Card
        card_eligible = wm.get_value("credit_card.eligible", False)
        card_cf = wm.get_certainty("credit_card.eligible", 0.85)
        card_headline = wm.get_value("credit_card.headline", "Credit Card Optimization")
        card_products = wm.get_value("credit_card.products", [])
        card_traces = [t.description for t in firing_history if t.domain == "credit"]

        card_rec = DomainRecommendation(
            module="Credit & Liquidity Cards",
            eligible=card_eligible,
            headline=card_headline,
            certainty=card_cf,
            confidence_label=self._cf_label(card_cf),
            details={
                "tier": wm.get_value("credit_card.tier", "General"),
                "preferred_category": profile.preferred_spend_category
            },
            products=card_products,
            rule_traces=card_traces
        )

        domains = {
            "loan": loan_rec,
            "insurance": ins_rec,
            "investment": inv_rec,
            "credit": card_rec
        }

        # 4. Multi-Attribute Financial Health Composite Scoring
        domains_summary = {
            "loan": {"eligible": loan_eligible, "headline": loan_headline},
            "insurance": {"eligible": ins_eligible, "headline": ins_headline},
            "investment": {"eligible": inv_eligible, "headline": inv_headline},
            "credit": {"eligible": card_eligible, "headline": card_headline}
        }
        fhi_breakdown = FinancialHealthScorer.evaluate(profile_dict, domains_summary)

        # 5. SHA-256 fingerprint of profile and results
        audit_record = EvidenceFingerprint.create_audit_record(
            profile_dict=profile_dict,
            results_summary={
                "fhi_composite_score": fhi_breakdown.composite_score,
                "tier": fhi_breakdown.tier_badge,
                "active_overrides": fhi_breakdown.active_overrides,
                "loan_verdict": loan_rec.headline,
                "insurance_verdict": ins_rec.headline,
                "investment_verdict": inv_rec.headline,
                "card_verdict": card_rec.headline
            }
        )

        return AdvisoryExecutionResult(
            profile=profile_dict,
            fhi=fhi_breakdown,
            domains=domains,
            firing_history=firing_history,
            audit_record=audit_record,
            working_memory_snapshot=wm.snapshot()
        )

    def _new_engine(self, wm: WorkingMemory) -> InferenceEngine:
        engine = InferenceEngine(wm)
        engine.rules = self.engine.rules
        engine.counterfactual_space = self.engine.counterfactual_space
        return engine

    def seek_goal_remediation(
        self,
        target_fact: str,
        desired_value: Any,
        profile: SecureUserProfileInput | None = None,
    ) -> dict[str, Any]:
        """
        Runs Backward Chaining counterfactual analysis for a target financial milestone.

        Pass `profile` to reason about a specific client (thread-safe). Without it the most
        recent analyze() result is used, which suits the single-user CLI.
        """
        if profile is not None:
            result = self.analyze(profile, record_session=False)
            wm = WorkingMemory()
            for _name, d in result.working_memory_snapshot.items():
                wm.assert_fact(Fact(**d))
            return self._new_engine(wm).backward_chain_goal(target_fact, desired_value)
        with self._lock:
            engine = self._new_engine(self.engine.wm)
        return engine.backward_chain_goal(target_fact, desired_value)

    @staticmethod
    def _cf_label(cf: float) -> str:
        if cf >= 0.85:
            return "High Confidence"
        elif cf >= 0.60:
            return "Strong Evidence"
        elif cf >= 0.30:
            return "Moderate Evidence"
        elif cf > 0.0:
            return "Weak Evidence"
        elif cf == 0.0:
            return "Neutral / Baseline"
        else:
            return "Counter-Indicated"
