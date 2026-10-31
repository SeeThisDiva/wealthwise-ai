"""
WealthWise Clean Executive Financial Plan PDF Generator.
Builds an approachable, structured 2-page personal wealth plan derived directly
from AdvisoryExecutionResult and core.vitals (single source of truth), with
XML-escaped text and a SHA-256 fingerprint of the inputs and results.
"""

from __future__ import annotations

import io
import time
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from advisor import AdvisoryExecutionResult
from core.vitals import build_vitals, stress_scenario


def _esc(value: Any) -> str:
    """Escape dynamic text for ReportLab's XML Paragraph parser."""
    return xml_escape("" if value is None else str(value), {'"': "&quot;", "'": "&#39;"})


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that sets neutral PDF metadata and renders total page numbers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        self.setTitle("WealthWise Personal Financial Plan")
        self.setAuthor("WealthWise")
        self.setSubject("Personal Financial Plan")
        self.setCreator("WealthWise")
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#94a3b8"))
        self.drawString(36, 22, "WealthWise Personal Financial Plan • Private & Confidential")
        self.drawRightString(612 - 36, 22, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


class FinancialDossierPDFGenerator:
    """Generates a clean, beginner-friendly 2-page Personal Financial Plan."""

    @classmethod
    def generate(cls, result: AdvisoryExecutionResult) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
            title="WealthWise Personal Financial Plan",
            author="WealthWise",
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "PlanTitle",
            parent=styles["Heading1"],
            fontSize=19,
            leading=23,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
            spaceAfter=2,
        )
        subtitle_style = ParagraphStyle(
            "PlanSubtitle",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#059669"),
            fontName="Helvetica-Bold",
            spaceAfter=8,
        )
        section_heading = ParagraphStyle(
            "PlanSectionHeading",
            parent=styles["Heading2"],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
            spaceBefore=6,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "PlanBody",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
            fontName="Helvetica",
        )
        body_bold = ParagraphStyle(
            "PlanBodyBold",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
        )
        footer_text = ParagraphStyle(
            "PlanFooter",
            parent=styles["Normal"],
            fontSize=7,
            leading=10,
            textColor=colors.HexColor("#94a3b8"),
            fontName="Helvetica",
        )

        story: list[Any] = []

        # Single source of truth: read every figure from AdvisoryExecutionResult & build_vitals
        vitals = build_vitals(result)
        profile = result.profile
        income = float(profile.get("monthly_income", 100000))
        emis = float(profile.get("existing_emis", 15000))
        surplus = max(0.0, income - emis)
        cibil = int(profile.get("credit_score", 750))
        age = int(profile.get("age", 30))
        dependents = int(profile.get("dependents", 0))
        goal = str(profile.get("financial_goal", "Wealth Creation"))
        spend = str(profile.get("preferred_spend_category", "Online Shopping"))
        client_name = str(profile.get("name", "Client"))
        date_str = time.strftime("%B %d, %Y")

        foir = float(vitals["foir"]["pct"])
        borrowing = vitals["borrowing"]
        loan_eligible = borrowing["state"] == "eligible"
        max_loan_lakhs = round(float(borrowing["max_amount"]) / 100_000.0, 2)
        loan_rate_note = str(borrowing.get("interest_rate") or "N/A").split(" (")[0]

        life_cover = vitals["life_cover"]
        life_recommended = bool(life_cover["recommended"])
        life_cover_cr = round(float(life_cover["amount"]) / 10_000_000.0, 2)
        hlv_mult = life_cover["annual_income_multiple"]

        ins_rec = result.domains.get("insurance")
        health_sum = float(ins_rec.details.get("health_sum_insured", 500_000.0)) if ins_rec else 500_000.0
        health_lakhs = int(round(health_sum / 100_000.0))

        reserve = vitals["emergency_reserve"]
        emergency_months = float(reserve["months"])
        emergency_lakhs = round(float(reserve["target_amount"]) / 100_000.0, 2)

        fhi = result.fhi
        score = fhi.composite_score
        tier = fhi.tier_badge

        # =========================================================================
        # PAGE 1: HEADER & CLIENT SNAPSHOT
        # =========================================================================
        story.append(Paragraph("WEALTHWISE PERSONAL FINANCIAL PLAN", title_style))
        story.append(
            Paragraph(
                f"PERSONALIZED ROADMAP PREPARED FOR {_esc(client_name.upper())} • {_esc(date_str.upper())}",
                subtitle_style,
            )
        )
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#059669"), spaceAfter=8))

        cibil_tier = (
            "Excellent (Prime)"
            if cibil >= 750
            else ("Good" if cibil >= 700 else ("Fair" if cibil >= 650 else "Subprime"))
        )
        snapshot_data = [
            [
                Paragraph(f"<b>Monthly Take-Home Income:</b> ₹{income:,.0f}", body_style),
                Paragraph(f"<b>Current Loan EMIs:</b> ₹{emis:,.0f}", body_style),
                Paragraph(f"<b>Net Leftover Monthly Cashflow:</b> ₹{surplus:,.0f}", body_style),
            ],
            [
                Paragraph(f"<b>CIBIL Credit Score:</b> {cibil} ({_esc(cibil_tier)})", body_style),
                Paragraph(f"<b>Age / Dependents:</b> {age} yrs • {dependents} dependent(s)", body_style),
                Paragraph(f"<b>Primary Life Goal:</b> {_esc(goal)}", body_style),
            ],
        ]
        t_snapshot = Table(snapshot_data, colWidths=[180, 180, 180])
        t_snapshot.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(t_snapshot)
        story.append(Spacer(1, 10))

        # SECTION 1: HEALTH SCORE
        story.append(Paragraph("1. YOUR FINANCIAL HEALTH AT A GLANCE", section_heading))

        score_color = "#059669" if score >= 80 else ("#0284c7" if score >= 60 else "#d97706")
        score_bg = "#ecfdf5" if score >= 80 else ("#f0f9ff" if score >= 60 else "#fffbeb")
        score_box_border = "#a7f3d0" if score >= 80 else ("#bae6fd" if score >= 60 else "#fde68a")

        summary_text = _esc(vitals["summary"]["body"])
        if fhi.active_overrides:
            overrides_str = "; ".join(_esc(o) for o in fhi.active_overrides)
            summary_text += f"<br/><font color='#b45309'><b>Protective Ceilings Applied:</b> {overrides_str}</font>"

        score_card_data = [
            [
                Paragraph(
                    f"<font size='26' color='{score_color}'><b>{score}</b></font>"
                    f"<font size='12' color='#64748b'>/100</font><br/>"
                    f"<font size='9' color='{score_color}'><b>{_esc(tier)}</b></font>",
                    body_bold,
                ),
                Paragraph(
                    f"<b>{_esc(vitals['summary']['headline'])}:</b><br/>{summary_text}",
                    body_style,
                ),
            ]
        ]
        t_score = Table(score_card_data, colWidths=[120, 420])
        t_score.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(score_bg)),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(score_box_border)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(t_score)
        story.append(Spacer(1, 10))

        # 4 Vitals Grid
        foir_state = vitals["foir"]["status"]
        if foir_state == "safe":
            foir_status_label = "Safe (Low loan burden)"
            foir_color = "#059669"
        elif foir_state == "moderate":
            foir_status_label = "Moderate (Within 50% limit)"
            foir_color = "#d97706"
        else:
            foir_status_label = "Critical (Over 50% limit)"
            foir_color = "#dc2626"

        if loan_eligible:
            borrowing_val = f"₹{max_loan_lakhs} Lakhs"
            borrowing_sub = f"<font size='7.5' color='#0284c7'>Pre-qualified @ {_esc(loan_rate_note)}</font>"
        else:
            borrowing_val = "Not Eligible"
            borrowing_sub = "<font size='7.5' color='#dc2626'>Unsecured rule gate active</font>"

        if life_recommended:
            life_val = f"₹{life_cover_cr:.2f} Crore"
            mult_label = f"{hlv_mult:.0f}x annual income cover" if hlv_mult else "HLV mortality cover"
            life_sub = f"<font size='7.5' color='#059669'>{_esc(mult_label)}</font>"
        else:
            life_val = "Not Required"
            life_reason = "No dependents on this income" if dependents == 0 else "Outside term-life window"
            life_sub = f"<font size='7.5' color='#64748b'>{_esc(life_reason)}</font>"

        vitals_data = [
            [
                Paragraph(
                    f"<b>MONTHLY DEBT LOAD</b><br/>"
                    f"<font size='14' color='#0f172a'><b>{foir:.1f}%</b></font><br/>"
                    f"<font size='7.5' color='{foir_color}'>{_esc(foir_status_label)}</font>",
                    body_style,
                ),
                Paragraph(
                    f"<b>SAFE BORROWING ROOM</b><br/>"
                    f"<font size='14' color='#0f172a'><b>{_esc(borrowing_val)}</b></font><br/>"
                    f"{borrowing_sub}",
                    body_style,
                ),
                Paragraph(
                    f"<b>RECOMMENDED LIFE COVER</b><br/>"
                    f"<font size='14' color='#0f172a'><b>{_esc(life_val)}</b></font><br/>"
                    f"{life_sub}",
                    body_style,
                ),
                Paragraph(
                    f"<b>EMERGENCY SAVINGS FUND</b><br/>"
                    f"<font size='14' color='#0f172a'><b>{emergency_months:.1f} Months</b></font><br/>"
                    f"<font size='7.5' color='#d97706'>₹{emergency_lakhs} Lakhs target reserve</font>",
                    body_style,
                ),
            ]
        ]
        t_vitals = Table(vitals_data, colWidths=[135, 135, 135, 135])
        t_vitals.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(t_vitals)
        story.append(Spacer(1, 14))

        # BUDGET SAFETY CHECK (WHAT-IF SCENARIOS) — shared stress_scenario()
        story.append(Paragraph("BUDGET SAFETY CHECK (WHAT-IF SCENARIOS)", section_heading))
        shock = stress_scenario(income, emis, rate_hike_bps=150.0, income_drop_pct=15.0)
        test_stressed_income = shock["stressed_income"]
        test_stressed_emis = shock["stressed_emis"]
        test_stressed_foir = shock["stressed_foir"]

        if not shock["insolvent"]:
            stress_title = "<b>Your Budget Stays Safe &amp; Protected</b>"
            stress_msg = (
                f"Even if your salary drops by 15% (to ₹{test_stressed_income:,.0f}/mo) and loan interest rates rise "
                f"by 1.50% (increasing EMIs to ₹{test_stressed_emis:,.0f}/mo), your monthly loan obligations would "
                f"take up <b>{test_stressed_foir:.1f}%</b> of your salary, leaving ₹{shock['leftover_cashflow']:,.0f}/mo."
            )
            stress_box_bg = "#ecfdf5"
            stress_box_border = "#a7f3d0"
            stress_title_color = "#059669"
        else:
            stress_title = "<b>Caution: Loans Would Exceed Safe 50% Threshold</b>"
            stress_msg = (
                f"If your salary dropped by 15% and interest rates rose by 1.50%, loan EMIs would consume "
                f"<b>{test_stressed_foir:.1f}%</b> of your income. Paying down existing liabilities builds safety margin."
            )
            stress_box_bg = "#fef2f2"
            stress_box_border = "#fecaca"
            stress_title_color = "#dc2626"

        stress_data = [
            [Paragraph(f"<font color='{stress_title_color}'>{stress_title}</font><br/>{stress_msg}", body_style)]
        ]
        t_stress = Table(stress_data, colWidths=[540])
        t_stress.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(stress_box_bg)),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(stress_box_border)),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(t_stress)

        story.append(Spacer(1, 14))
        story.append(
            Paragraph(
                "<font color='#64748b'><i>Turn to Page 2 for your Tailored 4-Pillar Action Plan &amp; "
                "Beginner Checklist &rarr;</i></font>",
                footer_text,
            )
        )

        # =========================================================================
        # PAGE 2: 4 PILLARS & 3-STEP CHECKLIST
        # =========================================================================
        story.append(PageBreak())

        story.append(Paragraph("2. YOUR PERSONALIZED 4-PILLAR ACTION PLAN", section_heading))
        story.append(
            Paragraph(
                "Clear, plain-English strategies for your spending, borrowing, insurance, and long-term investments:",
                body_style,
            )
        )
        story.append(Spacer(1, 6))

        pillars_data = [
            [
                Paragraph("<b>Area of Life</b>", body_bold),
                Paragraph("<b>Plain-English Advice &amp; Strategy</b>", body_bold),
                Paragraph("<b>Top Tailored Recommendation &amp; Benefit</b>", body_bold),
            ]
        ]

        # Pillar 1: Cards
        rec_card = result.domains.get("credit")
        card_prod = rec_card.products[0] if rec_card and rec_card.products else None
        card_name = (
            f"<b>{_esc(card_prod.name)}</b> ({_esc(card_prod.provider)})"
            if card_prod
            else "<b>HDFC Millennia Credit Card</b>"
        )
        card_benefit = (
            _esc(card_prod.key_benefit)
            if card_prod and card_prod.key_benefit
            else "5% cashback on top shopping platforms"
        )
        if rec_card and not rec_card.eligible:
            card_advice = (
                "Unsecured reward cards are currently gated by your profile. Start with an FD-backed secured "
                "card, keep utilisation under 30%, and pay on time to rebuild CIBIL above 650."
            )
        else:
            card_advice = (
                f"Use a card aligned to your top spend habit (<b>{_esc(spend)}</b>). "
                "Always pay the monthly balance in full so you never pay interest, while earning rewards."
            )
        pillars_data.append(
            [
                Paragraph(
                    "<b>1. Daily Spending &amp; Cards</b><br/><font size='7.5' color='#64748b'>Cashback &amp; Credit</font>",
                    body_style,
                ),
                Paragraph(card_advice, body_style),
                Paragraph(f"{card_name}<br/><font size='7.5' color='#059669'>Benefit: {card_benefit}</font>", body_style),
            ]
        )

        # Pillar 2: Loans
        rec_loan = result.domains.get("loan")
        loan_prod = rec_loan.products[0] if rec_loan and rec_loan.products else None
        loan_name = (
            f"<b>{_esc(loan_prod.name)}</b> ({_esc(loan_prod.provider)})"
            if loan_prod
            else "<b>Secured Gold Loan</b>"
        )
        loan_benefit = _esc(loan_prod.interest_or_cost) if loan_prod else "Asset-backed rate"
        if loan_eligible:
            loan_advice = (
                f"You qualify to safely borrow up to <b>₹{max_loan_lakhs} Lakhs</b> if needed for planned goals. "
                "Keep total EMIs comfortably within the statutory FOIR ceiling so repayments stay resilient."
            )
        else:
            reason_text = _esc(rec_loan.headline if rec_loan else "Unsecured credit not recommended")
            loan_advice = (
                f"{reason_text}. Avoid new unsecured borrowing right now; use asset-backed credit only for "
                "essential liquidity while improving eligibility."
            )
        pillars_data.append(
            [
                Paragraph(
                    "<b>2. Loans &amp; Borrowing</b><br/><font size='7.5' color='#64748b'>Credit Lines</font>",
                    body_style,
                ),
                Paragraph(loan_advice, body_style),
                Paragraph(f"{loan_name}<br/><font size='7.5' color='#0284c7'>Rate: {loan_benefit}</font>", body_style),
            ]
        )

        # Pillar 3: Insurance
        ins_prod = ins_rec.products[0] if ins_rec and ins_rec.products else None
        ins_name = (
            f"<b>{_esc(ins_prod.name)}</b> ({_esc(ins_prod.provider)})"
            if ins_prod
            else "<b>Comprehensive Health Shield</b>"
        )
        if life_recommended:
            ins_benefit = f"₹{life_cover_cr:.2f} Cr life cover + ₹{health_lakhs}L family health floater"
            ins_advice = (
                f"Secure a pure term life policy of <b>₹{life_cover_cr:.2f} Crore</b> to protect your "
                f"{dependents} dependent(s), paired with a <b>₹{health_lakhs} Lakhs</b> family health floater."
            )
        else:
            ins_benefit = f"₹{health_lakhs}L individual medical cover (term life not required)"
            ins_advice = (
                f"With {dependents} dependents on this income, pure term life cover is not required. "
                f"Prioritize a <b>₹{health_lakhs} Lakhs</b> individual health policy so hospital bills never erode savings."
            )
        pillars_data.append(
            [
                Paragraph(
                    "<b>3. Insurance &amp; Protection</b><br/><font size='7.5' color='#64748b'>Safety Net</font>",
                    body_style,
                ),
                Paragraph(ins_advice, body_style),
                Paragraph(
                    f"{ins_name}<br/><font size='7.5' color='#059669'>Coverage: {_esc(ins_benefit)}</font>",
                    body_style,
                ),
            ]
        )

        # Pillar 4: Investments (read directly from RULE_INV_01 allocation)
        rec_inv = result.domains.get("investment")
        alloc = (rec_inv.details.get("allocation") or {}) if rec_inv else {}
        suggested_equity = int(alloc.get("Equity", 50))
        suggested_debt = int(alloc.get("Debt / Fixed Income", 40))
        suggested_gold = int(alloc.get("Gold / Commodities", 10))
        risk_category = _esc(rec_inv.details.get("risk_category", "Moderate") if rec_inv else "Moderate")
        suggested_sip = max(5000, int(surplus * 0.25)) if surplus > 0 else 0
        inv_prod = rec_inv.products[0] if rec_inv and rec_inv.products else None
        inv_name = (
            f"<b>{_esc(inv_prod.name)}</b> ({_esc(inv_prod.provider)})"
            if inv_prod
            else "<b>UTI Nifty 50 Index Fund</b>"
        )
        sip_label = f"Suggested SIP: ~₹{suggested_sip:,}/mo" if suggested_sip > 0 else "Build surplus first"
        inv_benefit = f"{sip_label} • {suggested_equity}% Equity ({risk_category})"
        pillars_data.append(
            [
                Paragraph(
                    "<b>4. Growing Your Wealth</b><br/><font size='7.5' color='#64748b'>Investments &amp; SIP</font>",
                    body_style,
                ),
                Paragraph(
                    f"Rule-based risk profile (<b>{risk_category}</b>) for age {age} and goal <b>{_esc(goal)}</b>: "
                    f"allocate <b>{suggested_equity}%</b> Equity, <b>{suggested_debt}%</b> Debt, and "
                    f"<b>{suggested_gold}%</b> Gold.",
                    body_style,
                ),
                Paragraph(
                    f"{inv_name}<br/><font size='7.5' color='#0284c7'>{_esc(inv_benefit)}</font>",
                    body_style,
                ),
            ]
        )

        t_pillars = Table(pillars_data, colWidths=[120, 240, 180])
        t_pillars.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(t_pillars)
        story.append(Spacer(1, 14))

        # SECTION 3: CHECKLIST
        story.append(
            KeepTogether(
                [
                    Paragraph("3. SIMPLE 3-STEP ACTION CHECKLIST (WHAT TO DO NEXT)", section_heading),
                    Paragraph(
                        "Follow these three steps in order to put your personal finances on solid footing:",
                        body_style,
                    ),
                    Spacer(1, 6),
                ]
            )
        )

        if life_recommended:
            step2_text = (
                f"<b>Lock In Family Protection:</b> Activate pure term life insurance (₹{life_cover_cr:.2f} Cr) "
                f"and a ₹{health_lakhs} Lakhs cashless family health floater so emergencies never derail savings."
            )
        else:
            step2_text = (
                f"<b>Lock In Medical Protection:</b> Activate a ₹{health_lakhs} Lakhs cashless individual health "
                "policy so unexpected hospitalisation costs never drain your investments."
            )

        step3_text = (
            f"<b>Automate Monthly Investing:</b> Set up an automatic SIP of ~₹{suggested_sip:,} after salary day "
            f"following your {suggested_equity}% Equity / {suggested_debt}% Debt / {suggested_gold}% Gold split."
            if suggested_sip > 0
            else "<b>Restore Positive Cashflow:</b> Clear high-cost obligations first before starting market SIPs."
        )

        checklist_data = [
            [
                Paragraph("<b>STEP 1</b>", body_bold),
                Paragraph(
                    f"<b>Build Your Emergency Cushion:</b> Keep {emergency_months:.0f} months of estimated living "
                    f"expenses (₹{emergency_lakhs} Lakhs) in a liquid savings account or sweep FD before taking risk.",
                    body_style,
                ),
            ],
            [
                Paragraph("<b>STEP 2</b>", body_bold),
                Paragraph(step2_text, body_style),
            ],
            [
                Paragraph("<b>STEP 3</b>", body_bold),
                Paragraph(step3_text, body_style),
            ],
        ]
        t_checklist = Table(checklist_data, colWidths=[60, 480])
        t_checklist.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                    ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(t_checklist)
        story.append(Spacer(1, 16))

        # FOOTER & VERIFICATION
        sha_digest = _esc(result.audit_record.get("sha256_fingerprint", "N/A"))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=6))
        story.append(
            Paragraph(
                "<b>WealthWise Personal Finance</b> • Educational illustration based on general RBI, SEBI &amp; IRDAI "
                "rules of thumb. Not financial advice. • "
                f"<font color='#64748b'>SHA-256 Integrity Fingerprint: {sha_digest[:32]}...</font>",
                footer_text,
            )
        )

        doc.build(story, canvasmaker=NumberedCanvas)
        buffer.seek(0)
        return buffer.getvalue()
