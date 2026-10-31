"""
WealthWise web server and REST API.

Local-only by default: requests must be addressed to a loopback name (blocks DNS rebinding),
cross-site browser requests are rejected, every POST needs the per-launch CSRF token, and all
input is validated before it reaches the inference engine or the Gemini bridge.
"""

from __future__ import annotations

import hmac
import io
import math
import os
import re
import secrets
import socket
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file
from pydantic import ValidationError

from advisor import AdvisoryExecutionResult, WealthExpertAdvisor
from core.security import AdvisoryRateLimiter, SecureUserProfileInput, validation_summary
from core.vitals import build_vitals, stress_scenario
from reports.dossier_generator import FinancialDossierPDFGenerator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOOPBACK_NAMES = {"127.0.0.1", "localhost", "::1"}
STRESS_FIELDS = {"monthly_income", "existing_emis", "rate_hike_bps", "income_drop_pct"}

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024  # 32 KB payload limit

# Random per launch; handed only to the page served from this origin and echoed back by the
# browser in the X-CSRF-Token header on every POST.
CSRF_TOKEN = secrets.token_urlsafe(32)

advisor = WealthExpertAdvisor()
rate_limiter = AdvisoryRateLimiter(max_requests=120, window_seconds=60.0)

# Most recent POST /api/analyze result, used when the PDF is requested with no query parameters.
latest_execution_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


# ==============================================================================
# Bind address and allowed Host headers
# ==============================================================================


def _detect_lan_ip() -> str | None:
    """Active outbound IPv4 interface address without transmitting packets."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            ip = sock.getsockname()[0]
            return ip if ip and ip != "0.0.0.0" else None
    except OSError:
        return None


def _strip_host(raw: str) -> str:
    host = raw.strip().lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def get_bind_address() -> tuple[str, int]:
    """Host and port from the environment.

    There is no login, so anything other than loopback has to be requested explicitly.
    """
    host = os.environ.get("WEALTHWISE_HOST", "127.0.0.1").strip() or "127.0.0.1"
    raw_port = os.environ.get("WEALTHWISE_PORT", "5000").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("WEALTHWISE_PORT must be an integer between 1 and 65535.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("WEALTHWISE_PORT must be between 1 and 65535.")
    if _strip_host(host) not in LOOPBACK_NAMES and os.environ.get("WEALTHWISE_ALLOW_REMOTE") != "1":
        raise SystemExit(
            f"Refusing to listen on {host}: WealthWise has no authentication and handles personal "
            "financial data. Set WEALTHWISE_ALLOW_REMOTE=1 only if you understand the risk."
        )
    return host, port


def allowed_hosts() -> set[str]:
    hosts = set(LOOPBACK_NAMES)
    configured = _strip_host(os.environ.get("WEALTHWISE_HOST", ""))
    if configured and configured not in ("0.0.0.0", "::"):
        hosts.add(configured)
    if os.environ.get("WEALTHWISE_ALLOW_REMOTE") == "1":
        extra = os.environ.get("WEALTHWISE_ALLOWED_HOSTS", "")
        for item in extra.split(","):
            cleaned = _strip_host(item)
            if cleaned:
                hosts.add(cleaned)
        if configured in ("0.0.0.0", "::"):
            lan_ip = _detect_lan_ip()
            if lan_ip:
                hosts.add(lan_ip.lower())
    return hosts


def request_hostname() -> str:
    """Hostname part of the Host header, without port or IPv6 brackets."""
    return _strip_host(request.host)


def _error(status: int, message: str):
    return jsonify({"error": message}), status


# ==============================================================================
# Request / response hardening
# ==============================================================================


@app.before_request
def security_filter():
    if request_hostname() not in allowed_hosts():
        return _error(403, "Unrecognised Host header.")

    if request.headers.get("Sec-Fetch-Site", "").strip().lower() == "cross-site":
        return _error(403, "Cross-site request rejected.")

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent.encode(), CSRF_TOKEN.encode()):
            return _error(403, "Missing or invalid CSRF token.")
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc.lower() != request.host.lower():
            return _error(403, "Cross-origin request rejected.")


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(400)
def bad_request(e):
    return _error(400, "The request contained invalid parameters.")


@app.errorhandler(404)
def not_found(e):
    return _error(404, "The requested resource does not exist.")


@app.errorhandler(405)
def method_not_allowed(e):
    return _error(405, "HTTP method is not allowed on this endpoint.")


@app.errorhandler(413)
def payload_too_large(e):
    return _error(413, "Request body exceeds the 32 KB limit.")


@app.errorhandler(500)
def internal_error(e):
    return _error(500, "An internal error occurred.")


def json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def too_many():
    return _error(429, "Rate limit exceeded (120 req/min). Please slow down.")


# ==============================================================================
# Pages
# ==============================================================================


@app.route("/")
def index():
    return render_template("index.html", csrf_token=CSRF_TOKEN)


# ==============================================================================
# API
# ==============================================================================


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Runs forward chaining and composite health scoring."""
    if not rate_limiter.allow_request():
        return too_many()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        return _error(400, "Invalid or missing JSON payload")

    try:
        user_input = SecureUserProfileInput(**payload)
    except ValidationError as e:
        return _error(422, f"Validation error: {validation_summary(e)}")

    try:
        result: AdvisoryExecutionResult = advisor.analyze(user_input)
    except Exception:
        app.logger.exception("Inference failed")
        return _error(500, "Inference execution failed.")

    with _cache_lock:
        latest_execution_cache["last_result"] = result

    domains_data = {}
    for key, rec in result.domains.items():
        domains_data[key] = {
            "module": rec.module,
            "eligible": rec.eligible,
            "headline": rec.headline,
            "certainty": rec.certainty,
            "confidence_label": rec.confidence_label,
            "details": rec.details,
            "products": [p.to_dict() for p in rec.products],
            "rule_traces": rec.rule_traces,
        }

    return jsonify(
        {
            "profile": result.profile,
            "fhi": {
                "composite_score": result.fhi.composite_score,
                "unclamped_raw_score": result.fhi.unclamped_raw_score,
                "solvency_score": result.fhi.solvency_score,
                "coverage_score": result.fhi.coverage_score,
                "liquidity_score": result.fhi.liquidity_score,
                "credit_score_normalized": result.fhi.credit_score_normalized,
                "tier_badge": result.fhi.tier_badge,
                "active_overrides": result.fhi.active_overrides,
                "radar_metrics": result.fhi.radar_metrics,
            },
            "domains": domains_data,
            "firing_history": [
                {
                    "rule_id": t.rule_id,
                    "domain": t.domain,
                    "description": t.description,
                    "priority": t.priority,
                    "asserted_facts": t.asserted_facts,
                    "premise_cf": t.premise_cf,
                }
                for t in result.firing_history
            ],
            "audit_record": result.audit_record,
            "vitals": build_vitals(result),
        }
    ), 200


@app.route("/api/gemini-advisory", methods=["POST"])
def api_gemini_advisory():
    """Product advisory from Google Gemini (when a key is supplied) or the offline advisor."""
    from core.gemini_advisor import GeminiAdvisor

    if not rate_limiter.allow_request():
        return too_many()
    # The key travels in a header only, never in the body, and is never stored by the server.
    api_key = request.headers.get("X-Gemini-Api-Key")
    try:
        return jsonify(GeminiAdvisor.analyze_profile(json_body(), api_key=api_key)), 200
    except Exception:
        app.logger.exception("Advisory failed")
        return _error(500, "Advisory generation failed.")


@app.route("/api/backward-chain", methods=["POST"])
def api_backward_chain():
    """Backward-chaining goal seek that returns verified counterfactual changes.

    Body: {"target_fact": "loan.eligible", "desired_value": true, "profile": {...}}
    `profile` is optional; without it the most recent /api/analyze result is used.
    """
    if not rate_limiter.allow_request():
        return too_many()

    raw = request.get_json(silent=True)
    if not isinstance(raw, dict):
        return _error(400, "Invalid or missing JSON payload")

    unknown = set(raw) - {"target_fact", "desired_value", "profile"}
    if unknown:
        return _error(422, "Unexpected fields in backward-chain request.")

    target_fact = raw.get("target_fact", "loan.eligible")
    desired_val: Any = raw.get("desired_value", True)
    if not isinstance(target_fact, str) or not 0 < len(target_fact) <= 80:
        return _error(400, "target_fact must be a non-empty string (max 80 chars)")
    allowed_str_goals = {"investment.risk_category": {"Conservative", "Moderate", "Aggressive"}}
    valid_desired = isinstance(desired_val, bool) or (
        target_fact in allowed_str_goals
        and isinstance(desired_val, str)
        and desired_val in allowed_str_goals[target_fact]
    )
    if not valid_desired:
        return _error(400, "desired_value must be true or false")

    profile = None
    if raw.get("profile") is not None:
        if not isinstance(raw["profile"], dict):
            return _error(422, "Validation error: profile must be an object")
        try:
            profile = SecureUserProfileInput(**raw["profile"])
        except ValidationError as e:
            return _error(422, f"Validation error: {validation_summary(e)}")

    try:
        return jsonify(advisor.seek_goal_remediation(target_fact, desired_val, profile)), 200
    except Exception:
        app.logger.exception("Goal seek failed")
        return _error(500, "Goal seek failed.")


@app.route("/api/stress-test", methods=["POST"])
def api_stress_test():
    """Applies a rate-hike and income-drop shock to cashflow and debt ratios."""
    if not rate_limiter.allow_request():
        return too_many()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error(400, "Invalid or missing JSON payload")
    if set(payload) - STRESS_FIELDS:
        return _error(422, "Unexpected fields in stress-test request")

    defaults = {
        "monthly_income": 50000.0,
        "existing_emis": 15000.0,
        "rate_hike_bps": 150.0,
        "income_drop_pct": 20.0,
    }
    parsed: dict[str, float] = {}
    for key, default in defaults.items():
        raw_val = payload.get(key, default)
        if isinstance(raw_val, bool):
            return _error(422, "Numeric fields required")
        try:
            parsed[key] = float(raw_val)
        except (TypeError, ValueError):
            return _error(422, "Numeric fields required")

    income = parsed["monthly_income"]
    emis = parsed["existing_emis"]
    rate_hike_bps = parsed["rate_hike_bps"]
    income_drop_pct = parsed["income_drop_pct"]

    if (
        not all(math.isfinite(v) for v in parsed.values())
        or income < 0
        or emis < 0
        or not 0 <= income_drop_pct <= 100
        or not 0 <= rate_hike_bps <= 2000
    ):
        return _error(422, "Values out of range")
    return jsonify(stress_scenario(income, emis, rate_hike_bps, income_drop_pct)), 200


@app.route("/api/export-pdf", methods=["GET"])
def api_export_pdf():
    """Builds the two-page PDF plan with its SHA-256 fingerprint (side-effect-free GET)."""
    if not rate_limiter.allow_request():
        return too_many()

    if "income" in request.args:
        # Live slider values: validate and fail loudly without mutating shared server cache.
        try:
            live_user = SecureUserProfileInput(
                name=request.args.get("name", "Client"),
                age=int(request.args.get("age", 28)),
                monthly_income=float(request.args.get("income", 120000)),
                credit_score=int(request.args.get("credit", 785)),
                employment_type=request.args.get("employment", "Salaried"),
                existing_emis=float(request.args.get("emis", 18000)),
                dependents=int(request.args.get("deps", 1)),
                financial_goal=request.args.get("goal", "Wealth Creation"),
                risk_tolerance=request.args.get("risk", "Medium"),
                preferred_spend_category=request.args.get("spend", "General"),
            )
        except (ValidationError, ValueError, TypeError) as e:
            return _error(422, f"Validation error: {validation_summary(e)}")
        last_res = advisor.analyze(live_user, record_session=False)
    else:
        with _cache_lock:
            last_res = latest_execution_cache.get("last_result")

    if not last_res:
        # Cold cache and no parameters: export a built-in demo client without mutating session state.
        default_user = SecureUserProfileInput(
            name="Demo Client",
            age=28,
            monthly_income=135000.0,
            credit_score=785,
            employment_type="Salaried",
            existing_emis=15000.0,
            dependents=1,
            financial_goal="Wealth Creation",
            risk_tolerance="High",
            preferred_spend_category="Travel",
        )
        last_res = advisor.analyze(default_user, record_session=False)

    try:
        pdf_bytes = FinancialDossierPDFGenerator.generate(last_res)
    except Exception:
        app.logger.exception("PDF generation failed")
        return _error(500, "PDF compilation error.")

    raw_name = str(last_res.profile.get("name", "Client"))
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_name).strip("_") or "Client"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"WealthWise_Plan_{safe_name}.pdf",
    )


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify(
        {
            "status": "HEALTHY",
            "engine": "WealthWise Neuro-Symbolic Expert System",
            "reasoning": ["Forward Chaining", "Backward Chaining", "MYCIN Certainty Factors"],
            "timestamp": time.time(),
        }
    ), 200
