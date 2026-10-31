"""
Authentic Financial Products Catalog with verified official links.
Static catalogue of products from RBI, SEBI and IRDAI regulated institutions. Check current terms with the provider.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Product:
    name: str
    provider: str
    category: str
    apply_url: str
    interest_or_cost: str
    key_benefit: str
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "provider": self.provider,
            "category": self.category,
            "apply_url": self.apply_url,
            "interest_or_cost": self.interest_or_cost,
            "key_benefit": self.key_benefit,
            "note": self.note
        }


# ==============================================================================
# 1. Loan Products by Credit Tier
# ==============================================================================

LOAN_CATALOG: dict[str, list[Product]] = {
    "excellent": [
        Product(
            name="XPRESS Personal Loan",
            provider="HDFC Bank",
            category="Personal Loan",
            apply_url="https://www.hdfcbank.com/personal/borrow/popular-loans/personal-loan",
            interest_or_cost="10.50% – 11.25% p.a.",
            key_benefit="10-second instant disbursal for pre-approved salaried professionals",
            note="Zero collateral required"
        ),
        Product(
            name="SBI Personal Loan (Xpress Credit)",
            provider="State Bank of India",
            category="Personal Loan",
            apply_url="https://sbi.bank.in/web/personal-banking/loans/personal-loans",
            interest_or_cost="11.15% – 12.00% p.a.",
            key_benefit="Lowest processing fee (0.50%) with zero hidden administrative charges",
            note="Sovereign PSU Bank reliability"
        )
    ],
    "good": [
        Product(
            name="ICICI Bank Instant Personal Loan",
            provider="ICICI Bank",
            category="Personal Loan",
            apply_url="https://www.icicibank.com/personal-banking/loans/personal-loan",
            interest_or_cost="12.50% – 13.50% p.a.",
            key_benefit="Paperless digital sanction up to ₹50 Lakh with flexible tenures",
            note="Flexible part-prepayment facility"
        ),
        Product(
            name="Bajaj Finserv Flexi Personal Loan",
            provider="Bajaj Finserv",
            category="Personal Loan",
            apply_url="https://www.bajajfinserv.in/personal-loan",
            interest_or_cost="13.00% – 14.50% p.a.",
            key_benefit="Withdraw cash whenever needed, pay interest only on utilized amount",
            note="Hybrid flexi-draw facility"
        )
    ],
    "fair": [
        Product(
            name="IDFC FIRST FIRSTmoney Loan",
            provider="IDFC FIRST Bank",
            category="Personal Loan",
            apply_url="https://www.idfcfirstbank.com/personal-banking/loans/personal-loan",
            interest_or_cost="14.50% – 16.50% p.a.",
            key_benefit="Lenient assessment for emerging credit profiles and self-employed",
            note="Transparent pricing with zero foreclosure charges"
        ),
        Product(
            name="SMFG India Credit Personal Loan",
            provider="SMFG India Credit",
            category="Personal Loan",
            apply_url="https://www.smfgindiacredit.com/personal-loan.aspx",
            interest_or_cost="15.50% – 18.00% p.a.",
            key_benefit="Customized underwriting with quick turn-around time for Tier-2 cities",
            note="Tailored for credit scores 650-699"
        )
    ],
    "secured_fallback": [
        Product(
            name="Muthoot Gold Loan (Secured Credit)",
            provider="Muthoot Finance",
            category="Secured Gold Loan",
            apply_url="https://www.muthootfinance.com/gold-loan",
            interest_or_cost="9.90% – 14.00% p.a.",
            key_benefit="Guaranteed approval with zero CIBIL score checks; builds credit history",
            note="Immediate liquidity against gold ornaments"
        )
    ]
}


# ==============================================================================
# 2. Insurance Products
# ==============================================================================

INSURANCE_CATALOG: dict[str, list[Product]] = {
    "term_life": [
        Product(
            name="Tech Term Insurance",
            provider="Life Insurance Corporation of India (LIC)",
            category="Term Life Protection",
            apply_url="https://licindia.in/tech-term",
            interest_or_cost="From ₹7,500/year (₹1 Cr cover)",
            key_benefit="98.5% claim settlement ratio backed by sovereign guarantee",
            note="Pure protection plan, Section 80C tax deduction"
        ),
        Product(
            name="Click 2 Protect Super",
            provider="HDFC Life",
            category="Term Life Protection",
            apply_url="https://www.hdfclife.com/term-insurance-plans/click-2-protect-super",
            interest_or_cost="From ₹8,200/year (₹1 Cr cover)",
            key_benefit="Comprehensive critical illness accelerator and terminal illness rider",
            note="99.3% claim settlement ratio"
        )
    ],
    "health_family": [
        Product(
            name="Optima Secure (Family Floater)",
            provider="HDFC ERGO",
            category="Health Insurance",
            apply_url="https://www.hdfcergo.com/health-insurance/optima-secure",
            interest_or_cost="From ₹14,000/year (₹10L sum insured)",
            key_benefit="2X coverage from Day 1 at zero extra cost + 4X restore benefit",
            note="Zero room-rent capping, cashless across 12,000+ hospitals"
        ),
        Product(
            name="Family Health Optima",
            provider="Star Health Insurance",
            category="Health Insurance",
            apply_url="https://www.starhealth.in/health-insurance/family-health-optima/",
            interest_or_cost="From ₹12,500/year (₹10L sum insured)",
            key_benefit="Dedicated in-house claim settlement team with air ambulance cover",
            note="Comprehensive family medical safeguard"
        )
    ],
    "health_individual": [
        Product(
            name="Care Advantage Health Plan",
            provider="Care Health Insurance",
            category="Individual Health Insurance",
            apply_url="https://www.careinsurance.com/health-insurance-plans.html",
            interest_or_cost="From ₹6,800/year (₹5L sum insured)",
            key_benefit="Annual health checkups and unlimited automatic recharge of sum insured",
            note="Section 80D tax exemption up to ₹25,000"
        )
    ],
    "child_education": [
        Product(
            name="Youngstar Udaan Child Plan",
            provider="HDFC Life",
            category="Child Education Endowment",
            apply_url="https://www.hdfclife.com/children-insurance-plans",
            interest_or_cost="Premium waiver on death",
            key_benefit="Guaranteed payouts during university admission years (ages 18-22)",
            note="Ring-fenced educational corpus"
        )
    ],
    "retirement_pension": [
        Product(
            name="National Pension System (NPS Tier-I)",
            provider="PFRDA / eNPS",
            category="Retirement Pension",
            apply_url="https://enps.nsdl.com/eNPS/NationalPensionSystem.html",
            interest_or_cost="Low fund management charge (0.09%)",
            key_benefit="Exclusive ₹50,000 tax deduction under Sec 80CCD(1B) over Section 80C",
            note="Government sovereign retirement vehicle"
        )
    ]
}


# ==============================================================================
# 3. Investment Platforms & Strategic Funds
# ==============================================================================

INVESTMENT_CATALOG: dict[str, list[Product]] = {
    "conservative": [
        Product(
            name="Public Provident Fund (PPF)",
            provider="India Post / Nationalized Banks",
            category="Government Sovereign Debt",
            apply_url="https://www.indiapost.gov.in/Financial/Pages/Content/Post-Office-Saving-Schemes.aspx",
            interest_or_cost="7.10% p.a. (Tax-Free EEE)",
            key_benefit="100% principal safety backed by Union Govt; zero market volatility",
            note="15-year statutory compounding wealth vehicle"
        ),
        Product(
            name="HDFC Short Term Debt Fund",
            provider="Groww Mutual Funds",
            category="Corporate Bond / Debt Fund",
            apply_url="https://groww.in/mutual-funds/hdfc-short-term-debt-fund-direct-growth",
            interest_or_cost="7.40% – 7.80% annualized",
            key_benefit="High liquidity with low interest rate sensitivity; superior to bank FD",
            note="High credit quality portfolio"
        )
    ],
    "moderate": [
        Product(
            name="ICICI Prudential Balanced Advantage Fund",
            provider="Groww / Zerodha Coin",
            category="Hybrid Dynamic Asset Allocation",
            apply_url="https://groww.in/mutual-funds/icici-prudential-balanced-advantage-fund-direct-growth",
            interest_or_cost="12.00% – 14.00% 5Y CAGR",
            key_benefit="Automatically shifts between equity and debt using in-house P/E valuation",
            note="Downside protection during stock market crashes"
        ),
        Product(
            name="NPS Auto Choice (Life Cycle Fund LC-50)",
            provider="PFRDA eNPS",
            category="Balanced Pension Asset Allocation",
            apply_url="https://enps.nsdl.com/eNPS/NationalPensionSystem.html",
            interest_or_cost="10.50% – 12.00% annualized",
            key_benefit="Gradually tapers equity exposure as you age to preserve capital",
            note="Disciplined long-term wealth accumulation"
        )
    ],
    "aggressive": [
        Product(
            name="UTI Nifty 50 Index Fund (Direct)",
            provider="Zerodha Coin / Groww",
            category="Large Cap Passive Equity",
            apply_url="https://coin.zerodha.com/",
            interest_or_cost="13.50% – 15.00% 10Y CAGR",
            key_benefit="Ultra-low expense ratio (0.05%); owns the top 50 bluechip companies of India",
            note="Core compounding engine for young investors"
        ),
        Product(
            name="Parag Parikh Flexi Cap Fund (Direct)",
            provider="PPFAS Mutual Fund / Groww",
            category="Diversified Global Equity",
            apply_url="https://groww.in/mutual-funds/parag-parikh-long-term-equity-fund-direct-growth",
            interest_or_cost="18.00%+ 5Y CAGR",
            key_benefit="Value investing with exposure to international tech leaders (Alphabet, Microsoft)",
            note="Top-rated alpha generating equity fund"
        )
    ]
}


# ==============================================================================
# 4. Credit Cards by Tier and Lifestyle Category
# ==============================================================================

CREDIT_CARD_CATALOG: dict[str, list[Product]] = {
    "super_premium": [
        Product(
            name="HDFC Infinia Metal Edition",
            provider="HDFC Bank",
            category="Ultra-Luxury Travel & Rewards",
            apply_url="https://www.hdfcbank.com/personal/pay/cards/credit-cards/infinia-credit-card",
            interest_or_cost="Annual Fee: ₹12,500",
            key_benefit="3.3% base reward rate + up to 33% reward points via SmartBuy flight/hotel bookings",
            note="Unlimited complimentary airport lounge access worldwide"
        ),
        Product(
            name="Axis Bank Magnus Card",
            provider="Axis Bank",
            category="Luxury Lifestyle & Dining",
            apply_url="https://www.axisbank.com/retail/cards/credit-card/axis-bank-magnus-card",
            interest_or_cost="Annual Fee: ₹12,500",
            key_benefit="Exclusive airport concierge service and complimentary flight transfers",
            note="Designed for annual spends > ₹15 Lakhs"
        )
    ],
    "upper_mid": [
        Product(
            name="HDFC Regalia Gold Credit Card",
            provider="HDFC Bank",
            category="Premium Travel & Shopping",
            apply_url="https://www.hdfcbank.com/personal/pay/cards/credit-cards/regalia-gold-credit-card",
            interest_or_cost="Annual Fee: ₹2,500",
            key_benefit="12 domestic airport lounge visits + ₹1,500 Marks & Spencer / Myntra vouchers",
            note="Fee waived on ₹4 Lakh annual spend"
        ),
        Product(
            name="SBI Card PRIME",
            provider="SBI Card",
            category="Lifestyle & Utilities",
            apply_url="https://www.sbicard.com/en/personal/credit-cards/lifestyle/sbi-card-prime.page",
            interest_or_cost="Annual Fee: ₹2,999",
            key_benefit="20 reward points per ₹100 on utility bill payments and standing instructions",
            note="Complimentary Priority Pass membership"
        )
    ],
    "mid": [
        Product(
            name="Amazon Pay ICICI Credit Card",
            provider="ICICI Bank",
            category="Online Shopping & Cashback",
            apply_url="https://www.icicibank.com/personal-banking/cards/credit-card/amazon-pay-credit-card",
            interest_or_cost="Lifetime Free (₹0 Annual Fee)",
            key_benefit="Flat 5% unlimited cashback for Amazon Prime members directly into wallet",
            note="Zero joining fee, zero annual renewal fee"
        ),
        Product(
            name="HDFC Millennia Credit Card",
            provider="HDFC Bank",
            category="Cashback & Digital Spends",
            apply_url="https://www.hdfcbank.com/personal/pay/cards/credit-cards/millennia-credit-card",
            interest_or_cost="Annual Fee: ₹1,000",
            key_benefit="5% cashback on Amazon, Flipkart, Swiggy, Zomato, Uber, BookMyShow",
            note="Fee waived on ₹1 Lakh spend"
        ),
        Product(
            name="SBI SimplyCLICK Credit Card",
            provider="SBI Card",
            category="E-commerce & Dining",
            apply_url="https://www.sbicard.com/en/personal/credit-cards/shopping/simplyclick-sbi-card.page",
            interest_or_cost="Annual Fee: ₹499",
            key_benefit="10X reward points on partner e-commerce merchants (Cleartrip, Lenskart)",
            note="Instant Amazon gift voucher upon joining"
        )
    ],
    "entry_or_secured": [
        Product(
            name="IDFC FIRST WOW Credit Card",
            provider="IDFC FIRST Bank",
            category="Credit Rebuilder (FD Backed)",
            apply_url="https://www.idfcfirstbank.com/credit-card/wow",
            interest_or_cost="Lifetime Free (FD from ₹2,000)",
            key_benefit="Guaranteed approval with 0 credit score requirement; 100% CIBIL reporting to rebuild score",
            note="Earn up to 7.5% interest on backing Fixed Deposit"
        )
    ]
}
