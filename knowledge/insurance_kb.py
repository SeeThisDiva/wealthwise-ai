"""
Insurance Knowledge Base — Production Rules for Family & Life Protection.
Implements IRDAI thumb rules, Human Life Value (HLV) mortality cover,
health sum insured matrices, and education/retirement riders.
"""

from __future__ import annotations

from core.facts import Fact, WorkingMemory
from core.rules import Remedy, Rule
from data.catalog import INSURANCE_CATALOG, Product


def _remedy_term(wm: WorkingMemory) -> list[Remedy]:
    deps = int(wm.get_value("user.dependents", 0))
    age = int(wm.get_value("user.age", 30))
    income = float(wm.get_value("user.monthly_income", 0.0))
    steps: list[Remedy] = []
    if deps <= 0:
        steps.append(Remedy(
            text="Term life cover is recommended once at least one person depends on your income "
                 "(dependents is 0 now).",
            changes={"user.dependents": 1}
        ))
    if age >= 60:
        steps.append(Remedy(
            text=f"This term-cover rule applies below age 60 (age is {age}); it cannot be changed.",
            fixable=False
        ))
    if income <= 0:
        steps.append(Remedy(
            text="Term cover is sized on verifiable income, and none is declared.",
            fixable=False
        ))
    return steps


def _remedy_family_health(wm: WorkingMemory) -> list[Remedy]:
    return [Remedy(
        text="The family floater applies once at least one dependent is declared (dependents is 0 now); "
             "with none, the individual plan is recommended instead.",
        changes={"user.dependents": 1}
    )]


def _remedy_individual_health(wm: WorkingMemory) -> list[Remedy]:
    deps = int(wm.get_value("user.dependents", 0))
    return [Remedy(
        text=f"The individual plan applies when no one depends on you ({deps} dependents declared); "
             f"with dependents, the family floater is recommended instead.",
        changes={"user.dependents": 0}
    )]


def _remedy_child_edu(wm: WorkingMemory) -> list[Remedy]:
    steps: list[Remedy] = []
    if wm.get_value("user.financial_goal", "") != "Child Education":
        steps.append(Remedy(
            text="The child education plan is added when the financial goal is 'Child Education'.",
            changes={"user.financial_goal": "Child Education"}
        ))
    if int(wm.get_value("user.dependents", 0)) <= 0:
        steps.append(Remedy(
            text="It also needs at least one dependent (a child) on the profile.",
            changes={"user.dependents": 1}
        ))
    return steps


def _remedy_retirement(wm: WorkingMemory) -> list[Remedy]:
    return [Remedy(
        text="The NPS pension is recommended for a 'Retirement Planning' goal, or for earners aged 35-55 "
             "with monthly income of at least ₹40,000.",
        changes={"user.financial_goal": "Retirement Planning"}
    )]


def build_insurance_rules() -> list[Rule]:
    """Generates production rules for the Insurance Advisory Domain."""
    rules: list[Rule] = []

    # --------------------------------------------------------------------------
    # RULE 1: Comprehensive Term Life Protection (Human Life Value Sizing)
    # --------------------------------------------------------------------------
    def cond_term_life(wm: WorkingMemory) -> bool:
        deps = int(wm.get_value("user.dependents", 0))
        age = int(wm.get_value("user.age", 30))
        income = float(wm.get_value("user.monthly_income", 0.0))
        return deps > 0 and age < 60 and income > 0

    def act_term_life(wm: WorkingMemory, r: Rule) -> list[Fact]:
        income = float(wm.get_value("user.monthly_income", 50000))
        age = int(wm.get_value("user.age", 30))
        # HLV thumb rule: 15x annual income if < 35, else 10x
        multiplier = 15 if age < 35 else 10
        annual_income = income * 12.0
        hlv_cover = round(annual_income * multiplier / 100000.0) * 100000.0  # Round to Lakhs

        return [
            Fact(name="insurance.term_recommended", value=True, certainty=0.95, domain="insurance", source="inferred"),
            Fact(name="insurance.term_cover_amount", value=hlv_cover, certainty=0.95, domain="insurance", source="inferred"),
            Fact(
                name="insurance.term_explanation",
                value=f"HLV thumb rule specifies {multiplier}x annual income cover (₹{hlv_cover:,.0f}) to secure dependents against loss of breadwinner.",
                certainty=0.95,
                domain="insurance",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_INS_01_TERM_LIFE_PROTECTION",
        domain="insurance",
        description="Human Life Value (HLV) Mandate: Earners with dependents require 10x-15x annual income term life coverage.",
        priority=250,
        conditions=[cond_term_life],
        action=act_term_life,
        cf_rule=0.95,
        condition_descriptions=["Dependents > 0", "Applicant Age < 60", "Positive verifiable income"],
        consequence_fact_names=["insurance.term_recommended", "insurance.term_cover_amount", "insurance.term_explanation"],
        remedy=_remedy_term
    ))

    # --------------------------------------------------------------------------
    # RULE 2: Family Floater Health Insurance
    # --------------------------------------------------------------------------
    def cond_family_health(wm: WorkingMemory) -> bool:
        deps = int(wm.get_value("user.dependents", 0))
        return deps > 0

    def act_family_health(wm: WorkingMemory, r: Rule) -> list[Fact]:
        age = int(wm.get_value("user.age", 30))
        sum_insured = 1000000.0 if age < 45 else 1500000.0  # ₹10L or ₹15L
        return [
            Fact(name="insurance.health_family_recommended", value=True, certainty=0.95, domain="insurance", source="inferred"),
            Fact(name="insurance.health_sum_insured", value=sum_insured, certainty=0.95, domain="insurance", source="inferred"),
            Fact(
                name="insurance.health_explanation",
                value=f"Family Floater coverage of ₹{sum_insured:,.0f} recommended to ring-fence family savings against medical inflation.",
                certainty=0.95,
                domain="insurance",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_INS_02_FAMILY_HEALTH_FLOATER",
        domain="insurance",
        description="Family Floater Health Rule: Recommends ₹10L-₹15L floater policy for households with dependents.",
        priority=240,
        conditions=[cond_family_health],
        action=act_family_health,
        cf_rule=0.95,
        condition_descriptions=["Dependents > 0"],
        consequence_fact_names=["insurance.health_family_recommended", "insurance.health_sum_insured", "insurance.health_explanation"],
        remedy=_remedy_family_health
    ))

    # --------------------------------------------------------------------------
    # RULE 3: Individual Comprehensive Health Insurance
    # --------------------------------------------------------------------------
    def cond_indiv_health(wm: WorkingMemory) -> bool:
        deps = int(wm.get_value("user.dependents", 0))
        return deps == 0

    def act_indiv_health(wm: WorkingMemory, r: Rule) -> list[Fact]:
        age = int(wm.get_value("user.age", 30))
        sum_insured = 500000.0 if age < 45 else 1000000.0  # ₹5L or ₹10L
        return [
            Fact(name="insurance.health_indiv_recommended", value=True, certainty=0.90, domain="insurance", source="inferred"),
            Fact(name="insurance.health_sum_insured", value=sum_insured, certainty=0.90, domain="insurance", source="inferred"),
            Fact(
                name="insurance.health_explanation",
                value=f"Individual medical cover of ₹{sum_insured:,.0f} recommended with restoration and OPD benefits.",
                certainty=0.90,
                domain="insurance",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_INS_03_INDIVIDUAL_HEALTH_COVER",
        domain="insurance",
        description="Individual Health Rule: Recommends ₹5L-₹10L individual cover for single individuals.",
        priority=240,
        conditions=[cond_indiv_health],
        action=act_indiv_health,
        cf_rule=0.90,
        condition_descriptions=["Dependents == 0"],
        consequence_fact_names=["insurance.health_indiv_recommended", "insurance.health_sum_insured", "insurance.health_explanation"],
        remedy=_remedy_individual_health
    ))

    # --------------------------------------------------------------------------
    # RULE 4: Child Education Endowment
    # --------------------------------------------------------------------------
    def cond_child_edu(wm: WorkingMemory) -> bool:
        goal = wm.get_value("user.financial_goal", "")
        deps = int(wm.get_value("user.dependents", 0))
        return goal == "Child Education" and deps > 0

    def act_child_edu(wm: WorkingMemory, r: Rule) -> list[Fact]:
        return [
            Fact(name="insurance.child_edu_recommended", value=True, certainty=0.90, domain="insurance", source="inferred"),
            Fact(
                name="insurance.child_edu_explanation",
                value="Targeted child plan with premium waiver rider ensures university funds even in unforeseen circumstances.",
                certainty=0.90,
                domain="insurance",
                source="inferred"
            )
        ]

    rules.append(Rule(
        rule_id="RULE_INS_04_CHILD_EDUCATION_PLAN",
        domain="insurance",
        description="Goal Alignment: Injects child education endowment plan when Goal = 'Child Education'.",
        priority=220,
        conditions=[cond_child_edu],
        action=act_child_edu,
        cf_rule=0.90,
        condition_descriptions=["Financial Goal == 'Child Education'", "Dependents > 0"],
        consequence_fact_names=["insurance.child_edu_recommended", "insurance.child_edu_explanation"],
        remedy=_remedy_child_edu
    ))

    # --------------------------------------------------------------------------
    # RULE 6: Retirement Pension (NPS)
    # --------------------------------------------------------------------------
    def cond_retirement(wm: WorkingMemory) -> bool:
        goal = wm.get_value("user.financial_goal", "")
        age = int(wm.get_value("user.age", 30))
        income = float(wm.get_value("user.monthly_income", 0.0))
        if goal == "Retirement Planning":
            return age < 70   # NPS Tier-I entry age limit
        return 35 <= age <= 55 and income >= 40000

    def act_retirement(wm: WorkingMemory, r: Rule) -> list[Fact]:
        goal = wm.get_value("user.financial_goal", "")
        if goal == "Retirement Planning":
            why = "Your stated goal is retirement planning, and NPS gives a low-cost, regulated pension corpus."
        else:
            why = "Earners in their prime saving years benefit from starting a pension corpus alongside protection cover."
        return [
            Fact(name="insurance.retirement_recommended", value=True, certainty=0.90, domain="insurance", source="inferred"),
            Fact(name="insurance.retirement_explanation", value=why, certainty=0.90, domain="insurance", source="inferred"),
        ]

    rules.append(Rule(
        rule_id="RULE_INS_06_RETIREMENT_PENSION",
        domain="insurance",
        description="Retirement Pension Rule: Recommends NPS Tier-I for retirement goals or mid-career earners (35-55, income >= ₹40,000).",
        priority=230,
        conditions=[cond_retirement],
        action=act_retirement,
        cf_rule=0.90,
        condition_descriptions=["Goal == 'Retirement Planning' (age < 70) OR age 35-55 with monthly income >= ₹40,000"],
        consequence_fact_names=["insurance.retirement_recommended", "insurance.retirement_explanation"],
        remedy=_remedy_retirement
    ))

    # --------------------------------------------------------------------------
    # RULE 5: Aggregator & Product Synthesis Rule
    # --------------------------------------------------------------------------
    def cond_synthesize(wm: WorkingMemory) -> bool:
        return (
            wm.has_fact("insurance.term_recommended") or
            wm.has_fact("insurance.health_family_recommended") or
            wm.has_fact("insurance.health_indiv_recommended") or
            wm.has_fact("insurance.retirement_recommended")
        )

    def act_synthesize(wm: WorkingMemory, r: Rule) -> list[Fact]:
        products: list[Product] = []
        headlines: list[str] = []

        if wm.get_value("insurance.term_recommended"):
            cover = wm.get_value("insurance.term_cover_amount", 10000000.0)
            headlines.append(f"Term Life (₹{cover/10000000:.1f} Cr Cover)")
            products.extend(INSURANCE_CATALOG["term_life"])

        if wm.get_value("insurance.health_family_recommended"):
            cover = wm.get_value("insurance.health_sum_insured", 1000000.0)
            headlines.append(f"Family Health Floater (₹{cover/100000:.0f}L)")
            products.extend(INSURANCE_CATALOG["health_family"])
        elif wm.get_value("insurance.health_indiv_recommended"):
            cover = wm.get_value("insurance.health_sum_insured", 500000.0)
            headlines.append(f"Individual Health (₹{cover/100000:.0f}L)")
            products.extend(INSURANCE_CATALOG["health_individual"])

        if wm.get_value("insurance.child_edu_recommended"):
            headlines.append("Child Future Shield")
            products.extend(INSURANCE_CATALOG["child_education"])

        if wm.get_value("insurance.retirement_recommended"):
            headlines.append("Retirement Pension (NPS)")
            products.extend(INSURANCE_CATALOG["retirement_pension"])

        full_headline = " + ".join(headlines)

        return [
            Fact(name="insurance.eligible", value=True, certainty=0.95, domain="insurance", source="inferred"),
            Fact(name="insurance.headline", value=full_headline, certainty=0.95, domain="insurance", source="inferred"),
            Fact(name="insurance.products", value=products, certainty=0.95, domain="insurance", source="inferred")
        ]

    rules.append(Rule(
        rule_id="RULE_INS_05_SYNTHESIZE_PORTFOLIO",
        domain="insurance",
        description="Insurance Synthesis Engine: Combines mortality and morbidity recommendations into a unified protection portfolio.",
        priority=150,
        conditions=[cond_synthesize],
        action=act_synthesize,
        cf_rule=0.95,
        condition_descriptions=["At least one underlying insurance condition triggered"],
        consequence_fact_names=["insurance.eligible", "insurance.headline", "insurance.products"]
    ))

    return rules
