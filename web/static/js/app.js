/**
 * WealthWise — Apple HIG Client Controller & Rule Engine Bridge
 * Single source of truth: all health scores, borrowing limits, insurance covers,
 * backward-chaining counterfactuals, and stress scenarios come from the server APIs.
 */

const currentProfile = {
  income: 120000,
  emis: 18000,
  creditScore: 785,
  age: 28,
  dependents: 1,
  employment: "Salaried",
  risk: "High",
  spendCategory: "Online Shopping",
  goal: "Wealth Creation"
};

let debounceTimer = null;
let advisoryRequestId = 0;
let isCurrentlyShimmering = false;
let fallbackCardsShown = false;

// ==============================================================================
// 1. Initialization
// ==============================================================================
document.addEventListener("DOMContentLoaded", () => {
  bindUi();
  initGeminiKey();
  readInputsFromDOM();
  showAnalysisPending();
  refreshAnalysis();
  refreshGoalSeek();
  renderAllSkeletonCards();
  updateStressSim();
  scheduleAdvisorySynthesis(250);
});

// ==============================================================================
// 1b. Event wiring (no inline handlers, so CSP forbids inline scripts)
// ==============================================================================
const ACTIONS = {
  "open-gemini": () => openGeminiModal(),
  "close-gemini": () => closeGeminiModal(),
  "save-gemini-key": () => saveGeminiKey(),
  "clear-gemini-key": () => clearGeminiKey(),
  "export-pdf": () => exportDossierPDF(),
};

function bindUi() {
  document.addEventListener("click", (event) => {
    const el = event.target.closest("[data-action]");
    if (el && ACTIONS[el.dataset.action]) {
      event.preventDefault();
      ACTIONS[el.dataset.action](el);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeGeminiModal();
  });
  document.querySelectorAll('[data-input="profile"]').forEach(el => el.addEventListener("input", onInputChange));
  document.querySelectorAll('[data-change="profile"]').forEach(el => el.addEventListener("change", onInputChange));
  document.querySelectorAll('[data-input="stress"]').forEach(el => el.addEventListener("input", updateStressSim));
  document.querySelectorAll('[data-change="goal-seek"]').forEach(el => el.addEventListener("change", () => scheduleGoalSeek(80)));
  const form = document.getElementById("profile-form");
  if (form) form.addEventListener("submit", (event) => event.preventDefault());
  const modal = document.getElementById("gemini-modal");
  if (modal) modal.addEventListener("click", (event) => { if (event.target === modal) closeGeminiModal(); });
}

function postJson(path, body, extraHeaders = {}) {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": token, ...extraHeaders },
    body: JSON.stringify(body)
  });
}

function readGeminiKey() {
  try { return sessionStorage.getItem("wealthwise_gemini_key") || ""; } catch (e) { return ""; }
}
function writeGeminiKey(key) {
  try { key ? sessionStorage.setItem("wealthwise_gemini_key", key) : sessionStorage.removeItem("wealthwise_gemini_key"); } catch (e) { /* storage blocked */ }
}
try { localStorage.removeItem("wealthwise_gemini_key"); } catch (e) { /* clear legacy storage */ }

function safeHref(url) {
  try {
    const parsed = new URL(String(url));
    return parsed.protocol === "https:" ? parsed.href : "#";
  } catch (e) {
    return "#";
  }
}

// ==============================================================================
// 2. Gemini API Key Management
// ==============================================================================
function initGeminiKey() {
  const savedKey = readGeminiKey();
  const inputEl = document.getElementById("gemini-key-input");
  if (savedKey) {
    if (inputEl) inputEl.value = savedKey;
    updateGeminiStatusUI(true, "Gemini AI");
  } else {
    updateGeminiStatusUI(false);
  }
}

function updateGeminiStatusUI(isGeminiActive, modelName = "Gemini AI") {
  const chipLabel = document.getElementById("ai-chip-label");
  const pulseDot = document.getElementById("ai-pulse-dot");
  const modalEngine = document.getElementById("modal-current-engine");

  if (isGeminiActive) {
    if (chipLabel) chipLabel.textContent = `${modelName} Active`;
    if (pulseDot) {
      pulseDot.style.background = "var(--pastel-mint-solid)";
      pulseDot.style.boxShadow = "0 0 0 2px var(--pastel-mint-bg)";
    }
    if (modalEngine) modalEngine.textContent = `Active: Google ${modelName} (validated against catalogue host allowlist)`;
  } else {
    if (chipLabel) chipLabel.textContent = "Offline Rule Engine";
    if (pulseDot) {
      pulseDot.style.background = "var(--text-tertiary)";
      pulseDot.style.boxShadow = "none";
    }
    if (modalEngine) modalEngine.textContent = "Offline neuro-symbolic rule engine (add a Gemini key to enable Google Gemini)";
  }
}

function openGeminiModal() {
  const modal = document.getElementById("gemini-modal");
  if (modal) modal.style.display = "flex";
}

function closeGeminiModal() {
  const modal = document.getElementById("gemini-modal");
  if (modal) modal.style.display = "none";
}

function saveGeminiKey() {
  const inputEl = document.getElementById("gemini-key-input");
  const key = inputEl ? inputEl.value.trim() : "";
  if (key) {
    writeGeminiKey(key);
    updateGeminiStatusUI(true);
    closeGeminiModal();
    scheduleAdvisorySynthesis(150);
  } else {
    clearGeminiKey();
  }
}

function clearGeminiKey() {
  writeGeminiKey("");
  const inputEl = document.getElementById("gemini-key-input");
  if (inputEl) inputEl.value = "";
  updateGeminiStatusUI(false);
  closeGeminiModal();
  scheduleAdvisorySynthesis(150);
}

// ==============================================================================
// 3. User Input Synchronization
// ==============================================================================
function onInputChange() {
  readInputsFromDOM();
  showAnalysisPending();
  scheduleAnalysis(200);
  scheduleGoalSeek(250);
  updateStressSim();
  showSkeletonStateIfReady();
  scheduleAdvisorySynthesis(280);
}

function numVal(id, fallback) {
  const el = document.getElementById(id);
  if (!el) return fallback;
  const parsed = Number(el.value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readInputsFromDOM() {
  currentProfile.income = numVal("f_income", 120000);
  currentProfile.emis = numVal("f_emis", 18000);
  currentProfile.creditScore = Math.round(numVal("f_credit", 785));
  currentProfile.age = Math.round(numVal("f_age", 28));
  currentProfile.dependents = Math.round(numVal("f_deps", 1));
  currentProfile.employment = document.getElementById("f_employment")?.value || "Salaried";
  currentProfile.risk = document.getElementById("f_risk")?.value || "High";
  currentProfile.spendCategory = document.getElementById("f_spend")?.value || "Online Shopping";
  currentProfile.goal = document.getElementById("f_goal")?.value || "Wealth Creation";

  document.getElementById("disp_income").textContent = "₹" + Math.round(currentProfile.income).toLocaleString("en-IN");
  document.getElementById("disp_emis").textContent = "₹" + Math.round(currentProfile.emis).toLocaleString("en-IN");
  document.getElementById("disp_credit").textContent = currentProfile.creditScore;
  document.getElementById("disp_age").textContent = currentProfile.age;
  document.getElementById("disp_deps").textContent = currentProfile.dependents;

  const tierBadge = document.getElementById("cibil-tier-badge");
  if (currentProfile.creditScore >= 750) {
    tierBadge.textContent = "Excellent";
    tierBadge.className = "apple-pill mint";
  } else if (currentProfile.creditScore >= 700) {
    tierBadge.textContent = "Good";
    tierBadge.className = "apple-pill sky";
  } else if (currentProfile.creditScore >= 650) {
    tierBadge.textContent = "Fair";
    tierBadge.className = "apple-pill amber";
  } else {
    tierBadge.textContent = "Subprime";
    tierBadge.className = "apple-pill coral";
  }
}

let analysisTimer = null;
let analysisRequestId = 0;
let latestAnalysis = null;

let goalSeekTimer = null;
let goalSeekRequestId = 0;

const VITAL_IDS = ["vital-loan", "vital-insurance", "vital-runway"];

const rupees = (n) => "₹" + Math.round(n).toLocaleString("en-IN");
const lakhs = (n) => "₹" + (n / 100000).toFixed(2).replace(/\.00$/, ".0").replace(/(\.\d)0$/, "$1") + " Lakhs";
const crores = (n) => "₹" + (n / 10000000).toFixed(2) + " Crore";

function setFoirDisplay(pct, status) {
  document.getElementById("vital-foir").textContent = pct.toFixed(1) + "%";
  const sub = document.getElementById("vital-foir-sub");
  const icon = document.getElementById("icon-foir");
  const view = {
    safe: ["Safe (Low Loan Burden)", "mint"],
    moderate: ["Moderate (Within safe 50% limit)", "amber"],
    critical: ["Critical (Over safe 50% limit)", "coral"],
  }[status] || ["Moderate", "amber"];
  sub.textContent = view[0];
  sub.style.color = `var(--pastel-${view[1]}-text)`;
  icon.style.color = `var(--pastel-${view[1]}-solid)`;
}

function showAnalysisPending() {
  const { income, emis } = currentProfile;
  const pct = income > 0 ? (emis / income) * 100 : 100;
  setFoirDisplay(pct, pct <= 35 ? "safe" : pct <= 50 ? "moderate" : "critical");
  VITAL_IDS.forEach(id => {
    document.getElementById(id).textContent = "…";
    document.getElementById(id + "-sub").textContent = "Running rule engine";
  });
}

function showAnalysisOffline() {
  VITAL_IDS.forEach(id => {
    document.getElementById(id).textContent = "—";
    document.getElementById(id + "-sub").textContent = "Server unreachable; figures unavailable";
  });
  const headline = document.getElementById("summary-headline");
  const body = document.getElementById("summary-body");
  if (headline) headline.textContent = "Analysis unavailable";
  if (body) body.textContent = "The advisory server could not be reached, so no score is shown rather than an unverified one.";
}

function scheduleAnalysis(delayMs = 200) {
  if (analysisTimer) clearTimeout(analysisTimer);
  analysisTimer = setTimeout(refreshAnalysis, delayMs);
}

function scheduleGoalSeek(delayMs = 200) {
  if (goalSeekTimer) clearTimeout(goalSeekTimer);
  goalSeekTimer = setTimeout(refreshGoalSeek, delayMs);
}

function profilePayload() {
  return {
    name: "Client",
    age: currentProfile.age,
    monthly_income: currentProfile.income,
    credit_score: currentProfile.creditScore,
    employment_type: currentProfile.employment,
    existing_emis: currentProfile.emis,
    dependents: currentProfile.dependents,
    financial_goal: currentProfile.goal,
    risk_tolerance: currentProfile.risk,
    preferred_spend_category: currentProfile.spendCategory
  };
}

async function refreshAnalysis() {
  const requestId = ++analysisRequestId;
  showAnalysisPending();
  let data = null;
  try {
    const res = await postJson("/api/analyze", profilePayload());
    data = res.ok ? await res.json() : null;
  } catch (err) {
    console.warn("Analysis request failed:", err);
  }
  if (requestId !== analysisRequestId) return;
  if (!data || !data.vitals) {
    showAnalysisOffline();
    return;
  }
  latestAnalysis = data;
  renderAnalysis(data);
}

function renderAnalysis(data) {
  const v = data.vitals;
  setFoirDisplay(v.foir.pct, v.foir.status);

  const loanEl = document.getElementById("vital-loan");
  const loanSub = document.getElementById("vital-loan-sub");
  if (v.borrowing.state === "eligible") {
    loanEl.textContent = lakhs(v.borrowing.max_amount);
    loanSub.textContent = "Pre-qualified @ " + v.borrowing.interest_rate;
  } else {
    loanEl.textContent = "Not eligible";
    loanSub.textContent = v.borrowing.note;
  }

  const coverEl = document.getElementById("vital-insurance");
  const coverSub = document.getElementById("vital-insurance-sub");
  if (v.life_cover.recommended) {
    coverEl.textContent = crores(v.life_cover.amount);
    coverSub.textContent = `${v.life_cover.annual_income_multiple}x annual income cover`;
  } else {
    coverEl.textContent = "Not required";
    coverSub.textContent = currentProfile.dependents === 0 ? "No dependents on this income" : "Outside term-life window";
  }

  const reserve = v.emergency_reserve;
  document.getElementById("vital-runway").textContent = `${reserve.months} Months`;
  document.getElementById("vital-runway-sub").textContent =
    `${lakhs(reserve.target_amount)} target (est. spend ${rupees(reserve.assumed_monthly_expenses)}/mo)`;

  updateOptimizedAppleGauge(v.fhi.score, v.fhi.tier);

  const headlineEl = document.getElementById("summary-headline");
  const bodyEl = document.getElementById("summary-body");
  if (headlineEl) headlineEl.textContent = v.summary.headline;
  if (bodyEl) bodyEl.textContent = v.summary.body;

  const alertBox = document.getElementById("override-alert-box");
  if (alertBox) {
    alertBox.innerHTML = v.fhi.overrides.map(o => `
      <div class="override-alert">
        <svg class="icon-svg icon-sm" aria-hidden="true"><use href="#i-report"></use></svg>
        <span>${escapeHtml(o)}</span>
      </div>`).join("");
  }
  renderRuleTrace(data.firing_history);

  if (fallbackCardsShown) applyDeterministicCategorizedAdvisory();
}

function renderRuleTrace(firings) {
  const list = document.getElementById("rule-trace-list");
  const count = document.getElementById("rule-trace-count");
  if (!list) return;
  if (count) count.textContent = firings.length;
  list.innerHTML = firings.map(f => {
    const facts = f.asserted_facts
      .map(a => `${escapeHtml(a.name)}${a.certainty !== undefined ? ` (CF ${Number(a.certainty).toFixed(2)})` : ""}`)
      .join(", ");
    return `<li><b>${escapeHtml(f.rule_id)}</b>
      <span class="trace-meta">evidence CF ${Number(f.premise_cf).toFixed(2)}</span><br>
      <span class="trace-desc">${escapeHtml(f.description)}</span><br>
      <span class="trace-meta">asserted: ${facts}</span></li>`;
  }).join("");
}

// ==============================================================================
// 3b. Backward-Chaining Goal Seek UI (/api/backward-chain)
// ==============================================================================
function parseGoalSelection() {
  const raw = document.getElementById("goal-seek-target")?.value || "loan.eligible:true";
  const [targetFact, rawVal] = raw.split(":");
  const desiredValue = rawVal === "true" ? true : rawVal === "false" ? false : rawVal;
  return { target_fact: targetFact, desired_value: desiredValue };
}

async function refreshGoalSeek() {
  const outEl = document.getElementById("goal-seek-output");
  if (!outEl) return;
  const reqId = ++goalSeekRequestId;
  const goalSpec = parseGoalSelection();
  outEl.textContent = "Evaluating counterfactual path…";

  let data = null;
  try {
    const res = await postJson("/api/backward-chain", {
      ...goalSpec,
      profile: profilePayload()
    });
    data = res.ok ? await res.json() : null;
  } catch (err) {
    console.warn("Backward-chaining request failed:", err);
  }
  if (reqId !== goalSeekRequestId) return;
  if (!data) {
    outEl.textContent = "Goal analysis unavailable.";
    return;
  }

  if (data.achieved) {
    outEl.innerHTML = `
      <span class="goal-seek-badge achieved">Already Satisfied</span>
      <div>${escapeHtml(data.message)}</div>`;
    return;
  }

  const badgeClass = data.plan_verified ? "verified" : "blocked";
  const badgeLabel = data.plan_verified
    ? "Verified by Forward Chaining"
    : "Blocked by Unfixable Constraint";
  const steps = Array.isArray(data.remediation_plan) ? data.remediation_plan : [];
  const stepsHtml = steps.length
    ? `<ol>${steps.map(s => `<li>${escapeHtml(s)}</li>`).join("")}</ol>`
    : `<div>${escapeHtml(data.message || "No remediation steps available.")}</div>`;

  outEl.innerHTML = `
    <span class="goal-seek-badge ${badgeClass}">${badgeLabel}</span>
    <div>${escapeHtml(data.message || "")}</div>
    ${stepsHtml}`;
}

// ==============================================================================
// 4. Shimmering Skeleton System & Advisory Fetch
// ==============================================================================
function scheduleAdvisorySynthesis(delayMs = 280) {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    executeDeliberateAdvisory();
  }, delayMs);
}

function showSkeletonStateIfReady() {
  if (!isCurrentlyShimmering) {
    isCurrentlyShimmering = true;
    renderAllSkeletonCards();

    const indicator = document.getElementById("ai-evaluation-indicator");
    const textEl = document.getElementById("ai-eval-text");
    if (indicator && textEl) {
      indicator.className = "ai-eval-badge analyzing";
      textEl.textContent = "Evaluating Rule Base…";
    }
  }
}

function generateSkeletonCardHTML() {
  return `
    <div class="product-card skeleton-card">
      <div class="card-content-top">
        <div class="product-card-top">
          <div style="display:flex; flex-direction:column; gap:6px; flex:1; min-width:0;">
            <div class="skeleton-shimmer" style="width: 145px; height: 18px; border-radius: 6px;"></div>
            <div class="skeleton-shimmer" style="width: 85px; height: 12px; border-radius: 4px;"></div>
          </div>
          <div class="skeleton-shimmer match-pill" style="width: 78px; height: 22px; border-radius: 9999px;"></div>
        </div>

        <div class="card-highlight-box" style="margin: 12px 0;">
          <div style="display:flex; flex-direction:column; gap:6px; width:100%;">
            <div class="skeleton-shimmer" style="width: 105px; height: 10px; border-radius: 3px;"></div>
            <div class="skeleton-shimmer" style="width: 180px; height: 19px; border-radius: 5px;"></div>
          </div>
        </div>

        <div class="why-matched" style="display:flex; flex-direction:column; gap:8px;">
          <div class="skeleton-shimmer" style="width: 100%; height: 12px; border-radius: 4px;"></div>
          <div class="skeleton-shimmer" style="width: 92%; height: 12px; border-radius: 4px;"></div>
          <div class="skeleton-shimmer" style="width: 65%; height: 12px; border-radius: 4px;"></div>
        </div>
      </div>

      <div class="card-action-bar">
        <div class="skeleton-shimmer" style="width: 95px; height: 22px; border-radius: 9999px;"></div>
        <div class="skeleton-shimmer" style="width: 100px; height: 28px; border-radius: 9999px;"></div>
      </div>
    </div>
  `;
}

function renderAllSkeletonCards() {
  const containers = ["cards-container", "loans-container", "insurance-container", "investments-container"];
  containers.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = generateSkeletonCardHTML() + generateSkeletonCardHTML() + generateSkeletonCardHTML();
    }
  });
}

async function executeDeliberateAdvisory() {
  const thisRequestId = ++advisoryRequestId;
  const geminiKey = readGeminiKey();

  showSkeletonStateIfReady();

  // Brief 150ms settle window to prevent rapid slider flicker
  const pacingPromise = new Promise(resolve => setTimeout(resolve, 150));

  let finalData = null;

  try {
    const fetchPromise = postJson("/api/gemini-advisory", {
      monthly_income: currentProfile.income,
      existing_emis: currentProfile.emis,
      credit_score: currentProfile.creditScore,
      age: currentProfile.age,
      dependents: currentProfile.dependents,
      employment_type: currentProfile.employment,
      risk_tolerance: currentProfile.risk,
      preferred_spend_category: currentProfile.spendCategory,
      financial_goal: currentProfile.goal
    }, geminiKey ? { "X-Gemini-Api-Key": geminiKey } : {})
      .then(res => res.ok ? res.json() : null)
      .catch(() => null);

    const [data] = await Promise.all([fetchPromise, pacingPromise]);
    finalData = data;
  } catch (err) {
    console.warn("Advisory fetch exception:", err);
  }

  if (thisRequestId !== advisoryRequestId) return;

  if (finalData && (finalData.categorized_products || finalData.recommended_products)) {
    const usedGemini = finalData.source === "gemini_ai";
    updateGeminiStatusUI(usedGemini || Boolean(geminiKey), finalData.model && usedGemini ? finalData.model : "Gemini AI");
    applyCategorizedAdvisory(finalData);
  } else {
    applyDeterministicCategorizedAdvisory();
  }

  isCurrentlyShimmering = false;

  const indicator = document.getElementById("ai-evaluation-indicator");
  const textEl = document.getElementById("ai-eval-text");
  if (indicator && textEl) {
    indicator.className = "ai-eval-badge ready";
    textEl.textContent = finalData?.source === "gemini_ai"
      ? "Gemini Evaluation Complete (12 Options)"
      : "Rule Evaluation Complete (12 Options)";
  }
}

// ==============================================================================
// 5. Categorized Advisory Application & Rendering
// ==============================================================================
function applyCategorizedAdvisory(data) {
  fallbackCardsShown = false;
  const grouped = { cards: [], loans: [], insurance: [], investments: [] };

  if (data.categorized_products && typeof data.categorized_products === "object") {
    grouped.cards = data.categorized_products.cards || [];
    grouped.loans = data.categorized_products.loans || [];
    grouped.insurance = data.categorized_products.insurance || [];
    grouped.investments = data.categorized_products.investments || [];
  } else if (Array.isArray(data.recommended_products)) {
    data.recommended_products.forEach(p => {
      const cat = p.category || "cards";
      if (grouped[cat]) grouped[cat].push(p);
    });
  }

  const det = buildDeterministicCategorizedProducts();
  ["cards", "loans", "insurance", "investments"].forEach(c => {
    while (grouped[c].length < 3 && det[c] && det[c].length > grouped[c].length) {
      grouped[c].push(det[c][grouped[c].length]);
    }
    grouped[c] = grouped[c].slice(0, 3);
  });

  renderCategorizedCards(grouped);
}

function applyDeterministicCategorizedAdvisory() {
  fallbackCardsShown = true;
  const det = buildDeterministicCategorizedProducts();
  renderCategorizedCards(det);
}

function escapeHtml(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function renderCardHTML(item, pillClass, index) {
  const rawUrl = item.apply_url;
  const safe = Object.fromEntries(
    Object.entries(item).map(([k, v]) => [k, typeof v === "string" ? escapeHtml(v) : v])
  );
  return `
    <div class="product-card fade-in" style="animation-delay: ${index * 60}ms;">
      <div class="card-content-top">
        <div class="product-card-top">
          <div class="product-meta">
            <span class="product-name">${safe.name}</span>
            <span class="product-provider">${safe.provider}</span>
          </div>
          <span class="apple-pill mint match-pill">${escapeHtml(Number(safe.match_score) || 0)}% Match</span>
        </div>

        <div class="card-highlight-box">
          <span class="highlight-label">YOUR SIZED BENEFIT</span>
          <span class="highlight-val">${safe.personalized_metric}</span>
        </div>

        <div class="why-matched">
          ${safe.why_matched}
        </div>
      </div>

      <div class="card-action-bar">
        <span class="${pillClass}">${safe.category_label || safe.category}</span>
        <a href="${escapeHtml(safeHref(rawUrl))}" target="_blank" rel="noopener noreferrer" class="apply-btn">
          Apply Online &rarr;
        </a>
      </div>
    </div>
  `;
}

function renderCategorizedCards(grouped) {
  const mapping = [
    ["cards-container", grouped.cards, "apple-pill sky"],
    ["loans-container", grouped.loans, "apple-pill sky"],
    ["insurance-container", grouped.insurance, "apple-pill mint"],
    ["investments-container", grouped.investments, "apple-pill purple"],
  ];
  mapping.forEach(([id, items, pill]) => {
    const el = document.getElementById(id);
    if (el && items) {
      el.innerHTML = items.map((p, i) => renderCardHTML(p, pill, i)).join("");
    }
  });
}

// ==============================================================================
// 6. Client Fallback Cards (reads sizing strictly from latestAnalysis)
// ==============================================================================
function buildDeterministicCategorizedProducts() {
  const { income, emis, creditScore, spendCategory, age, dependents, goal } = currentProfile;

  const domains = latestAnalysis ? latestAnalysis.domains : null;
  const cardInfo = domains ? domains.credit : null;
  const loanInfo = domains ? domains.loan : null;
  const insInfo = domains ? domains.insurance : null;
  const invInfo = domains ? domains.investment : null;

  const cardEligible = !!(cardInfo && cardInfo.eligible);
  const loanEligible = !!(loanInfo && loanInfo.eligible);
  const maxLoanLakhs = loanEligible ? (loanInfo.details.max_amount / 100000).toFixed(2) : "0.0";
  const aprQuoted = loanEligible ? String(loanInfo.details.interest_rate).split(" (")[0] : "";

  const termCover = insInfo ? insInfo.details.term_cover : 0;
  const lifeCoverCrores = (termCover / 10000000).toFixed(2);
  const healthCoverLakhs = insInfo && insInfo.details.health_sum_insured
    ? Math.round(insInfo.details.health_sum_insured / 100000) : 5;
  const equityPct = invInfo && invInfo.details.allocation ? invInfo.details.allocation.Equity : null;
  const suggestedSip = Math.max(0, income - emis) > 0 ? Math.round(Math.max(5000, (income - emis) * 0.25)) : 0;
  const emergencyBufferLakhs = latestAnalysis
    ? (latestAnalysis.vitals.emergency_reserve.target_amount / 100000).toFixed(2) : "0.0";

  // Cards (3 Options)
  const cards = [];
  if (cardEligible) {
    if (spendCategory === "Travel") {
      cards.push({
        id: "card_atlas", category: "cards", name: "Axis Bank Atlas Card", provider: "Axis Bank",
        category_label: "Travel & Air-Miles", match_score: creditScore >= 750 ? 98 : 90,
        headline: "5x EDGE Air-Miles on Airline & Hotel Bookings",
        personalized_metric: `~₹${Math.round(income * 0.12).toLocaleString("en-IN")} in flight miles`,
        why_matched: "Matched to your Travel spend preference with accelerated air-miles and lounge access.",
        apply_url: "https://www.axisbank.com/retail/cards/credit-card/atlas-credit-card"
      });
    } else if (spendCategory === "Dining & Lifestyle") {
      cards.push({
        id: "card_liveplus", category: "cards", name: "HSBC Live+ Credit Card", provider: "HSBC India",
        category_label: "Dining & Groceries", match_score: creditScore >= 750 ? 97 : 89,
        headline: "10% Direct Cashback on Dining & Grocery Apps",
        personalized_metric: `~₹${Math.round(income * 0.09).toLocaleString("en-IN")}/yr dining savings`,
        why_matched: "Matched to your dining habit with statement cashback on food delivery and groceries.",
        apply_url: "https://www.hsbc.co.in/credit-cards/products/live-plus/"
      });
    } else if (spendCategory === "Fuel & Commute") {
      cards.push({
        id: "card_bpcl", category: "cards", name: "BPCL SBI Card Octane", provider: "State Bank of India",
        category_label: "Fuel & Commute", match_score: 96,
        headline: "7.25% Value-Back on Fuel at BPCL Outlets",
        personalized_metric: `~₹${Math.round(income * 0.06).toLocaleString("en-IN")}/yr saved on fuel`,
        why_matched: "Tailored for daily commutes with fuel surcharge waivers and accelerated rewards.",
        apply_url: "https://www.sbicard.com/en/personal/credit-cards/fuel/bpcl-sbi-card-octane.page"
      });
    } else {
      cards.push({
        id: "card_millennia", category: "cards", name: "HDFC Millennia Credit Card", provider: "HDFC Bank",
        category_label: "Cashback & Retail", match_score: creditScore >= 750 ? 98 : 91,
        headline: "5% Direct Cashback on Amazon, Flipkart & Myntra",
        personalized_metric: `~₹${Math.round(income * 0.10).toLocaleString("en-IN")}/yr cashback projection`,
        why_matched: "Top pick for digital retail and Online Shopping with 5% monthly cash points.",
        apply_url: "https://www.hdfcbank.com/personal/pay/cards/credit-cards/millennia-credit-card"
      });
    }
    cards.push({
      id: "card_amazon", category: "cards", name: "Amazon Pay ICICI Credit Card", provider: "ICICI Bank",
      category_label: "Lifetime Free Cashback", match_score: 94,
      headline: "Flat 5% Unlimited Cashback • Lifetime Free Card",
      personalized_metric: `~₹${Math.round(income * 0.07).toLocaleString("en-IN")}/yr lifetime-free cashback`,
      why_matched: "Zero joining and renewal fees; earns uncapped cashback on utilities and digital spends.",
      apply_url: "https://www.icicibank.com/personal-banking/cards/credit-card/amazon-pay-credit-card"
    });
    cards.push({
      id: "card_regalia", category: "cards", name: "HDFC Regalia Gold Credit Card", provider: "HDFC Bank",
      category_label: "Lounge & Milestone Tier", match_score: creditScore >= 750 ? 92 : 85,
      headline: "12 Domestic Airport Lounge Visits + Milestone Flights",
      personalized_metric: `~₹${Math.round(income * 0.05).toLocaleString("en-IN")} in annual milestone rewards`,
      why_matched: "Adds airport lounge privileges and annual milestone vouchers.",
      apply_url: "https://www.hdfcbank.com/personal/pay/cards/credit-cards/regalia-gold-credit-card"
    });
  } else {
    cards.push({
      id: "card_wow", category: "cards", name: "IDFC FIRST WOW! Card", provider: "IDFC FIRST Bank",
      category_label: "FD-Backed Credit Builder", match_score: 98,
      headline: "Zero CIBIL Check • 100% Approval Backed by FD",
      personalized_metric: "FD from ₹2,000 • Rebuilds CIBIL bureau track",
      why_matched: `Unsecured cards are gated by RULE_CARD_01 (CIBIL ${creditScore}). Reports monthly to rebuild credit safely.`,
      apply_url: "https://www.idfcfirstbank.com/credit-card/wow"
    });
    cards.push({
      id: "card_amazon_goal", category: "cards", name: "Amazon Pay ICICI Credit Card (Target Tier)", provider: "ICICI Bank",
      category_label: "Next Milestone (CIBIL 650+)", match_score: 82,
      headline: "Lifetime-Free Entry Unsecured Card Once CIBIL Clears 650",
      personalized_metric: "₹0 Annual Fee • Target after 6 mos FD card history",
      why_matched: "Keep utilisation below 30% and FOIR under 50% to unlock unsecured cards.",
      apply_url: "https://www.icicibank.com/personal-banking/cards/credit-card/amazon-pay-credit-card"
    });
    cards.push({
      id: "card_simplyclick_goal", category: "cards", name: "SBI SimplyCLICK Credit Card (Target Tier)", provider: "SBI Card",
      category_label: "Entry Digital Spends", match_score: 80,
      headline: "Low-Fee Entry Card Once Eligibility Clears",
      personalized_metric: "₹499 Annual Fee • 10X Partner Rewards",
      why_matched: "Accessible entry-tier card once verifiable income, FOIR, and CIBIL pass underwriting.",
      apply_url: "https://www.sbicard.com/en/personal/credit-cards/shopping/simplyclick-sbi-card.page"
    });
  }

  // Loans (3 Options)
  const loans = [];
  if (loanEligible) {
    loans.push({
      id: "loan_hdfc", category: "loans", name: "HDFC XPRESS Personal Loan", provider: "HDFC Bank",
      category_label: "Pre-Qualified Unsecured Loan", match_score: creditScore >= 750 ? 96 : 88,
      headline: "60-Month Reverse-EMI Sized Capacity",
      personalized_metric: `Up to ₹${maxLoanLakhs}L @ ${aprQuoted}`,
      why_matched: `Approved by RULE_LOAN_05 within statutory FOIR limits after existing EMIs (₹${Math.round(emis).toLocaleString("en-IN")}/mo).`,
      apply_url: "https://www.hdfcbank.com/personal/borrow/popular-loans/personal-loan"
    });
    const flexiLimit = Math.max(1.0, (parseFloat(maxLoanLakhs) * 0.75)).toFixed(1);
    loans.push({
      id: "loan_flexi", category: "loans", name: "Bajaj Finserv Flexi Loan", provider: "Bajaj Finserv",
      category_label: "Flexible Drawdown Line", match_score: 91,
      headline: "Pay Interest Only on Drawn Funds",
      personalized_metric: `Drawdown line up to ₹${flexiLimit} Lakhs`,
      why_matched: "Sized at 75% of your maximum unsecured limit so idle funds incur zero interest.",
      apply_url: "https://www.bajajfinserv.in/personal-loan"
    });
    loans.push({
      id: "loan_gold", category: "loans", name: "Muthoot Gold Loan (Asset Backed)", provider: "Muthoot Finance",
      category_label: "Secured Credit", match_score: 93,
      headline: "Low-Rate Collateral Option Preserving Unsecured Headroom",
      personalized_metric: "9.90% – 11.50% APR against gold collateral",
      why_matched: "Collateral-backed alternative when you prefer lower interest rates over unsecured debt.",
      apply_url: "https://www.muthootfinance.com/gold-loan"
    });
  } else {
    loans.push({
      id: "loan_gold", category: "loans", name: "Muthoot Gold Loan (Secured Fallback)", provider: "Muthoot Finance",
      category_label: "Rule-Engine Secured Fallback", match_score: 95,
      headline: "Asset-Backed Liquidity Without Unsecured Gates",
      personalized_metric: "9.90% – 14.00% p.a. • Unsecured limit: ₹0",
      why_matched: `${loanInfo ? loanInfo.headline : "Unsecured loan gated by rule base"}. Asset-backed credit avoids unsecured rejection.`,
      apply_url: "https://www.muthootfinance.com/gold-loan"
    });
    loans.push({
      id: "loan_smfg", category: "loans", name: "SMFG India Credit Consolidation Review", provider: "SMFG India Credit",
      category_label: "Debt Restructuring", match_score: 84,
      headline: "Refinance High-Cost Obligations Before Taking New Debt",
      personalized_metric: "Unsecured borrowing paused until blockers clear",
      why_matched: "Open the backward-chaining panel above to see the exact CIBIL, EMI, or income change needed.",
      apply_url: "https://www.smfgindiacredit.com/personal-loan.aspx"
    });
    loans.push({
      id: "loan_sbi", category: "loans", name: "SBI Secured Overdraft", provider: "State Bank of India",
      category_label: "PSU Secured Option", match_score: 88,
      headline: "FD-Backed Overdraft at ~1% Above Deposit Rate",
      personalized_metric: "Secured against fixed deposits • Zero CIBIL gate",
      why_matched: "Overdraft against term deposits provides regulated liquidity while unsecured gates apply.",
      apply_url: "https://sbi.bank.in/web/personal-banking/loans/personal-loans"
    });
  }

  // Insurance (3 Options)
  const insurance = [];
  if (termCover > 0) {
    insurance.push({
      id: "ins_lic", category: "insurance", name: "LIC Tech Term Insurance", provider: "Life Insurance Corporation (LIC)",
      category_label: "Pure Term Life Cover", match_score: 97,
      headline: "Pure Mortality Income Replacement Sized by RULE_INS_01",
      personalized_metric: `₹${lifeCoverCrores} Crore Life Sum Assured`,
      why_matched: `Sized by the Human Life Value rule for age ${age}y with ${dependents} dependent(s).`,
      apply_url: "https://licindia.in/tech-term"
    });
    insurance.push({
      id: "ins_star", category: "insurance", name: "Star Health Family Optima Floater", provider: "Star Health Insurance",
      category_label: "Family Medical Floater", match_score: 95,
      headline: "Cashless Family Hospitalisation Shield (RULE_INS_02)",
      personalized_metric: `₹${healthCoverLakhs} Lakhs Family Sum Insured`,
      why_matched: `Rule-engine family floater sizing covering you and ${dependents} dependent(s).`,
      apply_url: "https://www.starhealth.in/health-insurance/family-health-optima/"
    });
    insurance.push({
      id: "ins_hdfc_term", category: "insurance", name: "HDFC Life Click 2 Protect Super", provider: "HDFC Life",
      category_label: "Term + Critical Illness Rider", match_score: 92,
      headline: "99.3% Claim Settlement Ratio with Critical Illness Rider",
      personalized_metric: `₹${lifeCoverCrores} Crore Alternative Term Quote`,
      why_matched: "Compare private-insurer critical illness riders for the same rule-sized mortality cover.",
      apply_url: "https://www.hdfclife.com/term-insurance-plans/click-2-protect-super"
    });
  } else {
    insurance.push({
      id: "ins_care_indiv", category: "insurance", name: "Care Advantage Individual Health Plan", provider: "Care Health Insurance",
      category_label: "Individual Medical Cover", match_score: 96,
      headline: "Individual Hospitalisation Cover with Unlimited Recharge",
      personalized_metric: `₹${healthCoverLakhs} Lakhs Individual Cover • Sec 80D eligible`,
      why_matched: `With ${dependents} dependents, term life cover is not required; RULE_INS_03 prioritizes ₹${healthCoverLakhs}L medical cover.`,
      apply_url: "https://www.careinsurance.com/health-insurance-plans.html"
    });
    insurance.push({
      id: "ins_ergo_secure", category: "insurance", name: "HDFC ERGO Optima Secure Health", provider: "HDFC ERGO",
      category_label: "2X Day-1 Medical Shield", match_score: 93,
      headline: "Zero Room-Rent Capping + 2X Coverage from Day 1",
      personalized_metric: `₹${healthCoverLakhs}L Base + Restore Cushion`,
      why_matched: "Protects your own earning capacity and liquid investments against major hospital bills.",
      apply_url: "https://www.hdfcergo.com/health-insurance/optima-secure"
    });
    insurance.push({
      id: "ins_nps", category: "insurance", name: "National Pension System (NPS Tier-I)", provider: "PFRDA / eNPS",
      category_label: "Longevity & Pension Shield", match_score: 91,
      headline: "Sovereign Retirement Corpus • Ultra-Low 0.09% Fee",
      personalized_metric: "Extra ₹50,000 Sec 80CCD(1B) tax deduction",
      why_matched: "Without dependents requiring mortality cover, pension compounding strengthens long-term self-reliance.",
      apply_url: "https://enps.nsdl.com/eNPS/NationalPensionSystem.html"
    });
  }

  // Investments (3 Options)
  const investments = [];
  const sipMetric = suggestedSip > 0 ? `~₹${suggestedSip.toLocaleString("en-IN")}/mo SIP` : "Build cash surplus first";
  investments.push({
    id: "inv_nifty", category: "investments", name: "UTI Nifty 50 Index Fund", provider: "UTI Mutual Fund",
    category_label: "Core Index Equity", match_score: 96,
    headline: "Low-Cost Passive Exposure to India's Top 50 Companies",
    personalized_metric: `${equityPct !== null ? equityPct + "% Equity Split • " : ""}${sipMetric}`,
    why_matched: `Allocation follows RULE_INV_01 for age ${age}y and goal '${goal}'.`,
    apply_url: "https://www.utimf.com/mutual-fund-products/equity-funds/uti-nifty-50-index-fund"
  });
  investments.push({
    id: "inv_hybrid", category: "investments", name: "ICICI Prudential Balanced Advantage Fund", provider: "Groww / ICICI Prudential AMC",
    category_label: "Dynamic Hybrid Guard", match_score: 93,
    headline: "Valuation-Driven Equity/Debt Rebalancing",
    personalized_metric: equityPct !== null ? `Complements ${100 - equityPct}% Debt & Gold sleeve` : "Dynamic Equity/Debt Split",
    why_matched: "Automatically shifts exposure between equity and debt based on market valuations.",
    apply_url: "https://groww.in/mutual-funds/icici-prudential-balanced-advantage-fund-direct-growth"
  });
  investments.push({
    id: "inv_ppf", category: "investments", name: "Public Provident Fund (PPF)", provider: "India Post / State Bank of India",
    category_label: "Sovereign Debt & Reserve", match_score: 91,
    headline: "Sovereign-Backed Fixed Income • EEE Tax-Exempt Interest",
    personalized_metric: `7.10% Tax-Free • ₹${emergencyBufferLakhs}L Reserve Target`,
    why_matched: `Anchors your 6-month emergency reserve target (₹${emergencyBufferLakhs} Lakhs).`,
    apply_url: "https://www.indiapost.gov.in/Financial/Pages/Content/Post-Office-Saving-Schemes.aspx"
  });

  return { cards, loans, insurance, investments };
}

// ==============================================================================
// 7. Apple Score Meter (240-degree Pastel Arc)
// ==============================================================================
function updateOptimizedAppleGauge(score, tierLabel) {
  const numEl = document.getElementById("gauge-num");
  const arcFill = document.getElementById("gauge-arc-fill");
  const pillText = document.getElementById("gauge-pill-text");
  const statusBadge = document.getElementById("fhi-status-badge");

  if (!numEl || !arcFill) return;
  numEl.textContent = score;

  const sweep = Math.max(10, Math.min(293.2, (score / 100) * 293.2));
  arcFill.setAttribute("stroke-dasharray", `${sweep} 440`);

  const tierStyle = [
    ["OPTIMAL", "apple-pill mint", "url(#meter-mint-grad)"],
    ["STABLE", "apple-pill sky", "url(#meter-sky-grad)"],
    ["VULNERABLE", "apple-pill amber", "url(#meter-amber-grad)"],
  ].find(([key]) => String(tierLabel).startsWith(key)) || [null, "apple-pill coral", "url(#meter-amber-grad)"];
  const pillClass = tierStyle[1];
  const gradUrl = tierStyle[2];

  arcFill.setAttribute("stroke", gradUrl);
  if (pillText) {
    pillText.textContent = tierLabel;
    pillText.className = pillClass;
  }
  if (statusBadge) {
    statusBadge.textContent = tierLabel;
    statusBadge.className = pillClass;
  }
}

// ==============================================================================
// 8. What-If Stress Simulator
// ==============================================================================
let stressTimer = null;
let stressRequestId = 0;

function updateStressSim() {
  const rateBps = numVal("s_rate", 150);
  const incomeDropPct = numVal("s_income_drop", 15);
  document.getElementById("disp_stress_rate").textContent = `+${(rateBps / 100).toFixed(2)}% higher interest`;
  document.getElementById("disp_stress_income").textContent = `-${incomeDropPct}% pay cut`;

  if (stressTimer) clearTimeout(stressTimer);
  stressTimer = setTimeout(() => runStressTest(rateBps, incomeDropPct), 150);
}

async function runStressTest(rateBps, incomeDropPct) {
  const requestId = ++stressRequestId;
  let r = null;
  try {
    const res = await postJson("/api/stress-test", {
      monthly_income: currentProfile.income,
      existing_emis: currentProfile.emis,
      rate_hike_bps: rateBps,
      income_drop_pct: incomeDropPct
    });
    r = res.ok ? await res.json() : null;
  } catch (err) {
    console.warn("Stress test request failed:", err);
  }
  if (requestId !== stressRequestId) return;
  renderStress(r, rateBps, incomeDropPct);
}

function renderStress(r, rateBps, incomeDropPct) {
  const foirNumEl = document.getElementById("s_disp_foir");
  const foirNoteEl = document.getElementById("s_disp_foir_status");
  const banner = document.getElementById("stress-banner");
  const icon = document.getElementById("stress-alert-icon");
  const iconUse = document.getElementById("stress-alert-icon-use");
  const title = document.getElementById("stress-alert-title");
  const desc = document.getElementById("stress-alert-desc");

  if (!r) {
    foirNumEl.textContent = "—";
    foirNoteEl.textContent = "Server unreachable";
    return;
  }

  const incomeDiff = r.stressed_income - currentProfile.income;
  const emiDiff = r.stressed_emis - currentProfile.emis;
  document.getElementById("s_disp_inflow").textContent = rupees(r.stressed_income);
  document.getElementById("s_disp_inflow_diff").textContent =
    (incomeDiff < 0 ? "-" : "+") + rupees(Math.abs(incomeDiff)) + " / month";
  document.getElementById("s_disp_emis").textContent = rupees(r.stressed_emis);
  document.getElementById("s_disp_emis_diff").textContent = "+" + rupees(emiDiff) + " / month higher";
  foirNumEl.textContent = r.stressed_foir.toFixed(1) + "%";

  const tone = r.insolvent ? "coral" : "mint";
  foirNumEl.style.color = `var(--pastel-${tone}-text)`;
  foirNoteEl.textContent = r.insolvent ? "Too High (Over 50% limit)" : "Safe (Under 50% limit)";
  foirNoteEl.style.color = `var(--pastel-${tone}-text)`;
  banner.style.background = `var(--pastel-${tone}-bg)`;
  banner.style.borderColor = `var(--pastel-${tone}-border)`;
  if (iconUse) iconUse.setAttribute("href", r.insolvent ? "#i-report" : "#i-verified");
  if (icon) icon.style.color = `var(--pastel-${tone}-solid)`;
  title.style.color = `var(--pastel-${tone}-text)`;
  desc.style.color = `var(--pastel-${tone}-text)`;
  if (r.insolvent) {
    title.textContent = "Caution: Loans Would Exceed Safe 50% Limit";
    desc.textContent = `Under this scenario, loan EMIs would take ${r.stressed_foir.toFixed(1)}% of your monthly pay. Planners recommend keeping total loan payments below 50% so essentials stay covered.`;
  } else {
    title.textContent = "Your Budget Stays Safe & Protected";
    desc.textContent = `Even with a ${incomeDropPct}% pay cut and +${(rateBps / 100).toFixed(2)}% higher loan interest, loans take ${r.stressed_foir.toFixed(1)}% of your salary, leaving ${rupees(r.leftover_cashflow)}/mo.`;
  }
}

// ==============================================================================
// 9. PDF Export
// ==============================================================================
function exportDossierPDF() {
  const p = currentProfile;
  const query = new URLSearchParams({
    name: "Client",
    income: p.income,
    emis: p.emis,
    credit: p.creditScore,
    age: p.age,
    deps: p.dependents,
    employment: p.employment,
    risk: p.risk,
    spend: p.spendCategory,
    goal: p.goal,
  });
  window.location.href = `/api/export-pdf?${query.toString()}`;
}
