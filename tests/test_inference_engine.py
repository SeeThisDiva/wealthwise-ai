"""Tests for CF attenuation, verified backward chaining, the pension rule and thread safety."""

import itertools
from concurrent.futures import ThreadPoolExecutor

import pytest

from advisor import WealthExpertAdvisor
from core.engine import InferenceEngine
from core.facts import Fact, WorkingMemory
from core.rules import Rule
from core.security import SecureUserProfileInput


def make_profile(**overrides) -> SecureUserProfileInput:
    data = dict(
        name="Test User", age=30, monthly_income=60000.0, credit_score=760,
        employment_type="Salaried", existing_emis=5000.0, dependents=0,
        financial_goal="Wealth Creation", risk_tolerance="Medium",
        preferred_spend_category="General",
    )
    data.update(overrides)
    return SecureUserProfileInput(**data)


# ---------------------------------------------------------------- CF attenuation

def _chain_engine(first_cf, second_rule_cf, second_fact_cf=1.0):
    wm = WorkingMemory()
    wm.assert_fact(Fact(name="user.x", value=1, certainty=1.0, source="initial"))
    eng = InferenceEngine(wm)
    eng.register_rule(Rule(
        rule_id="R1", domain="t", description="derive a", priority=200,
        conditions=[lambda m: m.get_value("user.x") == 1],
        action=lambda m, r: [Fact(name="t.a", value=True, certainty=first_cf, source="inferred")],
        cf_rule=first_cf, consequence_fact_names=["t.a"],
    ))
    eng.register_rule(Rule(
        rule_id="R2", domain="t", description="derive b from a", priority=100,
        conditions=[lambda m: m.get_value("t.a") is True],
        action=lambda m, r: [Fact(name="t.b", value=True, certainty=second_fact_cf, source="inferred")],
        cf_rule=second_rule_cf, consequence_fact_names=["t.b"],
    ))
    return eng, wm


def test_client_input_premises_leave_certainty_unchanged():
    eng, wm = _chain_engine(first_cf=0.8, second_rule_cf=0.9)
    eng.forward_chain()
    assert wm.get_certainty("t.a") == pytest.approx(0.8)


def test_chained_rule_inherits_premise_uncertainty():
    eng, wm = _chain_engine(first_cf=0.8, second_rule_cf=0.9, second_fact_cf=0.9)
    traces = eng.forward_chain()
    # premise CF 0.8 (fact t.a) * rule CF 0.9
    assert wm.get_certainty("t.b") == pytest.approx(0.72)
    assert traces[1].premise_cf == pytest.approx(0.8)


def test_rule_cf_caps_overconfident_fact():
    eng, wm = _chain_engine(first_cf=1.0, second_rule_cf=0.5, second_fact_cf=1.0)
    eng.forward_chain()
    assert wm.get_certainty("t.b") == pytest.approx(0.5)


def test_insurance_synthesis_is_weaker_than_its_evidence():
    result = WealthExpertAdvisor().analyze(make_profile(dependents=2))
    wm = result.working_memory_snapshot
    assert wm["insurance.eligible"]["certainty"] < wm["insurance.term_recommended"]["certainty"]


# ---------------------------------------------------------------- backward chaining

def _plan(profile, target="loan.eligible", value=True):
    return WealthExpertAdvisor().seek_goal_remediation(target, value, profile)


def test_verified_plan_actually_unlocks_the_loan():
    advisor = WealthExpertAdvisor()
    profile = make_profile(age=26, monthly_income=30000.0, credit_score=600,
                           existing_emis=18000.0, financial_goal="Emergency Fund")
    plan = advisor.seek_goal_remediation("loan.eligible", True, profile)
    assert plan["achieved"] is False and plan["plan_verified"] is True
    changed = profile.model_dump()
    for name, value in plan["verified_changes"].items():
        changed[name.split(".", 1)[1]] = value
    assert advisor.analyze(SecureUserProfileInput(**changed)).domains["loan"].eligible is True


def test_income_gate_uses_the_rule_threshold_not_a_stale_constant():
    plan = _plan(make_profile(monthly_income=14000.0, existing_emis=0.0))
    assert plan["plan_verified"] is True
    assert plan["verified_changes"] == {"user.monthly_income": 15000.0}


def test_age_blocker_is_reported_as_unfixable():
    plan = _plan(make_profile(age=63, existing_emis=0.0))
    assert plan["plan_verified"] is False
    assert any("cannot be changed" in step for step in plan["remediation_plan"])


def test_already_satisfied_goal():
    advisor = WealthExpertAdvisor()
    profile = make_profile()
    advisor.analyze(profile)
    assert advisor.seek_goal_remediation("loan.eligible", True)["achieved"] is True


def test_unknown_goal_has_no_rules():
    plan = _plan(make_profile(), target="nope.fact")
    assert plan["achieved"] is False and plan["remediation_plan"] == []


def test_dynamic_goal_uses_verified_counterfactual_search():
    plan = _plan(make_profile(age=26, risk_tolerance="Low", financial_goal="Emergency Fund"),
                 target="investment.risk_category", value="Aggressive")
    assert plan["plan_verified"] is True
    assert plan["verified_changes"] == {"user.risk_tolerance": "High"}


def test_insurance_goal_has_remediation():
    plan = _plan(make_profile(dependents=0), target="insurance.term_recommended")
    assert plan["verified_changes"] == {"user.dependents": 1}


def test_no_profile_loaded():
    plan = WealthExpertAdvisor().seek_goal_remediation("loan.eligible", True)
    assert plan["achieved"] is False and "No client profile" in plan["message"]


def test_plan_is_consistent_with_forward_chaining_across_a_grid():
    """Every plan marked verified must really flip the verdict; unverified ones must be unfixable or unsized."""
    advisor = WealthExpertAdvisor()
    grid = itertools.product(
        [18, 30, 62], [0.0, 12000.0, 40000.0], [550, 700], [0.0, 25000.0],
        ["Salaried", "Student", "Self-Employed"],
    )
    checked = 0
    for age, income, score, emis, emp in grid:
        profile = make_profile(age=age, monthly_income=income, credit_score=score,
                               existing_emis=emis, employment_type=emp)
        result = advisor.analyze(profile)
        plan = advisor.seek_goal_remediation("loan.eligible", True, profile)
        if result.domains["loan"].eligible:
            assert plan["achieved"] is True
            continue
        checked += 1
        if plan["plan_verified"]:
            changed = profile.model_dump()
            for name, value in plan["verified_changes"].items():
                changed[name.split(".", 1)[1]] = value
            assert advisor.analyze(SecureUserProfileInput(**changed)).domains["loan"].eligible is True
        else:
            assert plan["remediation_plan"], f"no advice for {profile}"
    assert checked > 20


# ---------------------------------------------------------------- pension rule

def test_retirement_goal_adds_nps_to_insurance_portfolio():
    result = WealthExpertAdvisor().analyze(make_profile(financial_goal="Retirement Planning"))
    ins = result.domains["insurance"]
    assert "Retirement Pension" in ins.headline
    assert any("NPS" in p.name for p in ins.products)
    assert any(t.rule_id == "RULE_INS_06_RETIREMENT_PENSION" for t in result.firing_history)


def test_young_non_retirement_profile_gets_no_pension():
    result = WealthExpertAdvisor().analyze(make_profile(age=25, financial_goal="Wealth Creation"))
    assert "Retirement Pension" not in result.domains["insurance"].headline


def test_mid_career_high_earner_gets_pension_without_stated_goal():
    result = WealthExpertAdvisor().analyze(make_profile(age=42, monthly_income=90000.0))
    assert "Retirement Pension" in result.domains["insurance"].headline


# ---------------------------------------------------------------- web + concurrency

def test_backward_chain_endpoint_with_profile_and_bad_profile():
    from web.server import app
    client = app.test_client()
    good = client.post("/api/backward-chain", json={
        "target_fact": "loan.eligible", "desired_value": True,
        "profile": make_profile(monthly_income=14000.0, existing_emis=0.0).model_dump(),
    })
    assert good.status_code == 200 and good.get_json()["plan_verified"] is True
    bad = client.post("/api/backward-chain", json={"profile": {"age": "x"}})
    assert bad.status_code == 422


def test_concurrent_analyses_do_not_share_working_memory():
    advisor = WealthExpertAdvisor()
    profiles = [make_profile(monthly_income=float(20000 + 5000 * i), credit_score=600 + 20 * i)
                for i in range(12)]
    expected = [advisor.analyze(p).domains["loan"].details["max_amount"] for p in profiles]
    with ThreadPoolExecutor(max_workers=8) as pool:
        got = list(pool.map(lambda p: advisor.analyze(p).domains["loan"].details["max_amount"],
                            profiles * 5))
    assert got == expected * 5


def test_export_pdf_rejects_invalid_live_params_instead_of_serving_stale_dossier():
    from web.server import app
    client = app.test_client()
    client.post("/api/analyze", json=make_profile().model_dump())   # warm the cache
    bad = client.get("/api/export-pdf?income=-5&age=30&credit=700")
    assert bad.status_code == 422
    good = client.get("/api/export-pdf?income=90000&age=30&credit=700&deps=0&goal=Wealth%20Creation")
    assert good.status_code == 200 and good.data[:4] == b"%PDF"


# ---------------------------------------------------------------- single source of truth

def _analyze_json(client, **overrides):
    body = make_profile(**overrides).model_dump()
    res = client.post("/api/analyze", json=body)
    assert res.status_code == 200
    return res.get_json()


def test_vitals_match_the_rule_engine_and_the_pdf_source():
    from web.server import app
    client = app.test_client()
    data = _analyze_json(client, age=28, monthly_income=120000.0, existing_emis=18000.0, dependents=1)
    v = data["vitals"]
    assert v["fhi"]["score"] == data["fhi"]["composite_score"]
    assert v["borrowing"]["max_amount"] == data["domains"]["loan"]["details"]["max_amount"]
    assert v["life_cover"]["amount"] == data["domains"]["insurance"]["details"]["term_cover"]
    assert v["life_cover"]["annual_income_multiple"] == 15.0      # HLV rule: 15x under 35
    assert v["foir"]["pct"] == 15.0 and v["foir"]["status"] == "safe"
    assert all("premise_cf" in f for f in data["firing_history"])


def test_no_dependents_means_no_life_cover_recommendation():
    from web.server import app
    v = _analyze_json(app.test_client(), dependents=0)["vitals"]
    assert v["life_cover"]["recommended"] is False


def test_ineligible_borrower_gets_no_borrowing_figure():
    from web.server import app
    v = _analyze_json(app.test_client(), credit_score=590)["vitals"]
    assert v["borrowing"]["state"] == "not_eligible" and v["borrowing"]["max_amount"] == 0.0


def test_stress_endpoint_validates_and_matches_formula():
    from web.server import app
    client = app.test_client()
    ok = client.post("/api/stress-test", json={"monthly_income": 100000, "existing_emis": 20000,
                                               "rate_hike_bps": 150, "income_drop_pct": 20})
    body = ok.get_json()
    assert ok.status_code == 200
    assert body["stressed_income"] == 80000.0
    assert body["stressed_emis"] == pytest.approx(21200.0)
    assert body["insolvent"] is False
    for bad in ({"income_drop_pct": 150}, {"monthly_income": "abc"}, {"rate_hike_bps": -1},
                {"monthly_income": float("inf")}):
        assert client.post("/api/stress-test", json=bad).status_code == 422


def test_frontend_no_longer_duplicates_scoring_math():
    """Guards the refactor: the browser must not recompute FHI, loan limits or HLV cover."""
    import pathlib
    js = pathlib.Path("web/static/js/app.js").read_text(encoding="utf-8")
    for leftover in ("hlvMultiplier", "emiPerLakh", "rawScore", "fhiScore", "updateVitalsAndScoreFast"):
        assert leftover not in js, leftover


def test_single_source_of_truth_parity_across_analyze_offline_advisory_and_pdf(monkeypatch):
    """Dashboard vitals, offline /api/gemini-advisory, and PDF generator must agree on every figure."""
    from reports.dossier_generator import FinancialDossierPDFGenerator
    from web.server import app

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = app.test_client()

    # Case 1: Eligible prime borrower with 1 dependent (HLV 15x under age 35, ₹10L family health)
    eligible_body = make_profile(
        age=28,
        monthly_income=120000.0,
        existing_emis=18000.0,
        credit_score=785,
        dependents=1,
        employment_type="Salaried",
        risk_tolerance="High",
        financial_goal="Wealth Creation",
        preferred_spend_category="Dining & Lifestyle",
    ).model_dump()

    analyze_data = client.post("/api/analyze", json=eligible_body).get_json()
    advisory_data = client.post("/api/gemini-advisory", json=eligible_body).get_json()

    assert advisory_data["source"] == "deterministic_expert"
    assert advisory_data["health_score"] == analyze_data["fhi"]["composite_score"]
    assert advisory_data["vital_metrics"]["max_borrowing_lakhs"] == pytest.approx(
        round(analyze_data["vitals"]["borrowing"]["max_amount"] / 100_000.0, 2)
    )
    assert advisory_data["vital_metrics"]["recommended_life_cover_cr"] == pytest.approx(2.16)
    assert advisory_data["vital_metrics"]["recommended_health_cover_lakhs"] == 10

    # Case 2: Age-gated borrower (age 63 > 60) with 0 dependents -> ₹0 loan limit and ₹0 term life cover
    senior_body = make_profile(
        age=63,
        monthly_income=120000.0,
        existing_emis=0.0,
        credit_score=800,
        dependents=0,
        employment_type="Salaried",
        risk_tolerance="Low",
        financial_goal="Retirement Planning",
    ).model_dump()

    senior_analyze = client.post("/api/analyze", json=senior_body).get_json()
    senior_advisory = client.post("/api/gemini-advisory", json=senior_body).get_json()

    assert senior_analyze["vitals"]["borrowing"]["state"] == "not_eligible"
    assert senior_analyze["vitals"]["borrowing"]["max_amount"] == 0.0
    assert senior_analyze["vitals"]["life_cover"]["recommended"] is False
    assert senior_advisory["vital_metrics"]["max_borrowing_lakhs"] == 0.0
    assert senior_advisory["vital_metrics"]["recommended_life_cover_cr"] == 0.0
    ins_names = [p["name"] for p in senior_advisory["categorized_products"]["insurance"]]
    loan_names = [p["name"] for p in senior_advisory["categorized_products"]["loans"]]
    assert not any("Tech Term" in n for n in ins_names)
    assert not any("XPRESS Personal Loan" in n for n in loan_names)

    senior_res = WealthExpertAdvisor().analyze(SecureUserProfileInput(**senior_body))
    pdf_bytes = FinancialDossierPDFGenerator.generate(senior_res)
    assert pdf_bytes.startswith(b"%PDF")


def test_pdf_escapes_xml_special_characters_and_sets_neutral_metadata():
    from reports.dossier_generator import FinancialDossierPDFGenerator, _esc

    assert _esc("Dining & Lifestyle <script>\"'") == "Dining &amp; Lifestyle &lt;script&gt;&quot;&#39;"

    advisor = WealthExpertAdvisor()
    result = advisor.analyze(
        make_profile(
            preferred_spend_category="Dining & Lifestyle",
            financial_goal="Tax Saving",
            dependents=1,
        )
    )
    # Inject XML-sensitive characters into a headline to verify ReportLab Paragraph escaping
    result.domains["loan"].headline = "Approved <Prime & Verified> Tier"
    pdf_bytes = FinancialDossierPDFGenerator.generate(result)
    assert pdf_bytes.startswith(b"%PDF")
    assert b"/Author (WealthWise)" in pdf_bytes
    assert b"/Creator (WealthWise)" in pdf_bytes

