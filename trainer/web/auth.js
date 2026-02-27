const els = {};
const params = new URLSearchParams(window.location.search);
const nextPath = sanitizeNext(params.get("next"));

let authSnapshot = null;
let plansSnapshot = [];

document.addEventListener("DOMContentLoaded", () => {
  mapIds([
    "emailInput",
    "codeInput",
    "startPlanBtn",
    "requestCodeBtn",
    "verifyCodeBtn",
    "portalBtn",
    "continueBtn",
    "logoutBtn",
    "planSummary",
    "statusLine",
  ]);
  bindEvents();
  bootstrap().catch((err) => setStatus(err.message, true));
});

function mapIds(ids) {
  ids.forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function bindEvents() {
  els.startPlanBtn?.addEventListener("click", continueWithSelectedPlan);
  els.requestCodeBtn?.addEventListener("click", requestCode);
  els.verifyCodeBtn?.addEventListener("click", verifyCode);
  els.portalBtn?.addEventListener("click", openBillingPortal);
  els.continueBtn?.addEventListener("click", () => {
    window.location.href = nextPath;
  });
  els.logoutBtn?.addEventListener("click", logout);
  document.querySelectorAll("input[name='planTier']").forEach((input) => {
    input.addEventListener("change", refreshAccountUi);
  });
}

async function bootstrap() {
  const status = await apiGet("/api/auth/status");
  authSnapshot = status;
  plansSnapshot = Array.isArray(status?.plans) ? status.plans : [];

  const preselect = normalizePlanTier(params.get("plan"));
  setSelectedPlanTier(preselect || status?.plan?.tier || "free");

  if (status.authenticated && status.email) {
    els.emailInput.value = status.email;
    setStatus(`Signed in as ${status.email}.`);
  } else {
    setStatus("Enter your email, choose a plan, then request a login code.");
  }

  const billing = params.get("billing");
  const error = params.get("error");
  if (billing === "cancelled") {
    setStatus("Checkout cancelled. You can restart anytime.", true);
  }
  if (error === "payment_not_verified") {
    setStatus("Could not verify payment. Contact support if this persists.", true);
  }

  refreshAccountUi();
}

function normalizePlanTier(raw) {
  const tier = String(raw || "").trim().toLowerCase();
  if (tier === "pro" || tier === "elite" || tier === "free") return tier;
  return "";
}

function selectedPlanTier() {
  const checked = document.querySelector("input[name='planTier']:checked");
  return normalizePlanTier(checked?.value) || "free";
}

function setSelectedPlanTier(tier) {
  const target = normalizePlanTier(tier) || "free";
  const input = document.querySelector(`input[name='planTier'][value='${target}']`);
  if (input) {
    input.checked = true;
  }
}

function planByTier(tier) {
  return plansSnapshot.find((p) => normalizePlanTier(p?.tier) === normalizePlanTier(tier)) || null;
}

function currentPlanTier() {
  return normalizePlanTier(authSnapshot?.plan?.tier) || "free";
}

function renderPlanSummary() {
  if (!els.planSummary) return;
  const tier = selectedPlanTier();
  const selected = planByTier(tier);
  const currentTier = currentPlanTier();
  const currentLabel = String(authSnapshot?.plan?.label || currentTier).trim();
  const checkoutEnabled = !!selected?.checkout_enabled;

  const parts = [];
  parts.push(`Current plan: ${currentLabel}`);

  if (tier === "free") {
    parts.push("Free uses email-code login directly.");
  } else if (!checkoutEnabled) {
    parts.push(`${tier.toUpperCase()} checkout is not configured yet.`);
  } else {
    const selectedLabel = checkoutPlanLabel(tier);
    parts.push(`Selected: ${selectedLabel}. Click ${newAccountCtaLabel(tier)} to open Stripe checkout.`);
  }

  if (currentTier === tier) {
    parts.push("You can request a login code now.");
  }
  if (tier !== "free" || !!authSnapshot?.plan?.paid) {
    parts.push("If you switch tiers, cancel any unused subscriptions in Manage Billing.");
  }

  els.planSummary.textContent = parts.join(" ");
}

function refreshTierPlaybook() {
  const tier = selectedPlanTier();
  document.querySelectorAll("[data-tier-help]").forEach((node) => {
    const cardTier = normalizePlanTier(node.getAttribute("data-tier-help"));
    node.hidden = cardTier !== tier;
  });
}

function refreshActionVisibility() {
  const tier = selectedPlanTier();
  const currentTier = currentPlanTier();
  const isAuthenticated = !!authSnapshot?.authenticated;
  const hasPaidPlan = !!authSnapshot?.plan?.paid;
  const checkoutReady = !!planByTier(tier)?.checkout_enabled;

  if (tier === "free") {
    if (els.startPlanBtn) {
      els.startPlanBtn.textContent = "Start Free";
      els.startPlanBtn.disabled = false;
    }
    toggleVisible(els.requestCodeBtn, false);
    toggleVisible(els.verifyCodeBtn, true);
    if (els.verifyCodeBtn) els.verifyCodeBtn.disabled = false;
    toggleVisible(els.portalBtn, false);
  } else {
    const newAccountLabel = newAccountCtaLabel(tier);
    if (els.startPlanBtn) {
      els.startPlanBtn.textContent = newAccountLabel;
      els.startPlanBtn.disabled = !checkoutReady;
    }
    toggleVisible(els.requestCodeBtn, true);
    toggleVisible(els.verifyCodeBtn, true);
    const canRequestCode = isAuthenticated || currentTier === tier;
    if (els.requestCodeBtn) {
      els.requestCodeBtn.textContent = canRequestCode ? "Email Login Code" : "Email Login Code (after checkout)";
      els.requestCodeBtn.disabled = !canRequestCode;
    }
    if (els.verifyCodeBtn) els.verifyCodeBtn.disabled = !canRequestCode;
    toggleVisible(els.portalBtn, isAuthenticated && hasPaidPlan);
  }

  toggleVisible(els.continueBtn, isAuthenticated);
  toggleVisible(els.logoutBtn, isAuthenticated);
}

function newAccountCtaLabel(tier) {
  const normalized = normalizePlanTier(tier);
  if (normalized === "elite") return "Continue With New Elite Account";
  if (normalized === "pro") return "Continue With New Pro Account";
  return "Start Free";
}

function checkoutPlanLabel(tier) {
  const normalized = normalizePlanTier(tier);
  const plan = planByTier(normalized);
  const fallback = normalized === "elite" ? "Elite Plan ($39/mo)" : normalized === "pro" ? "Pro Plan ($29/mo)" : "Free";
  const price = Number(plan?.monthly_price_usd || 0);
  const label = String(plan?.label || "").trim();
  if (label) {
    if (price > 0 && !/\$\d+/.test(label)) {
      return `${label} ($${price}/mo)`;
    }
    return label;
  }
  if (price > 0 && normalized !== "free") {
    const title = normalized === "elite" ? "Elite Plan" : "Pro Plan";
    return `${title} ($${price}/mo)`;
  }
  return fallback;
}

function refreshAccountUi() {
  renderPlanSummary();
  refreshTierPlaybook();
  refreshActionVisibility();
}

function toggleVisible(element, show) {
  if (!element) return;
  element.hidden = !show;
}

async function continueWithSelectedPlan() {
  const tier = selectedPlanTier();
  if (tier === "free") {
    await requestCode();
    return;
  }
  await startCheckout(tier);
}

function checkoutEmail() {
  return normalizedEmail() || String(authSnapshot?.email || "").trim().toLowerCase();
}

async function startCheckout(planTier, options = {}) {
  const { manageBusy = true } = options;
  const email = checkoutEmail();
  if (!email) {
    setStatus("Enter a valid email first.", true);
    return;
  }
  if (manageBusy) setBusy(true);
  try {
    const session = await apiPost("/api/billing/create-checkout-session", {
      email,
      plan_tier: planTier,
    });
    const checkoutUrl = String(session?.url || "").trim();
    if (!checkoutUrl) {
      throw new Error("Checkout URL missing from server response");
    }
    let target = null;
    try {
      target = new URL(checkoutUrl);
    } catch (err) {
      throw new Error("Received invalid Stripe checkout URL. Verify Stripe keys and price IDs.");
    }
    window.location.href = target.toString();
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    if (manageBusy) setBusy(false);
  }
}

async function requestCode() {
  const email = normalizedEmail();
  if (!email) {
    setStatus("Enter a valid email first.", true);
    return;
  }
  setBusy(true);
  try {
    const response = await apiPost("/api/auth/request-code", { email });
    const debug = response.debug_code ? ` Debug code: ${response.debug_code}` : "";
    const planNote = response.plan_tier ? ` (${String(response.plan_tier).toUpperCase()} access)` : "";
    setStatus(`Login code sent to ${email}${planNote}.${debug}`);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    setBusy(false);
  }
}

async function verifyCode() {
  const email = normalizedEmail();
  const code = String(els.codeInput?.value || "").trim();
  if (!email) {
    setStatus("Enter a valid email first.", true);
    return;
  }
  if (!/^\d{6}$/.test(code)) {
    setStatus("Enter the 6-digit login code.", true);
    return;
  }
  setBusy(true);
  try {
    await apiPost("/api/auth/verify-code", { email, code });
    setStatus("Signed in. Redirecting...");
    window.location.href = nextPath;
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    setBusy(false);
  }
}

async function openBillingPortal() {
  setBusy(true);
  try {
    const result = await apiPost("/api/billing/create-portal-session", {});
    if (!result?.url) {
      throw new Error("Billing portal URL missing");
    }
    let target = null;
    try {
      target = new URL(String(result.url || "").trim());
    } catch (err) {
      throw new Error("Received invalid billing portal URL from server.");
    }
    window.location.href = target.toString();
  } catch (err) {
    const message = String(err.message || "");
    if (
      /No Stripe customer linked|No billing profile found|No paid billing profile/i.test(message)
    ) {
      const tier = selectedPlanTier();
      if (tier === "free") {
        setStatus(
          "No paid billing account found yet. Select Pro or Elite and click Continue With Plan first.",
          true
        );
      } else {
        setStatus("No billing profile found yet. Starting checkout for selected plan...");
        await startCheckout(tier, { manageBusy: false });
      }
      return;
    }
    setStatus(err.message, true);
  } finally {
    setBusy(false);
  }
}

async function logout() {
  setBusy(true);
  try {
    await apiPost("/api/auth/logout", {});
    setStatus("Logged out.");
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    setBusy(false);
  }
}

function normalizedEmail() {
  return String(els.emailInput?.value || "").trim().toLowerCase();
}

function sanitizeNext(raw) {
  const value = String(raw || "").trim();
  if (!value) return "/play.html";
  if (!value.startsWith("/")) return "/play.html";
  if (value.startsWith("//")) return "/play.html";
  return value;
}

function setBusy(isBusy) {
  [
    els.startPlanBtn,
    els.requestCodeBtn,
    els.verifyCodeBtn,
    els.portalBtn,
    els.continueBtn,
    els.logoutBtn,
  ].forEach((btn) => {
    if (btn) btn.disabled = isBusy;
  });
  if (!isBusy) {
    refreshActionVisibility();
  }
}

function setStatus(message, isError = false) {
  if (!els.statusLine) return;
  els.statusLine.textContent = message;
  els.statusLine.style.color = isError ? "#e6a1a1" : "#f0dca8";
}

async function apiGet(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  return parseApiResponse(res);
}

async function apiPost(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseApiResponse(res);
}

async function parseApiResponse(res) {
  const raw = await res.text();
  let data = {};
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch (err) {
      data = {};
    }
  }
  if (!res.ok) {
    const fallback = raw ? raw.replace(/\s+/g, " ").trim().slice(0, 180) : "";
    throw new Error(data.error || fallback || `HTTP ${res.status}`);
  }
  return data;
}
