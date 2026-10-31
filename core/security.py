"""
Security Module for Financial Advisory Expert System.
Implements strict input validation, sanitization, rate-limiting, and SHA-256 fingerprinting.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ==============================================================================
# 1. Pydantic Security Schema with Strict Boundaries
# ==============================================================================

# Single source of truth for the categorical inputs; the advisor's counterfactual
# search reuses these so it only ever proposes values the validators accept.
ALLOWED_EMPLOYMENT = ("Salaried", "Self-Employed", "Business Owner", "Student", "Unemployed")
ALLOWED_GOALS = (
    "Wealth Creation",
    "Retirement Planning",
    "Child Education",
    "Tax Saving",
    "Emergency Fund",
    "Home Purchase",
    "Debt Free",
)
ALLOWED_RISK = ("Low", "Medium", "High")
ALLOWED_SPEND = ("General", "Travel", "Online Shopping", "Fuel & Commute", "Dining & Lifestyle")


class SecureUserProfileInput(BaseModel):
    """Strictly validated user profile input conforming to RBI / banking norms."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        default="Valued Client",
        min_length=2,
        max_length=60,
        description="Client legal name or pseudonym",
    )
    age: int = Field(
        ...,
        ge=18,
        le=100,
        description="Age must be between 18 and 100 years",
    )
    monthly_income: float = Field(
        ...,
        ge=0.0,
        le=100_000_000.0,
        description="Monthly verifiable income in INR (0 to 10 Cr)",
    )
    credit_score: int = Field(
        ...,
        ge=300,
        le=900,
        description="CIBIL / Experian credit score range: 300 to 900",
    )
    employment_type: str = Field(
        ...,
        description="Employment status",
    )
    existing_emis: float = Field(
        default=0.0,
        ge=0.0,
        le=50_000_000.0,
        description="Total existing monthly debt obligations",
    )
    dependents: int = Field(
        default=0,
        ge=0,
        le=20,
        description="Number of financially dependent individuals",
    )
    financial_goal: str = Field(
        ...,
        description="Primary financial milestone",
    )
    risk_tolerance: str = Field(
        ...,
        description="Self-assessed psychological risk tolerance",
    )
    preferred_spend_category: str = Field(
        default="General",
        description="Dominant card spending category",
    )
    requested_loan_amount: float | None = Field(
        default=None,
        ge=0.0,
        le=500_000_000.0,
        description="Optional loan amount requested for eligibility test",
    )

    @field_validator(
        "age",
        "monthly_income",
        "credit_score",
        "existing_emis",
        "dependents",
        "requested_loan_amount",
        mode="before",
    )
    @classmethod
    def reject_booleans(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("Boolean values are not valid numeric inputs")
        return v

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        # Prevent XSS / command injection
        cleaned = re.sub(r"[^\w\s\.\-]", "", v).strip()
        if not cleaned:
            return "Valued Client"
        return cleaned[:60]

    @field_validator("employment_type")
    @classmethod
    def validate_employment(cls, v: str) -> str:
        v_clean = v.strip().title()
        if v_clean not in ALLOWED_EMPLOYMENT:
            raise ValueError(f"Invalid employment type '{v}'. Must be one of: {ALLOWED_EMPLOYMENT}")
        return v_clean

    @field_validator("financial_goal")
    @classmethod
    def validate_goal(cls, v: str) -> str:
        v_clean = v.strip()
        if v_clean not in ALLOWED_GOALS:
            for item in ALLOWED_GOALS:
                if item.lower() == v_clean.lower():
                    return item
            raise ValueError(f"Invalid financial goal '{v}'. Must be one of: {ALLOWED_GOALS}")
        return v_clean

    @field_validator("risk_tolerance")
    @classmethod
    def validate_risk(cls, v: str) -> str:
        v_clean = v.strip().capitalize()
        if v_clean not in ALLOWED_RISK:
            raise ValueError(f"Invalid risk tolerance '{v}'. Must be Low, Medium, or High")
        return v_clean

    @field_validator("preferred_spend_category")
    @classmethod
    def validate_spend_category(cls, v: str) -> str:
        v_clean = v.strip()
        for item in ALLOWED_SPEND:
            if item.lower() == v_clean.lower():
                return item
        return "General"


def clean_advisory_profile(raw: Any) -> dict[str, Any]:
    """Coerce an untrusted advisory request into plain, bounded values.

    The Gemini endpoint accepts partial profiles, so it cannot use the strict model above.
    Numbers are clamped, categorical fields must match an allowlist, and nothing free-form
    survives, which also keeps arbitrary text out of the LLM prompt.
    """
    raw = raw if isinstance(raw, dict) else {}

    def number(key: str, default: float, low: float, high: float) -> float:
        candidate = raw.get(key, default)
        if isinstance(candidate, bool):
            return default
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            return default
        return min(max(value, low), high) if math.isfinite(value) else default

    credit = int(number("credit_score", 785, 300, 900))
    goal = raw.get("financial_goal")
    spend = raw.get("preferred_spend_category")
    employment = raw.get("employment_type")
    risk = raw.get("risk_tolerance")
    default_risk = "High" if credit >= 750 else "Medium"

    return {
        "monthly_income": number("monthly_income", 120000.0, 0.0, 100_000_000.0),
        "existing_emis": number("existing_emis", 18000.0, 0.0, 50_000_000.0),
        "credit_score": credit,
        "age": int(number("age", 28, 18, 100)),
        "dependents": int(number("dependents", 1, 0, 20)),
        "employment_type": employment if employment in ALLOWED_EMPLOYMENT else "Salaried",
        "risk_tolerance": risk if risk in ALLOWED_RISK else default_risk,
        "financial_goal": goal if goal in ALLOWED_GOALS else "Wealth Creation",
        "preferred_spend_category": spend if spend in ALLOWED_SPEND else "General",
    }


def validation_summary(exc: Exception) -> str:
    """Field names and messages only, never the submitted values."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return "Invalid input."
    parts = []
    for item in errors()[:5]:
        field = ".".join(str(x) for x in item.get("loc", ())) or "input"
        parts.append(f"{field}: {item.get('msg', 'invalid')}")
    return "; ".join(parts) or "Invalid input."


# ==============================================================================
# 2. Integrity Fingerprint (SHA-256 Digest)
# ==============================================================================


class EvidenceFingerprint:
    """Computes SHA-256 digests of intake data and advice.

    They show whether content changed, but are not signatures: anyone can recompute them.
    """

    @staticmethod
    def compute_sha256(data: Any) -> str:
        """Serialize data deterministically and calculate hex SHA-256."""
        if hasattr(data, "to_dict"):
            canonical_obj = data.to_dict()
        elif hasattr(data, "model_dump"):
            canonical_obj = data.model_dump()
        elif isinstance(data, dict):
            canonical_obj = data
        else:
            canonical_obj = str(data)

        canonical_json = json.dumps(canonical_obj, sort_keys=True, default=str)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    @staticmethod
    def create_audit_record(profile_dict: dict[str, Any], results_summary: dict[str, Any]) -> dict[str, Any]:
        """Generates an immutable, timestamped audit block."""
        timestamp = time.time()
        payload = {
            "timestamp": timestamp,
            "profile": profile_dict,
            "summary": results_summary,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        return {
            "timestamp": timestamp,
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(timestamp)),
            "sha256_fingerprint": digest,
            "status": "SHA256_FINGERPRINTED",
            "algorithm": "SHA-256 / RFC-6234",
        }


# ==============================================================================
# 3. Rate Limiting & Anti-Abuse Sentinel
# ==============================================================================


class AdvisoryRateLimiter:
    """In-memory sliding window rate limiter to prevent computational denial-of-service."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.history: list[float] = []
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        now = time.time()
        with self._lock:
            self.history = [t for t in self.history if now - t < self.window_seconds]
            if len(self.history) < self.max_requests:
                self.history.append(now)
                return True
            return False
