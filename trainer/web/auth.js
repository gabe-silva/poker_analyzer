const els = {};
const params = new URLSearchParams(window.location.search);
const nextPath = sanitizeNext(params.get("next"));

document.addEventListener("DOMContentLoaded", () => {
  mapIds([
    "emailInput",
    "codeInput",
    "subscribeBtn",
    "requestCodeBtn",
    "verifyCodeBtn",
    "portalBtn",
    "continueBtn",
    "logoutBtn",
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
  els.subscribeBtn?.addEventListener("click", startCheckout);
  els.requestCodeBtn?.addEventListener("click", requestCode);
  els.verifyCodeBtn?.addEventListener("click", verifyCode);
  els.portalBtn?.addEventListener("click", openBillingPortal);
  els.continueBtn?.addEventListener("click", () => {
    window.location.href = nextPath;
  });
  els.logoutBtn?.addEventListener("click", logout);
}

async function bootstrap() {
  const status = await apiGet("/api/auth/status");
  if (status.authenticated && status.email) {
    els.emailInput.value = status.email;
    setStatus(`Signed in as ${status.email}.`);
  } else {
    setStatus("Enter your email to subscribe or receive a login code.");
  }

  const billing = params.get("billing");
  const error = params.get("error");
  if (billing === "cancelled") {
    setStatus("Checkout cancelled. You can restart anytime.", true);
  }
  if (error === "payment_not_verified") {
    setStatus("Could not verify payment. Contact support if this persists.", true);
  }
}

async function startCheckout() {
  const email = normalizedEmail();
  if (!email) {
    setStatus("Enter a valid email first.", true);
    return;
  }
  setBusy(true);
  try {
    const session = await apiPost("/api/billing/create-checkout-session", { email });
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
    setStatus(`Login code sent to ${email}.${debug}`);
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
  if (!value) return "/setup.html";
  if (!value.startsWith("/")) return "/setup.html";
  if (value.startsWith("//")) return "/setup.html";
  return value;
}

function setBusy(isBusy) {
  [
    els.subscribeBtn,
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
