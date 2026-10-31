"""
Command Line Workstation (CLI) for Wealth Advisory Expert System.
Enables rapid terminal-based symbolic inference, backward chaining queries,
and PDF plan generation without launching a browser.
"""

from __future__ import annotations

import argparse
import sys

# Ensure Windows terminal outputs Unicode correctly (Rupee symbol, emojis)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from advisor import WealthExpertAdvisor
from core.security import SecureUserProfileInput
from reports.dossier_generator import FinancialDossierPDFGenerator


def print_banner():
    banner = r"""
  __          __        _ _   _              _____ 
  \ \        / /       | | | | |       /\   |_   _|
   \ \  /\  / /__  __ _| | |_| |__    /  \    | |  
    \ \/  \/ / _ \/ _` | | __| '_ \  / /\ \   | |  
     \  /\  /  __/ (_| | | |_| | | |/ ____ \ _| |_ 
      \/  \/ \___|\__,_|_|\__|_| |_/_/    \_\_____|
    Autonomous Personal Wealth & Estate Expert System
    [Deterministic Forward/Backward Chaining • MYCIN CF]
    """
    print(banner)


def run_cli():
    print_banner()

    parser = argparse.ArgumentParser(description="Wealth.AI Terminal Advisory Workstation")
    parser.add_argument("--name", type=str, default="Aarav Sharma", help="Client name")
    parser.add_argument("--age", type=int, default=28, help="Client age")
    parser.add_argument("--income", type=float, default=125000.0, help="Verifiable monthly income in INR")
    parser.add_argument("--credit-score", type=int, default=775, help="CIBIL credit score (300-900)")
    parser.add_argument("--employment", type=str, default="Salaried", help="Employment type")
    parser.add_argument("--emis", type=float, default=15000.0, help="Existing monthly EMIs")
    parser.add_argument("--dependents", type=int, default=1, help="Number of dependents")
    parser.add_argument("--goal", type=str, default="Wealth Creation", help="Primary financial goal")
    parser.add_argument("--risk", type=str, default="High", help="Risk tolerance (Low/Medium/High)")
    parser.add_argument("--spend", type=str, default="Travel", help="Dominant spend category")
    parser.add_argument("--pdf", type=str, default=None, help="Output PDF file path")
    parser.add_argument("--seek-goal", type=str, default=None, help="Run backward chaining for goal")

    args = parser.parse_args()

    # 1. Validate Input
    try:
        user_input = SecureUserProfileInput(
            name=args.name,
            age=args.age,
            monthly_income=args.income,
            credit_score=args.credit_score,
            employment_type=args.employment,
            existing_emis=args.emis,
            dependents=args.dependents,
            financial_goal=args.goal,
            risk_tolerance=args.risk,
            preferred_spend_category=args.spend
        )
    except Exception as e:
        print(f"\n[SECURITY BOUNDARY ERROR] {e}")
        sys.exit(1)

    # 2. Run Advisory
    advisor = WealthExpertAdvisor()
    print(f"[*] Executing Symbolic Inference for '{user_input.name}'...")
    result = advisor.analyze(user_input)

    # 3. Print Results
    fhi = result.fhi
    print("\n" + "="*70)
    print(f" FINANCIAL HEALTH INDEX (FHI): {fhi.composite_score:.1f} / 100  [{fhi.tier_badge}]")
    print(f" Raw Unclamped: {fhi.unclamped_raw_score:.1f} | Active Overrides: {len(fhi.active_overrides)}")
    for ov in fhi.active_overrides:
        print(f"   ! OVERRIDE: {ov}")
    print("="*70)
    print(f" Solvency: {fhi.solvency_score:.0f}%  |  Coverage: {fhi.coverage_score:.0f}%  |  Liquidity: {fhi.liquidity_score:.0f}%  |  Credit: {fhi.credit_score_normalized:.0f}%")
    print("="*70)

    print("\nDOMAIN ADVISORY VERDICTS:")
    for _dom_key, rec in result.domains.items():
        status = "[PASS]" if rec.eligible else "[REJECT/SECURED]"
        print(f"\n{status} {rec.module.upper()}")
        print(f"  Verdict:    {rec.headline}")
        print(f"  Certainty:  {rec.certainty:+.2f} ({rec.confidence_label})")
        if rec.products:
            print("  Products:   " + ", ".join([f"{p.name} ({p.provider})" for p in rec.products[:2]]))

    print("\n" + "="*70)
    print(f" SHA-256 FINGERPRINT: {result.audit_record.get('sha256_fingerprint')}")
    print(f" Production Rules Fired: {len(result.firing_history)}")
    print("="*70)

    # 4. Backward Chaining Goal Seek
    if args.seek_goal:
        print(f"\n[*] Running Backward Chaining Goal-Seek for '{args.seek_goal}'...")
        remediation = advisor.seek_goal_remediation(args.seek_goal, True)
        if remediation["achieved"]:
            print(f"  [ALREADY ACHIEVED] {remediation['message']}")
        else:
            print("  [ACTIONABLE REMEDIATION PLAN]:")
            for idx, step in enumerate(remediation["remediation_plan"], 1):
                print(f"   {idx}. {step}")
            if remediation["plan_verified"]:
                print("  [VERIFIED] Re-running the rules with the primary changes applied makes the goal true.")
            else:
                print("  [NOT VERIFIED] " + remediation["message"])

    # 5. Export PDF
    if args.pdf:
        pdf_bytes = FinancialDossierPDFGenerator.generate(result)
        with open(args.pdf, "wb") as f:
            f.write(pdf_bytes)
        print(f"\n[+] Court-ready PDF dossier successfully exported to: {args.pdf}")


if __name__ == "__main__":
    run_cli()
