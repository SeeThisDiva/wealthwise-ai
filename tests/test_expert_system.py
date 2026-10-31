"""
Automated Verification Test Suite for Financial Advisory Expert System.
Verifies Working Memory, MYCIN Certainty Factor calculus, Forward/Backward Chaining,
FHI composite scoring with protective override floors, security boundaries, and PDF generation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from advisor import WealthExpertAdvisor
from core.engine import InferenceEngine
from core.facts import Fact, WorkingMemory
from core.rules import Rule
from core.scoring import FinancialHealthScorer
from core.security import SecureUserProfileInput
from core.uncertainty import CertaintyFactorEngine
from reports.dossier_generator import FinancialDossierPDFGenerator


def test_working_memory_assertion_and_retract():
    wm = WorkingMemory()
    f1 = Fact(name="test.income", value=50000, certainty=0.9)
    wm.assert_fact(f1)

    assert wm.has_fact("test.income") is True
    assert wm.get_value("test.income") == 50000
    assert wm.get_certainty("test.income") == 0.9

    # Retraction
    assert wm.retract_fact("test.income") is True
    assert wm.has_fact("test.income") is False


def test_mycin_certainty_factor_combination():
    # Combining two positive evidences: CF = CF1 + CF2 * (1 - CF1)
    cf1 = 0.8
    cf2 = 0.6
    expected = 0.8 + 0.6 * (1.0 - 0.8) # 0.8 + 0.12 = 0.92
    combined = CertaintyFactorEngine.combine(cf1, cf2)
    assert abs(combined - expected) < 0.001

    # Combining opposite signs: (CF1 + CF2) / (1 - min(|CF1|, |CF2|))
    cf_pos = 0.7
    cf_neg = -0.3
    denom = 1.0 - min(0.7, 0.3) # 1 - 0.3 = 0.7
    expected_opp = (0.7 - 0.3) / denom # 0.4 / 0.7 = 0.5714
    assert abs(CertaintyFactorEngine.combine(cf_pos, cf_neg) - expected_opp) < 0.001


def test_forward_chaining_and_salience():
    wm = WorkingMemory()
    wm.assert_fact(Fact(name="user.age", value=25))
    engine = InferenceEngine(wm)

    # Low priority rule
    engine.register_rule(Rule(
        rule_id="RULE_LOW",
        domain="test",
        description="Low priority",
        priority=50,
        conditions=[lambda m: m.get_value("user.age") > 18],
        action=lambda m, r: [Fact(name="status.adult", value=True)],
        consequence_fact_names=["status.adult"]
    ))

    # High priority rule
    engine.register_rule(Rule(
        rule_id="RULE_HIGH",
        domain="test",
        description="High priority",
        priority=200,
        conditions=[lambda m: m.get_value("user.age") > 18],
        action=lambda m, r: [Fact(name="status.priority_handled", value=True)],
        consequence_fact_names=["status.priority_handled"]
    ))

    traces = engine.forward_chain()
    assert len(traces) == 2
    # High priority should fire first
    assert traces[0].rule_id == "RULE_HIGH"
    assert traces[1].rule_id == "RULE_LOW"
    assert wm.get_value("status.priority_handled") is True
    assert wm.get_value("status.adult") is True


def test_backward_chaining_goal_seek():
    advisor = WealthExpertAdvisor()
    # Profile with low credit score and high debt
    subprime_input = SecureUserProfileInput(
        name="Rohan Subprime",
        age=26,
        monthly_income=30000.0,
        credit_score=600,
        employment_type="Salaried",
        existing_emis=18000.0,
        dependents=0,
        financial_goal="Emergency Fund",
        risk_tolerance="Low",
        preferred_spend_category="General"
    )

    result = advisor.analyze(subprime_input)
    assert result.domains["loan"].eligible is False

    # Seek goal to qualify for loan
    remediation = advisor.seek_goal_remediation("loan.eligible", True)
    assert remediation["achieved"] is False
    assert len(remediation["remediation_plan"]) > 0
    # Must advise on CIBIL and FOIR
    remediation_str = " ".join(remediation["remediation_plan"])
    assert "CIBIL" in remediation_str or "credit score" in remediation_str.lower()
    assert "FOIR" in remediation_str or "EMI" in remediation_str


def test_protective_override_floors():
    # Case: Severe debt burden (FOIR = 25k/30k = 83%)
    stressed_profile = {
        "monthly_income": 30000.0,
        "existing_emis": 25000.0,
        "credit_score": 750,
        "dependents": 0,
        "employment_type": "Salaried"
    }
    dummy_domains = {"insurance": {"eligible": True, "headline": "Health Only"}}
    fhi = FinancialHealthScorer.evaluate(stressed_profile, dummy_domains)

    # Even with credit score 750, FOIR > 55% must clamp FHI <= 45
    assert fhi.composite_score <= 45.0
    assert any("CRITICAL_DEBT_BURDEN_CEILING" in ov for ov in fhi.active_overrides)


def test_security_input_validation():
    # Negative income must be rejected
    with pytest.raises(ValidationError):
        SecureUserProfileInput(
            age=30,
            monthly_income=-5000.0,
            credit_score=750,
            employment_type="Salaried",
            financial_goal="Wealth Creation",
            risk_tolerance="Medium",
        )

    # Invalid CIBIL credit score (>900) must be rejected
    with pytest.raises(ValidationError):
        SecureUserProfileInput(
            age=30,
            monthly_income=50000.0,
            credit_score=950,
            employment_type="Salaried",
            financial_goal="Wealth Creation",
            risk_tolerance="Medium",
        )


def test_pdf_generation_and_sha256_fingerprint():
    advisor = WealthExpertAdvisor()
    test_input = SecureUserProfileInput(
        name="Aarav Sharma",
        age=28,
        monthly_income=120000.0,
        credit_score=780,
        employment_type="Salaried",
        existing_emis=15000.0,
        dependents=1,
        financial_goal="Wealth Creation",
        risk_tolerance="High",
        preferred_spend_category="Travel"
    )
    result = advisor.analyze(test_input)

    assert result.audit_record["sha256_fingerprint"] is not None
    assert len(result.audit_record["sha256_fingerprint"]) == 64

    pdf_bytes = FinancialDossierPDFGenerator.generate(result)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")
