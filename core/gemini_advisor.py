"""
WealthWise Gemini advisory bridge.

Sends a bounded, allowlisted version of the client's profile to Google Gemini when an API key
is available and falls back to the offline rule-engine advisor otherwise. Everything the model
returns is treated as untrusted: it is rebuilt field by field, text is length-limited, and links
must point at a host already used by the built-in product catalogues.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from typing import Any
from urllib.parse import urlsplit

import requests

from advisor import WealthExpertAdvisor
from core.security import ALLOWED_SPEND, SecureUserProfileInput, clean_advisory_profile
from core.vitals import build_vitals
from data.catalog import CREDIT_CARD_CATALOG, INSURANCE_CATALOG, INVESTMENT_CATALOG, LOAN_CATALOG

try:
    import dotenv

    dotenv.load_dotenv()
except Exception:
    pass

log = logging.getLogger(__name__)

CATEGORIES = ("cards", "loans", "insurance", "investments")
HEALTH_TIERS = (
    "OPTIMAL / RESILIENT",
    "STABLE / GROWTH READY",
    "VULNERABLE / ACTION NEEDED",
    "DISTRESSED / HIGH RISK",
    "Optimal / Resilient",
    "Strong & Balanced",
    "Needs Attention",
    "Debt Stressed",
)
MAX_RESPONSE_BYTES = 200_000
TEXT_LIMITS = {
    "id": 40,
    "name": 80,
    "provider": 60,
    "category_label": 40,
    "headline": 140,
    "personalized_metric": 80,
    "why_matched": 300,
}

_RULE_ADVISOR = WealthExpertAdvisor()


def _text(value: Any, limit: int) -> str:
    """Printable, length-limited string. Markup is neutralised again on the client."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", "" if value is None else str(value)).strip()[:limit]


def _number(value: Any, low: float, high: float, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, low), high) if math.isfinite(number) else default


class GeminiAdvisor:
    """
    Intelligent financial advisor powered by Google Gemini with multi-model fallback
    and deterministic rule-engine fallback.
    """

    DEFAULT_MODELS = "gemini-2.5-flash,gemini-flash-latest"
    GEMINI_API_URL = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )  # key is sent as a header, never in the URL

    @classmethod
    def models_order(cls) -> list[str]:
        raw = os.environ.get("GEMINI_MODELS", cls.DEFAULT_MODELS)
        models = [m.strip() for m in raw.split(",") if m.strip() and re.fullmatch(r"[A-Za-z0-9._-]+", m.strip())]
        return models or ["gemini-2.5-flash", "gemini-flash-latest"]

    @classmethod
    def get_api_key(cls, user_key: str | None = None) -> str | None:
        """Resolves API key from user parameter or environment."""
        if user_key and user_key.strip():
            return user_key.strip()
        env_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if env_key and not env_key.startswith("your_"):  # ignore the .env.example placeholder
            return env_key
        return None

    _hosts: frozenset[str] | None = None

    @classmethod
    def allowed_link_hosts(cls) -> frozenset[str]:
        """Hosts the offline advisor and the static catalogues already link to."""
        if cls._hosts is None:
            urls: list[str] = []
            for catalog in (CREDIT_CARD_CATALOG, LOAN_CATALOG, INSURANCE_CATALOG, INVESTMENT_CATALOG):
                urls += [p.apply_url for products in catalog.values() for p in products]
            for spend in ALLOWED_SPEND:
                for goal in ("Wealth Creation", "Retirement Planning", "Home Purchase", "Child Education"):
                    for cibil in (600, 700, 800):
                        for deps in (0, 1):
                            profile = clean_advisory_profile(
                                {
                                    "preferred_spend_category": spend,
                                    "financial_goal": goal,
                                    "credit_score": cibil,
                                    "dependents": deps,
                                }
                            )
                            products = cls._deterministic_advisory(profile)["recommended_products"]
                            urls += [p["apply_url"] for p in products]
            cls._hosts = frozenset(h for u in urls if (h := urlsplit(u).hostname))
        return cls._hosts

    @classmethod
    def safe_link(cls, url: Any) -> str | None:
        """https only, and only hosts the project already links to."""
        if not isinstance(url, str) or len(url) > 300:
            return None
        parts = urlsplit(url.strip())
        if parts.scheme != "https" or parts.username or parts.password:
            return None
        return url.strip() if parts.hostname in cls.allowed_link_hosts() else None

    @classmethod
    def analyze_profile(cls, profile: dict[str, Any], api_key: str | None = None) -> dict[str, Any]:
        """Gemini when a key is available and its answer passes validation, else offline."""
        clean = clean_advisory_profile(profile)
        offline = cls._deterministic_advisory(clean)

        resolved_key = cls.get_api_key(api_key)
        if resolved_key:
            try:
                remote = cls._call_gemini_api(clean, resolved_key)
            except Exception as exc:
                log.warning("Gemini request failed (%s); using the offline advisor.", type(exc).__name__)
                remote = None
            if remote:
                return cls._merge_with_offline(remote, offline)
        return offline

    @classmethod
    def _call_gemini_api(cls, profile: dict[str, Any], api_key: str) -> dict[str, Any] | None:
        """Calls the configured models in order and returns the first answer that validates."""
        system_instruction = (
            "You are WealthWise AI, a personal finance assistant for an educational demo. "
            "Analyze the user's financial profile and return a JSON object with: "
            "1. 'health_score' (integer 0-100 based on debt load, CIBIL, age, and liquidity). "
            "2. 'health_tier' ('OPTIMAL / RESILIENT', 'STABLE / GROWTH READY', 'VULNERABLE / ACTION NEEDED', or 'DISTRESSED / HIGH RISK'). "
            "3. 'executive_summary' (concise 2-sentence financial health assessment). "
            "4. 'vital_metrics': {'debt_foir_pct': float, 'max_borrowing_lakhs': float, 'recommended_life_cover_cr': float, 'recommended_emergency_months': float}. "
            "5. 'categorized_products': An object with four keys: 'cards', 'loans', 'insurance', 'investments'. "
            "   EACH key MUST contain an array of EXACTLY 3 distinct, high-quality products (12 products total). "
            "Each product MUST have: 'id', 'name', 'provider', 'category' ('cards'|'loans'|'insurance'|'investments'), "
            "'match_score' (integer 75-99), 'category_label', 'headline', 'personalized_metric' (exact unique rupee/percentage figure calculated for this user), "
            "'why_matched' (specific 1-2 sentence explanation referencing their actual numbers and spend focus), "
            "'apply_url' (an https link on the provider's own website). "
            "DO NOT return identical numbers across different products. Health insurance must show hospital cover in lakhs, life insurance shows mortality cover in crores (0 if dependents is 0), "
            "cards show cashback/points in rupees, and loans show borrowing capacity in lakhs."
        )

        user_prompt = f"""
Financial Profile:
- Monthly Income: ₹{profile['monthly_income']:.0f}
- Existing Monthly EMIs: ₹{profile['existing_emis']:.0f}
- CIBIL Credit Score: {profile['credit_score']}
- Age: {profile['age']}
- Employment: {profile['employment_type']}
- Dependents: {profile['dependents']}
- Risk Tolerance: {profile['risk_tolerance']}
- Primary Goal: {profile['financial_goal']}
- Dominant Spend: {profile['preferred_spend_category']}

Return ONLY valid JSON with no markdown formatting.
"""

        payload = {
            "contents": [{"parts": [{"text": system_instruction + "\n" + user_prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }

        for model in cls.models_order():
            url = cls.GEMINI_API_URL.format(model=model)
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=14,
                    headers={"x-goog-api-key": api_key},
                )
                if response.status_code in (404, 429, 503):
                    log.info("%s returned %s; trying the next model.", model, response.status_code)
                    continue
                if response.status_code != 200 or len(response.content) > MAX_RESPONSE_BYTES:
                    log.warning("%s returned HTTP %s.", model, response.status_code)
                    continue
                candidates = response.json().get("candidates") or []
                if not candidates:
                    continue
                text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", text_content.strip(), flags=re.MULTILINE)
                result = cls._sanitize_model_output(json.loads(clean_json))
                if result:
                    result["source"] = "gemini_ai"
                    result["model"] = _text(model, 60)
                    return result
            except Exception as exc:
                log.warning("%s failed (%s); trying the next model.", model, type(exc).__name__)
        return None

    @classmethod
    def _sanitize_model_output(cls, parsed: Any) -> dict[str, Any] | None:
        """Rebuild the model's answer from known keys only; anything else is discarded."""
        if not isinstance(parsed, dict):
            return None

        grouped: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
        raw_groups = parsed.get("categorized_products")
        if not isinstance(raw_groups, dict):
            raw_groups = {}
        for category in CATEGORIES:
            items = raw_groups.get(category)
            for item in (items if isinstance(items, list) else [])[:3]:
                product = cls._sanitize_product(item, category)
                if product:
                    grouped[category].append(product)
        if not any(grouped.values()):
            return None

        out: dict[str, Any] = {"categorized_products": grouped}
        if isinstance(parsed.get("health_score"), (int, float)) and not isinstance(parsed.get("health_score"), bool):
            out["health_score"] = int(_number(parsed["health_score"], 0, 100, 0))
        if parsed.get("health_tier") in HEALTH_TIERS:
            out["health_tier"] = parsed["health_tier"]
        if parsed.get("executive_summary"):
            out["executive_summary"] = _text(parsed["executive_summary"], 400)
        metrics = parsed.get("vital_metrics")
        if isinstance(metrics, dict):
            out["vital_metrics"] = {
                key: round(_number(metrics.get(key), 0, 1_000_000, 0.0), 2)
                for key in (
                    "debt_foir_pct",
                    "max_borrowing_lakhs",
                    "recommended_life_cover_cr",
                    "recommended_emergency_months",
                )
                if key in metrics
            }
        return out

    @classmethod
    def _sanitize_product(cls, item: Any, category: str) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        link = cls.safe_link(item.get("apply_url"))
        product = {key: _text(item.get(key), limit) for key, limit in TEXT_LIMITS.items()}
        if not link or not product["name"] or not product["provider"]:
            return None
        product.update(
            category=category,
            apply_url=link,
            match_score=int(_number(item.get("match_score"), 0, 100, 80)),
        )
        return product

    @staticmethod
    def _merge_with_offline(remote: dict[str, Any], offline: dict[str, Any]) -> dict[str, Any]:
        """Fill anything the model left out (or that failed validation) from the offline advisor."""
        merged = {**offline, **{k: v for k, v in remote.items() if k != "categorized_products"}}
        grouped = {}
        for category in CATEGORIES:
            products = list(remote["categorized_products"].get(category, []))
            for fallback in offline["categorized_products"].get(category, []):
                if len(products) >= 3:
                    break
                products.append(fallback)
            grouped[category] = products[:3]
        merged["categorized_products"] = grouped
        merged["recommended_products"] = [p for c in CATEGORIES for p in grouped[c]]
        return merged

    @classmethod
    def _deterministic_advisory(cls, profile: dict[str, Any]) -> dict[str, Any]:
        """
        Offline deterministic advisory backed directly by WealthExpertAdvisor.analyze()
        and build_vitals(), guaranteeing identical figures across dashboard, cards, CLI, and PDF.
        """
        user_input = SecureUserProfileInput(
            name="Client",
            age=int(profile.get("age", 28)),
            monthly_income=float(profile.get("monthly_income", 120000.0)),
            credit_score=int(profile.get("credit_score", 785)),
            employment_type=str(profile.get("employment_type", "Salaried")),
            existing_emis=float(profile.get("existing_emis", 18000.0)),
            dependents=int(profile.get("dependents", 1)),
            financial_goal=str(profile.get("financial_goal", "Wealth Creation")),
            risk_tolerance=str(profile.get("risk_tolerance", "High")),
            preferred_spend_category=str(profile.get("preferred_spend_category", "General")),
        )
        exec_res = _RULE_ADVISOR.analyze(user_input, record_session=False)
        vitals = build_vitals(exec_res)

        income = user_input.monthly_income
        emis = user_input.existing_emis
        cibil = user_input.credit_score
        age = user_input.age
        dependents = user_input.dependents
        spend = user_input.preferred_spend_category
        goal = user_input.financial_goal

        foir = float(vitals["foir"]["pct"])
        score = round(exec_res.fhi.composite_score, 1)
        tier = exec_res.fhi.tier_badge
        summary = vitals["summary"]["body"]

        loan_rec = exec_res.domains["loan"]
        card_rec = exec_res.domains["credit"]
        ins_rec = exec_res.domains["insurance"]
        inv_rec = exec_res.domains["investment"]

        loan_eligible = vitals["borrowing"]["state"] == "eligible"
        max_loan_lakhs = round(float(vitals["borrowing"]["max_amount"]) / 100_000.0, 2)
        loan_rate_short = str(loan_rec.details.get("interest_rate", "10.99% p.a.")).split(" (")[0]

        life_recommended = bool(vitals["life_cover"]["recommended"])
        life_cover_cr = round(float(vitals["life_cover"]["amount"]) / 10_000_000.0, 2)
        hlv_mult = vitals["life_cover"]["annual_income_multiple"]
        health_cover_lakhs = int(round(float(ins_rec.details.get("health_sum_insured", 500_000.0)) / 100_000.0))

        emergency_months = float(vitals["emergency_reserve"]["months"])
        emergency_buffer_lakhs = round(float(vitals["emergency_reserve"]["target_amount"]) / 100_000.0, 2)

        alloc = inv_rec.details.get("allocation") or {}
        suggested_equity = int(alloc.get("Equity", 50))
        risk_cat = str(inv_rec.details.get("risk_category", "Moderate"))
        surplus = max(0.0, income - emis)
        sip_amount = max(5000, int(surplus * 0.25)) if surplus > 0 else 0

        cards: list[dict[str, Any]] = []
        loans: list[dict[str, Any]] = []
        insurance: list[dict[str, Any]] = []
        investments: list[dict[str, Any]] = []

        # ======================================================================
        # SECTION A: CREDIT CARDS (3 Distinct Options, respecting RULE_CARD_01..04)
        # ======================================================================
        if card_rec.eligible:
            if spend == "Travel":
                cards.append(
                    {
                        "id": "card_atlas",
                        "name": "Axis Bank Atlas Card",
                        "provider": "Axis Bank",
                        "category": "cards",
                        "category_label": "Travel & Air-Miles",
                        "match_score": 98 if cibil >= 750 else 90,
                        "headline": "5x EDGE Air-Miles on Airline & Hotel Bookings",
                        "personalized_metric": f"~₹{int(income * 0.12):,} value in airline miles",
                        "why_matched": "Matched to your Travel spend preference with accelerated air-miles and domestic/international lounge access.",
                        "apply_url": "https://www.axisbank.com/retail/cards/credit-card/atlas-credit-card",
                    }
                )
            elif spend == "Dining & Lifestyle":
                cards.append(
                    {
                        "id": "card_liveplus",
                        "name": "HSBC Live+ Credit Card",
                        "provider": "HSBC India",
                        "category": "cards",
                        "category_label": "Dining & Groceries",
                        "match_score": 97 if cibil >= 750 else 89,
                        "headline": "10% Direct Cashback on Dining, Food Apps & Groceries",
                        "personalized_metric": f"~₹{int(income * 0.09):,}/yr in direct cashback",
                        "why_matched": "Curated for Dining & Lifestyle spend with statement cashback on dining, food delivery, and groceries.",
                        "apply_url": "https://www.hsbc.co.in/credit-cards/products/live-plus/",
                    }
                )
            elif spend == "Fuel & Commute":
                cards.append(
                    {
                        "id": "card_bpcl",
                        "name": "BPCL SBI Card Octane",
                        "provider": "State Bank of India",
                        "category": "cards",
                        "category_label": "Fuel & Commute",
                        "match_score": 96,
                        "headline": "7.25% Value-Back on Fuel at Bharat Petroleum Outlets",
                        "personalized_metric": f"~₹{int(income * 0.06):,}/yr saved on fuel",
                        "why_matched": "Maximizes savings on daily commute and fuel purchases with fuel surcharge waivers.",
                        "apply_url": "https://www.sbicard.com/en/personal/credit-cards/fuel/bpcl-sbi-card-octane.page",
                    }
                )
            else:
                cards.append(
                    {
                        "id": "card_millennia",
                        "name": "HDFC Millennia Credit Card",
                        "provider": "HDFC Bank",
                        "category": "cards",
                        "category_label": "Cashback & Retail",
                        "match_score": 98 if cibil >= 750 else 91,
                        "headline": "5% Direct Cashback on Amazon, Flipkart, Myntra & Swiggy",
                        "personalized_metric": f"~₹{int(income * 0.10):,}/yr cashback projection",
                        "why_matched": "Top pick for digital retail and Online Shopping with 5% monthly cash points.",
                        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/millennia-credit-card",
                    }
                )

            cards.append(
                {
                    "id": "card_amazon",
                    "name": "Amazon Pay ICICI Credit Card",
                    "provider": "ICICI Bank",
                    "category": "cards",
                    "category_label": "Lifetime Free Cashback",
                    "match_score": 94,
                    "headline": "Flat 5% Unlimited Cashback • Lifetime Free Card",
                    "personalized_metric": f"~₹{int(income * 0.07):,}/yr lifetime-free cashback",
                    "why_matched": "Zero joining and renewal fees; earns uncapped cashback on utility bills and digital purchases.",
                    "apply_url": "https://www.icicibank.com/personal-banking/cards/credit-card/amazon-pay-credit-card",
                }
            )
            cards.append(
                {
                    "id": "card_regalia",
                    "name": "HDFC Regalia Gold Credit Card",
                    "provider": "HDFC Bank",
                    "category": "cards",
                    "category_label": "Lounge & Milestone Tier",
                    "match_score": 92 if cibil >= 750 else 85,
                    "headline": "12 Domestic Airport Lounge Visits + Milestone Flights",
                    "personalized_metric": f"~₹{int(income * 0.05):,} in annual milestone rewards",
                    "why_matched": "Adds airport lounge access and annual milestone vouchers alongside your primary spend card.",
                    "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/regalia-gold-credit-card",
                }
            )
        else:
            cards.append(
                {
                    "id": "card_wow",
                    "name": "IDFC FIRST WOW! Card",
                    "provider": "IDFC FIRST Bank",
                    "category": "cards",
                    "category_label": "FD-Backed Credit Builder",
                    "match_score": 98,
                    "headline": "Zero CIBIL Check • 100% Approval Backed by Fixed Deposit",
                    "personalized_metric": "FD from ₹2,000 • Rebuilds CIBIL bureau track",
                    "why_matched": f"Unsecured cards are gated by RULE_CARD_01 (CIBIL {cibil}, FOIR {foir:.1f}%). This FD-backed card reports monthly to rebuild credit safely.",
                    "apply_url": "https://www.idfcfirstbank.com/credit-card/wow",
                }
            )
            cards.append(
                {
                    "id": "card_amazon_goal",
                    "name": "Amazon Pay ICICI Credit Card (Target Tier)",
                    "provider": "ICICI Bank",
                    "category": "cards",
                    "category_label": "Next Milestone (CIBIL 650+)",
                    "match_score": 82,
                    "headline": "Lifetime-Free Entry Unsecured Card Once CIBIL Clears 650",
                    "personalized_metric": "₹0 Annual Fee • Target after 6 mos on-time FD card use",
                    "why_matched": "Keep utilisation below 30% on a secured card and reduce FOIR under 50% to unlock this lifetime-free unsecured card.",
                    "apply_url": "https://www.icicibank.com/personal-banking/cards/credit-card/amazon-pay-credit-card",
                }
            )
            cards.append(
                {
                    "id": "card_simplyclick_goal",
                    "name": "SBI SimplyCLICK Credit Card (Target Tier)",
                    "provider": "SBI Card",
                    "category": "cards",
                    "category_label": "Entry Digital Spends",
                    "match_score": 80,
                    "headline": "Low-Fee Entry Card for E-Commerce Once Eligibility Clears",
                    "personalized_metric": "₹499 Annual Fee • 10X Partner Rewards",
                    "why_matched": "Accessible entry-tier card once verifiable income, FOIR (<= 50%), and CIBIL (>= 650) pass underwriting.",
                    "apply_url": "https://www.sbicard.com/en/personal/credit-cards/shopping/simplyclick-sbi-card.page",
                }
            )

        # ======================================================================
        # SECTION B: PERSONAL & ASSET LOANS (3 Distinct Options, respecting RULE_LOAN_01..05)
        # ======================================================================
        if loan_eligible:
            loans.append(
                {
                    "id": "loan_hdfc",
                    "name": "HDFC XPRESS Personal Loan",
                    "provider": "HDFC Bank",
                    "category": "loans",
                    "category_label": "Pre-Qualified Unsecured Loan",
                    "match_score": 96 if cibil >= 750 else 88,
                    "headline": "60-Month Reverse-EMI Sized Capacity with Zero Collateral",
                    "personalized_metric": f"Up to ₹{max_loan_lakhs}L @ {loan_rate_short}",
                    "why_matched": f"Approved by RULE_LOAN_05 within your statutory FOIR ceiling after accounting for ₹{int(emis):,}/mo in existing EMIs.",
                    "apply_url": "https://www.hdfcbank.com/personal/borrow/popular-loans/personal-loan",
                }
            )
            flexi_limit = max(1.0, round(max_loan_lakhs * 0.75, 1))
            loans.append(
                {
                    "id": "loan_flexi",
                    "name": "Bajaj Finserv Flexi Loan",
                    "provider": "Bajaj Finserv",
                    "category": "loans",
                    "category_label": "Flexible Drawdown Line",
                    "match_score": 91,
                    "headline": "Pay Interest Only on Drawn Funds • Flexible Prepayment",
                    "personalized_metric": f"Drawdown line up to ₹{flexi_limit} Lakhs",
                    "why_matched": "Sized conservatively at 75% of your maximum unsecured eligibility so idle reserve credit incurs zero interest.",
                    "apply_url": "https://www.bajajfinserv.in/personal-loan",
                }
            )
        else:
            loans.append(
                {
                    "id": "loan_gold",
                    "name": "Muthoot Gold Loan (Secured Fallback)",
                    "provider": "Muthoot Finance",
                    "category": "loans",
                    "category_label": "Rule-Engine Secured Fallback",
                    "match_score": 95,
                    "headline": "Asset-Backed Liquidity Without Unsecured FOIR or CIBIL Gates",
                    "personalized_metric": "9.90% – 14.00% p.a. • Unsecured limit: ₹0",
                    "why_matched": f"{loan_rec.headline}. Asset-backed credit avoids unsecured rejection while providing regulated liquidity.",
                    "apply_url": "https://www.muthootfinance.com/gold-loan",
                }
            )
            loans.append(
                {
                    "id": "loan_smfg",
                    "name": "SMFG India Credit Consolidation Review",
                    "provider": "SMFG India Credit",
                    "category": "loans",
                    "category_label": "Debt Restructuring",
                    "match_score": 84,
                    "headline": "Refinance High-Cost Obligations Before Taking New Debt",
                    "personalized_metric": "Unsecured borrowing paused until blockers clear",
                    "why_matched": "Use backward-chaining goal remediation on the dashboard to see the exact CIBIL, EMI, or income change needed to qualify.",
                    "apply_url": "https://www.smfgindiacredit.com/personal-loan.aspx",
                }
            )

        loans.append(
            {
                "id": "loan_sbi" if not loan_eligible else "loan_gold",
                "name": "SBI Secured Overdraft / Personal Credit" if not loan_eligible else "Muthoot Gold Loan (Asset Backed)",
                "provider": "State Bank of India" if not loan_eligible else "Muthoot Finance",
                "category": "loans",
                "category_label": "PSU Secured Option" if not loan_eligible else "Secured Credit",
                "match_score": 88 if not loan_eligible else 93,
                "headline": (
                    "FD-Backed Overdraft at ~1% Above Deposit Rate"
                    if not loan_eligible
                    else "Low-Rate Collateral Option Preserving Unsecured Headroom"
                ),
                "personalized_metric": (
                    "Secured against fixed deposits • Zero CIBIL gate"
                    if not loan_eligible
                    else "9.90% – 11.50% APR against gold collateral"
                ),
                "why_matched": (
                    "PSU bank overdraft against existing term deposits provides emergency liquidity when unsecured rules block new loans."
                    if not loan_eligible
                    else "Optional collateral-backed alternative when you prefer lower interest rates over unsecured borrowing."
                ),
                "apply_url": (
                    "https://sbi.bank.in/web/personal-banking/loans/personal-loans"
                    if not loan_eligible
                    else "https://www.muthootfinance.com/gold-loan"
                ),
            }
        )

        # ======================================================================
        # SECTION C: LIFE & HEALTH INSURANCE (3 Distinct Options, respecting RULE_INS_01..06)
        # ======================================================================
        if life_recommended:
            mult_text = f"{hlv_mult:.0f}x" if hlv_mult else "HLV"
            insurance.append(
                {
                    "id": "ins_lic",
                    "name": "LIC Tech Term Insurance",
                    "provider": "Life Insurance Corporation (LIC)",
                    "category": "insurance",
                    "category_label": "Pure Term Life Cover",
                    "match_score": 97,
                    "headline": "Pure Mortality Income Replacement Sized by RULE_INS_01",
                    "personalized_metric": f"₹{life_cover_cr:.2f} Crore Life Cover ({mult_text} annual income)",
                    "why_matched": f"Sized by the {mult_text} Human Life Value rule for age {age} with {dependents} dependent(s) relying on your income.",
                    "apply_url": "https://licindia.in/tech-term",
                }
            )
            insurance.append(
                {
                    "id": "ins_star",
                    "name": "Star Health Family Optima Floater",
                    "provider": "Star Health Insurance",
                    "category": "insurance",
                    "category_label": "Family Medical Floater",
                    "match_score": 95,
                    "headline": "Cashless Family Hospitalisation Shield (RULE_INS_02)",
                    "personalized_metric": f"₹{health_cover_lakhs} Lakhs Family Sum Insured",
                    "why_matched": f"Rule-engine family floater sizing (₹{health_cover_lakhs}L for age {age} with dependents) to ring-fence investments from hospital bills.",
                    "apply_url": "https://www.starhealth.in/health-insurance/family-health-optima/",
                }
            )
            if ins_rec.details.get("has_child_plan"):
                insurance.append(
                    {
                        "id": "ins_child",
                        "name": "HDFC Life Youngstar Udaan Child Plan",
                        "provider": "HDFC Life",
                        "category": "insurance",
                        "category_label": "Child Education Waiver",
                        "match_score": 94,
                        "headline": "University Corpus Shield with Premium Waiver Rider",
                        "personalized_metric": "Triggered by Child Education goal + dependents",
                        "why_matched": "RULE_INS_04 fired because your goal is Child Education with active dependents.",
                        "apply_url": "https://www.hdfclife.com/children-insurance-plans",
                    }
                )
            else:
                insurance.append(
                    {
                        "id": "ins_hdfc_term",
                        "name": "HDFC Life Click 2 Protect Super",
                        "provider": "HDFC Life",
                        "category": "insurance",
                        "category_label": "Term + Critical Illness Rider",
                        "match_score": 92,
                        "headline": "99.3% Claim Settlement Ratio with Critical Illness Accelerator",
                        "personalized_metric": f"₹{life_cover_cr:.2f} Crore Alternative Private Term Quote",
                        "why_matched": "Compare private-insurer critical illness & waiver riders against LIC for the same rule-sized mortality cover.",
                        "apply_url": "https://www.hdfclife.com/term-insurance-plans/click-2-protect-super",
                    }
                )
        else:
            # 0 dependents (or age >= 60 / income == 0): RULE_INS_01 did NOT recommend term life cover.
            insurance.append(
                {
                    "id": "ins_care_indiv",
                    "name": "Care Advantage Individual Health Plan",
                    "provider": "Care Health Insurance",
                    "category": "insurance",
                    "category_label": "Individual Medical Cover",
                    "match_score": 96,
                    "headline": "Individual Hospitalisation Cover with Unlimited Recharge",
                    "personalized_metric": f"₹{health_cover_lakhs} Lakhs Individual Cover • Sec 80D eligible",
                    "why_matched": (
                        f"With {dependents} dependents, term life cover is not required; RULE_INS_03 prioritizes ₹{health_cover_lakhs}L individual medical protection."
                    ),
                    "apply_url": "https://www.careinsurance.com/health-insurance-plans.html",
                }
            )
            insurance.append(
                {
                    "id": "ins_ergo_secure",
                    "name": "HDFC ERGO Optima Secure Health",
                    "provider": "HDFC ERGO",
                    "category": "insurance",
                    "category_label": "2X Day-1 Medical Shield",
                    "match_score": 93,
                    "headline": "Zero Room-Rent Capping + 2X Coverage from Day 1",
                    "personalized_metric": f"₹{health_cover_lakhs}L Base + Restore Cushion",
                    "why_matched": "Protects your own earning capacity and liquid investments against major surgery or prolonged hospitalisation.",
                    "apply_url": "https://www.hdfcergo.com/health-insurance/optima-secure",
                }
            )
            insurance.append(
                {
                    "id": "ins_nps",
                    "name": "National Pension System (NPS Tier-I)",
                    "provider": "PFRDA / eNPS",
                    "category": "insurance",
                    "category_label": "Longevity & Pension Shield",
                    "match_score": 91,
                    "headline": "Sovereign Retirement Corpus • Ultra-Low 0.09% Fee",
                    "personalized_metric": "Extra ₹50,000 Sec 80CCD(1B) tax deduction",
                    "why_matched": "Without dependents requiring mortality cover, channelling protection budgets into your own retirement annuity builds self-reliance.",
                    "apply_url": "https://enps.nsdl.com/eNPS/NationalPensionSystem.html",
                }
            )

        # ======================================================================
        # SECTION D: WEALTH & INVESTMENT PORTFOLIOS (3 Options, respecting RULE_INV_01..02)
        # ======================================================================
        sip_metric = f"~₹{sip_amount:,}/mo SIP" if sip_amount > 0 else "Build cash surplus first"
        investments.append(
            {
                "id": "inv_nifty",
                "name": "UTI Nifty 50 Index Fund",
                "provider": "UTI Mutual Fund",
                "category": "investments",
                "category_label": f"{risk_cat} Core Equity",
                "match_score": 96,
                "headline": "Low-Cost Passive Exposure to India's Top 50 Companies",
                "personalized_metric": f"{suggested_equity}% Equity Split • {sip_metric}",
                "why_matched": f"RULE_INV_01 classified your profile as {risk_cat} ({suggested_equity}% Equity) for age {age} and goal '{goal}'.",
                "apply_url": "https://www.utimf.com/mutual-fund-products/equity-funds/uti-nifty-50-index-fund",
            }
        )
        investments.append(
            {
                "id": "inv_hybrid",
                "name": "ICICI Prudential Balanced Advantage Fund",
                "provider": "Groww / ICICI Prudential AMC",
                "category": "investments",
                "category_label": "Dynamic Hybrid Guard",
                "match_score": 93,
                "headline": "Valuation-Driven Equity/Debt Rebalancing for Drawdown Control",
                "personalized_metric": f"Complements {100 - suggested_equity}% Debt & Gold sleeve",
                "why_matched": "Automatically trims equity when market P/E multiples stretch and adds equity during corrections.",
                "apply_url": "https://groww.in/mutual-funds/icici-prudential-balanced-advantage-fund-direct-growth",
            }
        )
        investments.append(
            {
                "id": "inv_ppf",
                "name": "Public Provident Fund (PPF)",
                "provider": "India Post / State Bank of India",
                "category": "investments",
                "category_label": "Sovereign Debt & Reserve",
                "match_score": 91,
                "headline": "Sovereign-Backed Fixed Income • EEE Tax-Exempt Interest",
                "personalized_metric": f"7.10% Tax-Free • ₹{emergency_buffer_lakhs}L Reserve Target",
                "why_matched": f"Anchors your {emergency_months:.0f}-month emergency target (₹{emergency_buffer_lakhs} Lakhs) and long-term fixed-income sleeve.",
                "apply_url": "https://www.indiapost.gov.in/Financial/Pages/Content/Post-Office-Saving-Schemes.aspx",
            }
        )

        all_products = cards + loans + insurance + investments

        return {
            "source": "deterministic_expert",
            "model": "WealthWise Neuro-Symbolic Rule Engine",
            "health_score": score,
            "health_tier": tier,
            "executive_summary": summary,
            "vital_metrics": {
                "debt_foir_pct": foir,
                "max_borrowing_lakhs": max_loan_lakhs,
                "recommended_life_cover_cr": life_cover_cr,
                "recommended_health_cover_lakhs": health_cover_lakhs,
                "recommended_emergency_months": emergency_months,
                "recommended_emergency_lakhs": emergency_buffer_lakhs,
            },
            "categorized_products": {
                "cards": cards,
                "loans": loans,
                "insurance": insurance,
                "investments": investments,
            },
            "recommended_products": all_products,
        }
