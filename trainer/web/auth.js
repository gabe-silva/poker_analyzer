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
    input.addEventListener("change", renderPlanSummary);
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

  renderPlanSummary();
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

function renderPlanSummary() {
  if (!els.planSummary) return;
  const tier = selectedPlanTier();
  const selected = planByTier(tier);
  const currentTier = normalizePlanTier(authSnapshot?.plan?.tier) || "free";
  const currentLabel = String(authSnapshot?.plan?.label || currentTier).trim();
  const checkoutEnabled = !!selected?.checkout_enabled;

  const parts = [];
  parts.push(`Current plan: ${currentLabel}`);

  if (tier === "free") {
    parts.push("Free uses email-code login directly.");
  } else if (!checkoutEnabled) {
    parts.push(`${tier.toUpperCase()} checkout is not configured yet.`);
  } else {
    const price = Number(selected?.monthly_price_usd || 0);
    const text = price > 0 ? `$${price}/mo` : "paid tier";
    parts.push(`${tier.toUpperCase()} checkout ready (${text}).`);
  }

  if (currentTier === tier) {
    parts.push("You can request a login code now.");
  }

  els.planSummary.textContent = parts.join(" ");
}

async function continueWithSelectedPlan() {
  const tier = selectedPlanTier();
  if (tier === "free") {
    await requestCode();
    return;
  }
  await startCheckout(tier);
}

async function startCheckout(planTier) {
  const email = normalizedEmail();
  if (!email) {
    setStatus("Enter a valid email first.", true);
    return;
  }
  setBusy(true);
  try {
    const session = await apiPost("/api/billing/create-checkout-session", {
      email,
      plan_tier: planTier,
    });
    if (!session?.url) {
      throw new Error("Checkout URL missing from server response");
    }
    window.location.href = session.url;
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    setBusy(false);
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
    window.location.href = result.url;
  } catch (err) {
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
}

function setStatus(message, isError = false) {
  if (!els.statusLine) return;
  els.statusLine.textContent = message;
  els.statusLine.style.color = isError ? "#e6a1a1" : "#f0dca8";
}

async function apiGet(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function apiPost(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
