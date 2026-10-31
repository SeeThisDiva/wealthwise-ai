"""
Data Package: Verified Product Catalogs and Institutional Metadata.
"""

from data.catalog import CREDIT_CARD_CATALOG, INSURANCE_CATALOG, INVESTMENT_CATALOG, LOAN_CATALOG, Product

__all__ = [
    "Product",
    "LOAN_CATALOG",
    "INSURANCE_CATALOG",
    "INVESTMENT_CATALOG",
    "CREDIT_CARD_CATALOG"
]
