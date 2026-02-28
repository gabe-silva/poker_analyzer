const LIVE_SESSION_KEY = "trainer:liveSessionId";
const SETUP_STORAGE_KEY = "trainer:setupConfigV1";
const PLAY_MODE_KEY = "trainer:playModeV1";

const state = {
  config: null,
  auth: null,
  plan: null,
  trainingWorkspace: false,
  playMode: "full_match",
  session: null,
  liveSelectedAction: null,
  liveSelectedSize: null,
  liveSelectedIntent: "value",
  drillScenario: null,
  drillOpponentProfile: null,
  drillMappedArchetype: null,
  drillSelectedAction: null,
  drillSelectedSize: null,
  drillSelectedIntent: "value",
  analyzedProfile: null,
  comparedProfiles: [],
  compareLookup: {
    byText: new Map(),
    bySelectionKey: new Set(),
    bySelectionKeyDisplay: new Map(),
  },
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  bootstrap().catch((err) => setStatus(`Play init failed: ${err.message}`, true));
});

function mapIds(ids) {
  ids.forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function currentPlan() {
  return state.plan || {};
}

function featureEnabled(key) {
  return !!currentPlan()[key];
}

function maxAliasesPerProfile() {
  return Number(currentPlan().max_aliases_per_profile || 12);
}

function maxCompareGroups() {
  return Number(currentPlan().max_compare_groups || 1);
}

function workspaceMode() {
  const params = new URLSearchParams(window.location.search);
  return String(params.get("workspace") || "").trim().toLowerCase();
}

function isTrainingWorkspace() {
  return workspaceMode() === "training";
}

function renderPlanBadge() {
  if (!els.planBadge) return;
  const plan = currentPlan();
  const label = String(plan.label || "Free");
  const tier = String(plan.tier || "free").toUpperCase();
  const handLimit = Number(plan.max_upload_hands || 500);
  const exploitText = plan.show_exploits ? "Exploit reports: on" : "Exploit reports: off";
  els.planBadge.textContent = `Plan: ${label} (${tier}) | Upload cap: ${handLimit} total hands | ${exploitText}`;
}

function applyWorkspacePresentation() {
  const training = !!state.trainingWorkspace;

  if (els.navAnalyzerLink) {
    els.navAnalyzerLink.classList.toggle("active", !training);
  }
  if (els.navTrainerLink) {
    els.navTrainerLink.classList.toggle("active", training);
  }
  if (els.playWorkspaceTitle) {
    els.playWorkspaceTitle.textContent = training ? "Friend Training Workspace" : "Analyzer";
  }
  if (els.playWorkspaceSubtitle) {
    els.playWorkspaceSubtitle.textContent = training
      ? "Trainer workspace: run Elite friend matches from uploaded player profiles."
      : "Analyze profile stats and compare players side-by-side.";
  }
  if (els.analyzerGuide) {
    els.analyzerGuide.style.display = training ? "none" : "block";
  }
  if (els.analyzerActionGuide) {
    els.analyzerActionGuide.style.display = training ? "none" : "block";
  }
  if (els.trainingWorkspaceNotice) {
    els.trainingWorkspaceNotice.style.display = training ? "block" : "none";
  }
  if (els.analyzerPlayersLabel) {
    els.analyzerPlayersLabel.childNodes[0].textContent = training
      ? "Friend username (select one)"
      : "Friend usernames (select one or more aliases)";
  }
  if (els.analyzerPlayers) {
    els.analyzerPlayers.multiple = !training;
    if (training && els.analyzerPlayers.options.length > 0) {
      const selected = Array.from(els.analyzerPlayers.selectedOptions || []);
      if (!selected.length) {
        els.analyzerPlayers.options[0].selected = true;
      } else if (selected.length > 1) {
        const keep = selected[0].value;
        Array.from(els.analyzerPlayers.options).forEach((opt) => {
          opt.selected = opt.value === keep;
        });
      }
    }
  }
  if (els.targetConfigGuide) {
    els.targetConfigGuide.style.display = training ? "block" : "none";
  }
}

async function bootstrap() {
  mapIds([
    "navAnalyzerLink",
    "navTrainerLink",
    "playWorkspaceTitle",
    "playWorkspaceSubtitle",
    "analyzerGuide",
    "analyzerActionGuide",
    "trainingWorkspaceNotice",
    "analyzerPlayersLabel",
    "targetConfigGuide",
    "planBadge",
    "modeToggleRow",
    "playModeFull",
    "playModeDrill",
    "handsFiles",
    "uploadHandsBtn",
    "analyzerPlayers",
    "analyzeProfileBtn",
    "compareProfilesBtn",
    "analysisActionsRow",
    "compareConfig",
    "comparePlayerA",
    "comparePlayerB",
    "comparePlayerList",
    "comparisonPanel",
    "comparisonDashboard",
    "profilePanel",
    "profileDashboard",
    "trainingStyleWrap",
    "trainingStyle",
    "handsStatus",
    "uploadedFileList",
    "startingStackWrap",
    "startingStackBb",
    "targetedMode",
    "targetedModeWrap",
    "targetConfigWrap",
    "tStreet",
    "tNodeType",
    "tActionContext",
    "tHeroPosition",
    "fullModeActions",
    "drillModeActions",
    "startLiveBtn",
    "nextHandBtn",
    "startDrillBtn",
    "newDrillBtn",
    "fullModePanel",
    "drillModePanel",
    "liveMeta",
    "balanceTracker",
    "liveTable",
    "liveActions",
    "drillMeta",
    "drillTable",
    "drillPrompt",
    "drillDecisionPanel",
    "drillFeedbackSummary",
    "drillEvTableWrap",
    "drillLeakBreakdownWrap",
    "matchNotesPanel",
    "opponentSummary",
    "statusLine",
  ]);

  state.auth = await apiGet("/api/auth/status");
  state.plan = state.auth?.plan || {
    tier: "free",
    label: "Free",
    max_upload_hands: 500,
    max_aliases_per_profile: 12,
    max_compare_groups: 1,
    show_exploits: false,
    allow_multi_profile_compare: false,
    allow_live_training: false,
  };

  const config = await apiGet("/api/config");
  state.config = config;
  state.trainingWorkspace = isTrainingWorkspace();
  initControls(config);
  applyWorkspacePresentation();
  bindEvents();
  renderPlanBadge();
  applyPlanLocks();
  setOutputView("none");
  try {
    await refreshHandsPlayers(false);
  } catch {
    // Keep booting; user can retry refresh/upload manually.
  }

  setPlayMode("full_match");

  const existing = localStorage.getItem(LIVE_SESSION_KEY);
  if (existing && featureEnabled("allow_live_training") && state.trainingWorkspace) {
    try {
      const restored = await apiGet(`/api/live/state?session_id=${encodeURIComponent(existing)}`);
      renderLiveState(restored);
      if (state.playMode === "full_match") {
        setStatus(`Restored live session ${existing}.`);
      }
    } catch {
      localStorage.removeItem(LIVE_SESSION_KEY);
    }
  } else if (!featureEnabled("allow_live_training") || !state.trainingWorkspace) {
    localStorage.removeItem(LIVE_SESSION_KEY);
  }

  if (!state.trainingWorkspace) {
    setStatus(
      "Ready. Upload files, click Upload Hand Files, select username(s), then Analyze One Player. Friend training is in Trainer.",
    );
    return;
  }

  if (!featureEnabled("allow_live_training")) {
    setStatus("Upgrade to Elite to use Friend Training workspace.", true);
  } else if (!state.session) {
    setStatus("Ready. Upload hand files, select one friend username, then click Start Match.");
  }
}

function initControls(config) {
  const handsStatus = config.live?.hands_status || { players: [], total_files: 0, uploaded_files: [] };
  fillAnalyzerPlayerSelect(handsStatus.players || [], false);
  renderHandsStatus(handsStatus);

  fillSelect(els.tStreet, config.streets.map((v) => ({ value: v, label: titleCase(v) })));
  fillSelect(
    els.tNodeType,
    config.node_types.map((v) => ({ value: v, label: titleCase(v.replaceAll("_", " ")) })),
  );
  fillSelect(
    els.tActionContext,
    config.action_contexts.map((v) => ({ value: v, label: titleCase(v.replaceAll("_", " ")) })),
  );
  fillSelect(els.tHeroPosition, ["BTN", "BB"].map((v) => ({ value: v, label: v })));
  fillSelect(
    els.trainingStyle,
    [
      { value: "balanced_default", label: "Balanced (Optimal Baseline)" },
      ...(config.archetypes || []).map((a) => ({ value: a.key, label: `${a.label} Training` })),
    ],
  );

  const defaults = config.live?.defaults || {};
  els.startingStackBb.value = Number(defaults.starting_stack_bb || 100);
  els.targetedMode.checked = !!defaults.targeted_mode;

  const t = defaults.target_config || {};
  if (t.street) els.tStreet.value = t.street;
  if (t.node_type) els.tNodeType.value = t.node_type;
  if (t.action_context) els.tActionContext.value = t.action_context;
  if (t.hero_position && (t.hero_position === "BTN" || t.hero_position === "BB")) {
    els.tHeroPosition.value = t.hero_position;
  }

  updateTargetModeUi();
  updateSetupDraftUi();
}

function applyPlanLocks() {
  const liveAllowed = featureEnabled("allow_live_training");
  const compareAllowed = featureEnabled("allow_multi_profile_compare");
  const trainingWorkspace = !!state.trainingWorkspace;
  const trainingVisible = liveAllowed && trainingWorkspace;

  if (els.modeToggleRow) els.modeToggleRow.style.display = "none";
  if (els.targetedModeWrap) els.targetedModeWrap.style.display = trainingVisible ? "inline-flex" : "none";
  if (els.targetConfigWrap) els.targetConfigWrap.style.display = trainingVisible ? "block" : "none";
  if (els.fullModeActions) els.fullModeActions.style.display = trainingVisible ? "flex" : "none";
  if (els.drillModeActions) els.drillModeActions.style.display = "none";
  if (els.fullModePanel) els.fullModePanel.style.display = "none";
  if (els.drillModePanel) els.drillModePanel.style.display = "none";
  if (els.matchNotesPanel) els.matchNotesPanel.style.display = "none";
  if (els.trainingStyleWrap) els.trainingStyleWrap.style.display = trainingVisible ? "flex" : "none";
  if (els.startingStackWrap) els.startingStackWrap.style.display = trainingVisible ? "flex" : "none";
  if (els.startingStackBb) els.startingStackBb.disabled = !trainingVisible;

  if (els.analysisActionsRow) {
    els.analysisActionsRow.style.display = trainingWorkspace ? "none" : "flex";
  }
  if (els.compareConfig) {
    els.compareConfig.style.display = "none";
  }

  if (!trainingVisible) {
    state.playMode = "full_match";
    if (els.playModeFull) els.playModeFull.checked = true;
    if (els.playModeDrill) els.playModeDrill.checked = false;
  }

  if (els.compareProfilesBtn) {
    els.compareProfilesBtn.style.display = !trainingWorkspace && compareAllowed ? "inline-flex" : "none";
  }
  if (els.profilePanel && trainingWorkspace) {
    els.profilePanel.style.display = "none";
  }
  if (els.targetedMode) {
    els.targetedMode.disabled = !trainingVisible;
  }
}

function bindEvents() {
  if (els.playModeFull && featureEnabled("allow_live_training")) {
    els.playModeFull.addEventListener("change", () => {
      if (els.playModeFull.checked) setPlayMode("full_match");
    });
  }
  if (els.playModeDrill && featureEnabled("allow_live_training")) {
    els.playModeDrill.addEventListener("change", () => {
      if (els.playModeDrill.checked) setPlayMode("single_hand_drill");
    });
  }

  if (els.targetedMode) {
    els.targetedMode.addEventListener("change", updateTargetModeUi);
  }
  els.uploadHandsBtn.addEventListener("click", uploadHandsFiles);
  els.analyzeProfileBtn.addEventListener("click", analyzeSelectedProfile);
  if (els.compareProfilesBtn) {
    els.compareProfilesBtn.addEventListener("click", () => {
      toggleCompareConfig(true);
      compareProfileGroups();
    });
  }

  if (state.trainingWorkspace) {
    els.startLiveBtn.addEventListener("click", startLiveMatch);
    els.nextHandBtn.addEventListener("click", nextHand);
    els.startDrillBtn.addEventListener("click", startDrillHand);
    els.newDrillBtn.addEventListener("click", startDrillHand);
  }
}

function setPlayMode(mode) {
  if (!featureEnabled("allow_live_training") || !state.trainingWorkspace) {
    state.playMode = "full_match";
    if (els.playModeFull) els.playModeFull.checked = true;
    if (els.playModeDrill) els.playModeDrill.checked = false;
    updateModeUi();
    return;
  }
  state.playMode = mode === "single_hand_drill" ? "single_hand_drill" : "full_match";
  if (els.playModeFull) els.playModeFull.checked = state.playMode === "full_match";
  if (els.playModeDrill) els.playModeDrill.checked = state.playMode === "single_hand_drill";
  localStorage.setItem(PLAY_MODE_KEY, state.playMode);
  updateModeUi();
}

function updateModeUi() {
  if (!featureEnabled("allow_live_training") || !state.trainingWorkspace) {
    if (els.fullModeActions) els.fullModeActions.style.display = "none";
    if (els.drillModeActions) els.drillModeActions.style.display = "none";
    if (els.targetedModeWrap) els.targetedModeWrap.style.display = "none";
    if (els.targetConfigWrap) els.targetConfigWrap.style.display = "none";
    setOutputView("none");
    return;
  }
  const full = state.playMode === "full_match";

  if (els.fullModeActions) els.fullModeActions.style.display = full ? "flex" : "none";
  if (els.drillModeActions) els.drillModeActions.style.display = full ? "none" : "flex";
  if (els.targetedModeWrap) els.targetedModeWrap.style.display = full ? "inline-flex" : "none";
  if (els.targetedMode) els.targetedMode.disabled = !full;

  updateTargetModeUi();
  updateSetupDraftUi();
  toggleCompareConfig(false);

  if (full) {
    if (state.session) {
      setOutputView("live");
      renderLiveOpponentSummary(state.session.match?.opponent || {}, state.session.hand || {});
    } else {
      setOutputView("none");
      els.opponentSummary.textContent = "Opponent summary appears after match start.";
      setStatus("Full Match mode selected. Upload hands, choose one friend username, then click Start Match.");
    }
  } else {
    if (state.drillOpponentProfile) {
      setOutputView("drill");
      renderDrillOpponentSummary(state.drillOpponentProfile, state.drillMappedArchetype, state.drillScenario);
    } else {
      setOutputView("none");
      els.opponentSummary.textContent = "Opponent summary appears after drill hand generation.";
      setStatus("Single Hand Drill mode selected. Choose setup options, then click Start Drill.");
    }
  }
}

function updateTargetModeUi() {
  if (!state.trainingWorkspace) {
    if (els.targetConfigWrap) {
      els.targetConfigWrap.style.display = "none";
    }
    return;
  }
  const full = state.playMode === "full_match";
  const enabled = full ? !!els.targetedMode.checked : true;
  if (els.targetConfigWrap) {
    els.targetConfigWrap.style.display = enabled ? "block" : "none";
  }
}

function toggleCompareConfig(show) {
  if (!els.compareConfig) return;
  const compareAllowed = featureEnabled("allow_multi_profile_compare");
  els.compareConfig.style.display = show && compareAllowed ? "block" : "none";
}

function updateSetupDraftUi() {
  if (!featureEnabled("allow_live_training") || !state.trainingWorkspace) return;
  const draft = loadSetupDraft();
  if (!draft) return;
  if (draft.street && els.tStreet) els.tStreet.value = draft.street;
  if (draft.node_type && els.tNodeType) els.tNodeType.value = draft.node_type;
  if (draft.action_context && els.tActionContext) els.tActionContext.value = draft.action_context;
  if (draft.hero_position && els.tHeroPosition) {
    els.tHeroPosition.value = normalizeHeadsUpPosition(draft.hero_position);
  }
  if (draft.hero_training_style && els.trainingStyle) {
    const optionExists = Array.from(els.trainingStyle.options || []).some(
      (opt) => opt.value === String(draft.hero_training_style),
    );
    if (optionExists) {
      els.trainingStyle.value = String(draft.hero_training_style);
    }
  }
}

function setOutputView(view) {
  const liveAllowed = featureEnabled("allow_live_training");
  const compareAllowed = featureEnabled("allow_multi_profile_compare");
  const trainingWorkspace = !!state.trainingWorkspace;
  if (els.profilePanel) els.profilePanel.style.display = view === "profile" ? "block" : "none";
  if (els.comparisonPanel) {
    els.comparisonPanel.style.display = view === "compare" && compareAllowed ? "block" : "none";
  }
  if (els.fullModePanel) {
    els.fullModePanel.style.display = view === "live" && liveAllowed && trainingWorkspace ? "block" : "none";
  }
  if (els.drillModePanel) {
    els.drillModePanel.style.display = view === "drill" && liveAllowed && trainingWorkspace ? "block" : "none";
  }
  if (els.matchNotesPanel) {
    els.matchNotesPanel.style.display =
      (view === "live" || view === "drill") && liveAllowed && trainingWorkspace ? "block" : "none";
  }
}

function parseNumber(id, fallback) {
  const value = Number(els[id]?.value);
  if (!Number.isFinite(value)) return fallback;
  return value;
}

function normalizeHeadsUpPosition(value) {
  return value === "BB" ? "BB" : "BTN";
}

function buildTargetConfig(force = false) {
  if (!force && !els.targetedMode.checked) return null;

  if (state.trainingWorkspace) {
    const draft = loadSetupDraft();
    if (draft) {
      return {
        street: draft.street || els.tStreet.value,
        node_type: draft.node_type || els.tNodeType.value,
        action_context: draft.action_context || els.tActionContext.value,
        hero_position: normalizeHeadsUpPosition(draft.hero_position || els.tHeroPosition.value),
      };
    }
  }

  return {
    street: els.tStreet.value,
    node_type: els.tNodeType.value,
    action_context: els.tActionContext.value,
    hero_position: normalizeHeadsUpPosition(els.tHeroPosition.value),
  };
}

function loadSetupDraft() {
  const raw = localStorage.getItem(SETUP_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function fillAnalyzerPlayerSelect(players, preserveSelection = true) {
  const previouslySelected = preserveSelection ? new Set(getSelectedAnalyzerPlayers()) : new Set();
  const options = (players || [])
    .map((row) => {
      const selectionKey = String(row.selection_key || row.player_id || row.username || "").trim();
      if (!selectionKey) return "";
      const displayName = String(
        row.display_name ||
          (Array.isArray(row.usernames) && row.usernames.length ? row.usernames.join(" / ") : row.username || ""),
      ).trim();
      if (!displayName) return "";
      const handsSeen = Number(row.hands_seen || 0);
      const label = `${displayName.toUpperCase()} (${handsSeen} hands)`;
      const selected = previouslySelected.has(selectionKey) ? " selected" : "";
      return `<option value="${escapeHtml(selectionKey)}"${selected}>${escapeHtml(label)}</option>`;
    })
    .filter(Boolean)
    .join("");
  els.analyzerPlayers.innerHTML = options;
  if (!els.analyzerPlayers.selectedOptions.length && els.analyzerPlayers.options.length > 0) {
    els.analyzerPlayers.options[0].selected = true;
  }
  renderComparePlayerChoices(players || []);
}

function getSelectedAnalyzerPlayers() {
  const selected = Array.from(els.analyzerPlayers?.selectedOptions || [])
    .map((opt) => String(opt.value || "").trim())
    .filter(Boolean);
  if (state.trainingWorkspace) {
    return selected.length ? [selected[0]] : [];
  }
  return selected;
}

function renderComparePlayerChoices(players) {
  if (!els.comparePlayerList) return;
  const byText = new Map();
  const bySelectionKey = new Set();
  const bySelectionKeyDisplay = new Map();
  const items = [];
  for (const row of players || []) {
    const selectionKey = String(row?.selection_key || "").trim();
    if (!selectionKey) continue;
    const displayName = String(row?.display_name || row?.username || "").trim();
    if (!displayName) continue;
    const handsSeen = Number(row?.hands_seen || 0);
    items.push({ selectionKey, displayName, handsSeen });
    bySelectionKey.add(selectionKey);
    bySelectionKeyDisplay.set(selectionKey, displayName);
    byText.set(displayName.toLowerCase(), selectionKey);
    byText.set(selectionKey.toLowerCase(), selectionKey);
    const aliases = Array.isArray(row?.usernames) ? row.usernames : [];
    for (const alias of aliases) {
      const token = String(alias || "").trim();
      if (!token) continue;
      byText.set(token.toLowerCase(), selectionKey);
    }
  }

  const unique = [];
  const seenDisplay = new Set();
  for (const item of items) {
    const key = item.displayName.toLowerCase();
    if (seenDisplay.has(key)) continue;
    seenDisplay.add(key);
    unique.push(item);
  }
  unique.sort((a, b) => b.handsSeen - a.handsSeen || a.displayName.localeCompare(b.displayName));

  els.comparePlayerList.innerHTML = unique
    .map((item) => `<option value="${escapeHtml(item.displayName)}"></option>`)
    .join("");

  state.compareLookup = { byText, bySelectionKey, bySelectionKeyDisplay };
}

function renderHandsStatus(status) {
  const files = Array.isArray(status?.uploaded_files) ? status.uploaded_files : [];
  const totalFiles = Number(status?.total_files || files.length || 0);
  const totalPlayers = Number(status?.total_players || 0);
  const totalHands = Number(status?.total_hands || 0);
  renderUploadedFileList(files);
  if (!totalFiles) {
    els.handsStatus.textContent = "No uploaded files yet. Upload one or more PokerNow JSON files to build friend profiles.";
    return;
  }
  const recent = files.slice(-4).join(", ");
  els.handsStatus.textContent =
    `Uploaded files: ${totalFiles} | Players found: ${totalPlayers} | Hands parsed: ${totalHands}` +
    (recent ? ` | Recent: ${recent}` : "");
}

function renderUploadedFileList(files) {
  if (!els.uploadedFileList) return;
  const list = Array.isArray(files) ? files : [];
  if (!list.length) {
    els.uploadedFileList.innerHTML = "";
    return;
  }
  els.uploadedFileList.innerHTML = list
    .map(
      (filename) => `
      <div class="uploaded-file-row">
        <span class="uploaded-file-name">${escapeHtml(filename)}</span>
        <button class="btn-danger-soft" type="button" data-filename="${escapeHtml(filename)}">Remove</button>
      </div>
    `,
    )
    .join("");

  els.uploadedFileList.querySelectorAll("button[data-filename]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await deleteUploadedFile(btn.getAttribute("data-filename") || "");
    });
  });
}

async function deleteUploadedFile(filename) {
  const cleanName = String(filename || "").trim();
  if (!cleanName) {
    setStatus("Could not remove file: invalid filename.", true);
    return;
  }
  try {
    setStatus(`Removing ${cleanName}...`);
    const status = await apiPost("/api/hands/delete", { filename: cleanName });
    fillAnalyzerPlayerSelect(status.players || [], true);
    renderHandsStatus(status);
    setStatus(`Removed ${cleanName}.`);
  } catch (err) {
    setStatus(`Could not remove file: ${err.message}`, true);
  }
}

async function refreshHandsPlayers(showStatus = true) {
  const status = await apiGet("/api/hands/players");
  fillAnalyzerPlayerSelect(status.players || [], true);
  renderHandsStatus(status);
  if (showStatus) {
    setStatus(`Loaded ${Number(status.total_players || 0)} player buckets from ${Number(status.total_files || 0)} file(s).`);
  }
  return status;
}

async function uploadHandsFiles() {
  const files = Array.from(els.handsFiles?.files || []);
  if (!files.length) {
    setStatus("Choose one or more JSON files first.", true);
    return;
  }
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.name));
  try {
    setStatus(`Uploading ${files.length} file(s)...`);
    const status = await apiUpload("/api/hands/upload", form);
    fillAnalyzerPlayerSelect(status.players || [], false);
    renderHandsStatus(status);
    if (els.handsFiles) els.handsFiles.value = "";
    setStatus(`Upload complete. Found ${Number(status.total_players || 0)} player buckets.`);
  } catch (err) {
    setStatus(`Upload failed: ${err.message}`, true);
  }
}

async function resolveOpponentProfile() {
  const names = getSelectedAnalyzerPlayers();
  if (!names.length) {
    throw new Error("Select at least one friend username");
  }
  const aliasLimit = maxAliasesPerProfile();
  if (names.length > aliasLimit) {
    throw new Error(`Your plan allows up to ${aliasLimit} aliases per profile.`);
  }
  return apiGet(`/api/opponent_profile?name=${encodeURIComponent(names.join(","))}`);
}

function resolveComparePlayerInput(value) {
  const token = String(value || "").trim();
  if (!token) return null;
  const lookup = state.compareLookup || {};
  if (lookup.bySelectionKey instanceof Set && lookup.bySelectionKey.has(token)) {
    return token;
  }
  if (lookup.byText instanceof Map) {
    return lookup.byText.get(token.toLowerCase()) || null;
  }
  return null;
}

function profileStatsPills(profile) {
  return `
    <div class="stat-pill-row">
      <span class="stat-pill">Hands: ${profile.hands_analyzed || 0}</span>
      <span class="stat-pill">VPIP/PFR: ${pct(profile.vpip)} / ${pct(profile.pfr)}</span>
      <span class="stat-pill">3B/Fold3B: ${pct(profile.three_bet)} / ${pct(profile.fold_to_3bet)}</span>
      <span class="stat-pill">AF: ${Number(profile.af || 0).toFixed(2)}</span>
      <span class="stat-pill">WTSD/W$SD: ${pct(profile.wtsd)} / ${pct(profile.w_sd)}</span>
      <span class="stat-pill">Style: ${escapeHtml(profile.style_label || "Unknown")}</span>
    </div>
  `;
}

function renderSingleProfileDashboard(profile) {
  if (!els.profileDashboard) return;
  const tendencies = (profile.tendencies || [])
    .slice(0, 8)
    .map((t) => `<li>${escapeHtml(t)}</li>`)
    .join("");
  const exploits = (profile.exploits || [])
    .slice(0, 6)
    .map(
      (e) =>
        `<li><strong>[${escapeHtml((e.category || "").toUpperCase())}]</strong> ${escapeHtml(e.description || "")} -> ${escapeHtml(e.counter_strategy || "")}</li>`,
    )
    .join("");

  const exploitBlock = featureEnabled("show_exploits")
    ? `<div style="margin-top:8px;"><strong>Exploit Plan</strong><ul class="leak-note-list">${exploits || "<li>No exploit notes.</li>"}</ul></div>`
    : `<div class="meta-strip">Free tier hides exploit plans. Upgrade to Pro to unlock them.</div>`;

  els.profileDashboard.innerHTML = `
    <div><strong>${escapeHtml(profile.name || "Profile")}</strong></div>
    ${profileStatsPills(profile)}
    <div style="margin-top:8px;"><strong>Tendencies</strong><ul class="leak-note-list">${tendencies || "<li>No tendency data.</li>"}</ul></div>
    ${exploitBlock}
  `;
}

function renderComparisonDashboard(profiles) {
  if (!els.comparisonDashboard) return;
  if (!profiles.length) {
    els.comparisonDashboard.textContent = "No comparison results yet.";
    return;
  }
  const showExploitPlan = featureEnabled("show_exploits");
  const cards = profiles
    .map((profile) => {
      const tendencies = (profile.tendencies || [])
        .slice(0, 8)
        .map((t) => `<li>${escapeHtml(t)}</li>`)
        .join("");
      const exploits = (profile.exploits || [])
        .slice(0, 6)
        .map(
          (e) =>
            `<li><strong>[${escapeHtml((e.category || "").toUpperCase())}]</strong> ${escapeHtml(
              e.description || "",
            )} -> ${escapeHtml(e.counter_strategy || "")}</li>`,
        )
        .join("");
      const exploitBlock = showExploitPlan
        ? `<div><strong>Exploit Plan</strong><ul class="leak-note-list">${exploits || "<li>No exploit notes.</li>"}</ul></div>`
        : `<div class="meta-strip">Free tier hides exploit plans. Upgrade to Pro to unlock them.</div>`;
      return `
        <div class="comparison-card">
          <div><strong>${escapeHtml(profile.group_label || profile.name || "Player")}</strong></div>
          ${profileStatsPills(profile)}
          <div class="meta-strip">Aliases: ${escapeHtml((profile.selected_usernames || []).join(", ") || "n/a")}</div>
          <div><strong>Tendencies</strong><ul class="leak-note-list">${tendencies || "<li>No tendency data.</li>"}</ul></div>
          ${exploitBlock}
        </div>
      `;
    })
    .join("");
  els.comparisonDashboard.innerHTML = `<div class="comparison-grid">${cards}</div>`;
}

async function analyzeSelectedProfile() {
  if (state.trainingWorkspace) {
    setStatus("Analyzer actions are in Analyzer tab. Use Start Match here for friend training.");
    return;
  }
  try {
    toggleCompareConfig(false);
    setOutputView("none");
    setStatus("Building profile dashboard...");
    const selected = getSelectedAnalyzerPlayers();
    if (!selected.length) {
      throw new Error("Select at least one friend username");
    }
    const primarySelection = selected[0];
    const profile = await apiGet(`/api/opponent_profile?name=${encodeURIComponent(primarySelection)}`);
    state.analyzedProfile = profile;
    renderSingleProfileDashboard(profile);
    setOutputView("profile");
    if (selected.length > 1) {
      setStatus("Profile analysis ready. Multiple selected; used the first selected player only.");
    } else {
      setStatus("Profile analysis ready.");
    }
  } catch (err) {
    setStatus(`Could not analyze profile: ${err.message}`, true);
  }
}

async function compareProfileGroups() {
  if (state.trainingWorkspace) {
    setStatus("Two-player compare is in Analyzer tab.");
    return;
  }
  if (!featureEnabled("allow_multi_profile_compare")) {
    setStatus("Upgrade to Pro to compare multiple profiles.", true);
    return;
  }
  try {
    toggleCompareConfig(true);
    setOutputView("none");
    const playerA = resolveComparePlayerInput(els.comparePlayerA?.value);
    const playerB = resolveComparePlayerInput(els.comparePlayerB?.value);
    if (!playerA || !playerB) {
      throw new Error("Select both Player A and Player B from the suggested list.");
    }
    if (playerA === playerB) {
      throw new Error("Player A and Player B must be different.");
    }
    const labelMap = state.compareLookup?.bySelectionKeyDisplay;
    const labelA = (labelMap && labelMap.get(playerA)) || String(els.comparePlayerA?.value || "").trim() || "Player A";
    const labelB = (labelMap && labelMap.get(playerB)) || String(els.comparePlayerB?.value || "").trim() || "Player B";
    const groups = [
      { label: labelA, usernames: [playerA] },
      { label: labelB, usernames: [playerB] },
    ];
    const maxGroups = maxCompareGroups();
    if (groups.length > maxGroups) {
      throw new Error(`Your plan supports comparing up to ${maxGroups} player slot(s).`);
    }
    setStatus("Comparing players...");
    const result = await apiPost("/api/opponent/compare", { groups });
    state.comparedProfiles = result.profiles || [];
    renderComparisonDashboard(state.comparedProfiles);
    setOutputView("compare");
    setStatus("Comparison ready.");
  } catch (err) {
    setStatus(`Could not compare players: ${err.message}`, true);
  }
}

function mapProfileToArchetype(profile) {
  const archetypes = state.config?.archetypes || [];
  if (!archetypes.length) {
    return { key: "tag_reg", label: "TAG Reg", score: 0 };
  }

  const vpip = Number(profile?.vpip || 0.3);
  const pfr = Number(profile?.pfr || 0.2);
  const af = Number(profile?.af || 2.2);
  const gap = Math.max(0, vpip - pfr);
  const style = String(profile?.style_label || "").toLowerCase();

  let best = null;
  for (const a of archetypes) {
    const aGap = Math.max(0, Number(a.vpip || 0) - Number(a.pfr || 0));
    let score =
      Math.pow((vpip - Number(a.vpip || 0)) / 0.18, 2) +
      Math.pow((pfr - Number(a.pfr || 0)) / 0.13, 2) +
      Math.pow((af - Number(a.af || 0)) / 2.2, 2) +
      Math.pow((gap - aGap) / 0.15, 2);

    if ((style.includes("calling") || style.includes("loose-passive")) && a.key === "calling_station") {
      score *= 0.68;
    }
    if (gap > 0.2 && a.key === "overcaller_preflop") {
      score *= 0.78;
    }
    if (af >= 3.8 && (a.key === "maniac" || a.key === "lag_reg")) {
      score *= 0.82;
    }
    if (vpip <= 0.2 && (a.key === "nit" || a.key === "weak_tight")) {
      score *= 0.84;
    }

    if (!best || score < best.score) {
      best = { key: a.key, label: a.label, score };
    }
  }
  return best || { key: "tag_reg", label: "TAG Reg", score: 0 };
}

function heroProfileFromTrainingStyle(styleKey) {
  const key = String(styleKey || "").trim();
  if (!key || key === "balanced_default") {
    return null;
  }
  const archetype = (state.config?.archetypes || []).find((row) => row.key === key);
  if (!archetype) {
    return null;
  }
  const pfr = Number(archetype.pfr || 0.22);
  const vpip = Number(archetype.vpip || 0.3);
  const af = Number(archetype.af || 2.8);
  const threeBet = Math.min(0.28, Math.max(0.02, pfr * 0.42));
  const foldToThreeBet = Math.min(0.82, Math.max(0.22, 0.58 - (pfr - 0.2) * 0.3));
  return {
    vpip,
    pfr,
    af,
    three_bet: Number(threeBet.toFixed(3)),
    fold_to_3bet: Number(foldToThreeBet.toFixed(3)),
  };
}

function buildDrillPayload(profile, mapped) {
  const stackBb = parseNumber("startingStackBb", 100);
  const target = buildTargetConfig(true) || {
    street: "flop",
    node_type: "single_raised_pot",
    action_context: "facing_bet",
    hero_position: "BTN",
  };

  const heroPos = normalizeHeadsUpPosition(target.hero_position);
  const villainPos = heroPos === "BTN" ? "BB" : "BTN";

  const payload = {
    num_players: 2,
    players_in_hand: 2,
    street: target.street || "flop",
    node_type: target.node_type || "single_raised_pot",
    action_context: target.action_context || "facing_bet",
    hero_position: heroPos,
    equal_stacks: true,
    default_stack_bb: stackBb,
    sb: 1,
    bb: 2,
    randomize_archetypes: false,
    seats: [
      {
        position: heroPos,
        stack_bb: stackBb,
        in_hand: true,
        archetype_key: "hero",
      },
      {
        position: villainPos,
        stack_bb: stackBb,
        in_hand: true,
        archetype_key: mapped.key,
      },
    ],
  };

  let trainingStyle = String(els.trainingStyle?.value || "balanced_default").trim();
  if (state.trainingWorkspace) {
    const draft = loadSetupDraft();
    const draftStyle = String(draft?.hero_training_style || "").trim();
    if (draftStyle) {
      trainingStyle = draftStyle;
    }
  }
  const heroProfile = heroProfileFromTrainingStyle(trainingStyle);
  if (heroProfile) {
    payload.hero_profile = heroProfile;
  }
  return payload;
}

async function startLiveMatch() {
  if (!state.trainingWorkspace) {
    setStatus("Friend training is available from Trainer tab only.", true);
    return;
  }
  if (!featureEnabled("allow_live_training")) {
    setStatus("Upgrade to Elite to start live matches.", true);
    return;
  }
  try {
    toggleCompareConfig(false);
    setOutputView("none");
    setStatus("Starting live match...");
    const selectedNames = getSelectedAnalyzerPlayers();
    if (selectedNames.length !== 1) {
      throw new Error("Select exactly one friend username before starting.");
    }
    const payload = {
      analyzer_players: selectedNames,
      starting_stack_bb: parseNumber("startingStackBb", 100),
      targeted_mode: !!els.targetedMode.checked,
      target_config: buildTargetConfig(false),
    };

    const result = await apiPost("/api/live/start", payload);
    localStorage.setItem(LIVE_SESSION_KEY, result.session_id);
    renderLiveState(result);
    setStatus(`Live match started: ${result.session_id}.`);
  } catch (err) {
    setStatus(`Could not start live match: ${err.message}`, true);
  }
}

async function nextHand() {
  if (!state.trainingWorkspace) {
    setStatus("Open Friend Training from Trainer tab to continue a match.", true);
    return;
  }
  if (!featureEnabled("allow_live_training")) {
    setStatus("Upgrade to Elite to use live hand progression.", true);
    return;
  }
  if (!state.session?.session_id) {
    setStatus("Start a match first.", true);
    return;
  }
  try {
    setStatus("Dealing next hand...");
    const result = await apiPost("/api/live/new_hand", { session_id: state.session.session_id });
    renderLiveState(result);
    setStatus(`Hand #${result.hand.hand_no} ready.`);
  } catch (err) {
    setStatus(`Could not deal next hand: ${err.message}`, true);
  }
}

function renderLiveState(data) {
  state.session = data;
  if (state.playMode === "full_match") {
    setOutputView("live");
  }
  const m = data.match || {};
  const h = data.hand || {};
  const opponent = m.opponent || {};

  els.liveMeta.textContent =
    `Session ${data.session_id} | Hands: ${m.hands_played || 0} | Hero Net: ${(m.hero_net_bb || 0).toFixed(3)}bb | ` +
    `Mode: ${titleCase(String(m.mode || "full_game").replaceAll("_", " "))}`;
  renderBalanceTracker(m, h);

  const boardCards = (h.board || []).map(cardNode).join("");
  const heroCards = (h.hero_hand || []).map(cardNode).join("");
  const villainCards = h.hand_over
    ? (h.villain_hand || []).map(cardNode).join("")
    : `<div class="card">?</div><div class="card">?</div>`;
  const history = (h.action_history || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");

  els.liveTable.classList.remove("empty");
  els.liveTable.innerHTML = `
    <div class="table-headline">
      <span>Street: ${escapeHtml(titleCase(h.street || "preflop"))}</span>
      <span>Hero Pos: ${escapeHtml(h.hero_position || "-")}</span>
      <span>Context: ${escapeHtml(titleCase(String(h.action_context || "").replaceAll("_", " ")))}</span>
    </div>
    <div class="table-headline">
      <span>Pot: ${Number(h.pot_bb || 0).toFixed(1)}bb</span>
      <span>To call: ${Number(h.to_call_bb || 0).toFixed(1)}bb</span>
      <span>Hand result: ${h.hand_over ? `${Number(h.hero_delta_bb || 0).toFixed(3)}bb` : "in progress"}</span>
    </div>
    <div><strong>Board:</strong> <div class="board-row">${boardCards || "<em>(preflop)</em>"}</div></div>
    <div><strong>Hero:</strong> <div class="board-row">${heroCards}</div></div>
    <div><strong>Villain:</strong> <div class="board-row">${villainCards}</div></div>
    <div><strong>Action history:</strong><ul>${history}</ul></div>
  `;

  renderLiveActions(h);
  if (state.playMode === "full_match") {
    renderLiveOpponentSummary(opponent, h);
  }
}

function renderBalanceTracker(match, hand) {
  if (!els.balanceTracker) return;
  const heroNet = Number(match.hero_net_bb || 0);
  const villainNet = Number(match.villain_net_bb !== undefined ? match.villain_net_bb : -heroNet);
  const heroStack = Number(
    match.hero_bankroll_bb !== undefined ? match.hero_bankroll_bb : Number(match.starting_stack_bb || 100) + heroNet,
  );
  const villainStack = Number(
    match.villain_bankroll_bb !== undefined
      ? match.villain_bankroll_bb
      : Number(match.starting_stack_bb || 100) + villainNet,
  );
  const handDelta = Number(hand?.hero_delta_bb || 0);
  const handLabel = hand?.hand_over ? `${handDelta >= 0 ? "+" : ""}${handDelta.toFixed(2)}bb` : "in progress";

  els.balanceTracker.innerHTML = `
    <div class="table-headline">
      <span><strong>Hero Stack:</strong> ${heroStack.toFixed(2)}bb</span>
      <span><strong>Villain Stack:</strong> ${villainStack.toFixed(2)}bb</span>
      <span><strong>Last Hand:</strong> ${handLabel}</span>
    </div>
    <div class="stat-pill-row">
      <span class="stat-pill ${heroNet >= 0 ? "good" : "bad"}">Hero Net: ${heroNet >= 0 ? "+" : ""}${heroNet.toFixed(3)}bb</span>
      <span class="stat-pill ${villainNet >= 0 ? "good" : "bad"}">Villain Net: ${villainNet >= 0 ? "+" : ""}${villainNet.toFixed(3)}bb</span>
    </div>
  `;
}

function renderLiveActions(hand) {
  if (!hand || hand.hand_over) {
    const showdown = hand?.showdown || {};
    const winner = showdown.winner ? `Winner: ${showdown.winner}` : "";
    els.liveActions.innerHTML = `
      <div class="prompt-box">Hand complete. ${escapeHtml(winner)}</div>
      <div class="action-row">
        <button id="inlineNextHandBtn" class="btn-primary">Next Hand</button>
      </div>
    `;
    const btn = document.getElementById("inlineNextHandBtn");
    if (btn) btn.addEventListener("click", nextHand);
    return;
  }

  const legal = hand.legal_actions || [];
  if (!legal.length) {
    els.liveActions.innerHTML = `<div class="prompt-box">No legal actions.</div>`;
    return;
  }

  if (!legal.includes(state.liveSelectedAction)) {
    state.liveSelectedAction = legal.includes("call") ? "call" : legal[0];
  }
  const requiresSize = state.liveSelectedAction === "bet" || state.liveSelectedAction === "raise";
  const sizeOptions = hand.size_options_bb || [];
  if (requiresSize && !sizeOptions.includes(state.liveSelectedSize)) {
    state.liveSelectedSize = sizeOptions[0] || null;
  }
  if (!requiresSize) state.liveSelectedSize = null;

  const actionButtons = legal
    .map(
      (a) =>
        `<button class="btn-action live-action-btn ${a === state.liveSelectedAction ? "active" : ""}" data-action="${a}">${titleCase(a)}</button>`,
    )
    .join("");

  const sizeButtons = sizeOptions
    .map(
      (s) =>
        `<button class="btn-action live-size-btn ${Number(s) === Number(state.liveSelectedSize) ? "active" : ""}" data-size="${s}">${Number(s).toFixed(1)}bb</button>`,
    )
    .join("");

  const sizeRowStyle = requiresSize ? "" : "display:none;";
  const intentRowStyle = requiresSize ? "" : "display:none;";

  els.liveActions.innerHTML = `
    <div><strong>Choose Action</strong></div>
    <div class="choice-row">${actionButtons}</div>
    <div style="${sizeRowStyle}">
      <div><strong>Size</strong></div>
      <div class="choice-row">${sizeButtons || "<em>No sizing options</em>"}</div>
    </div>
    <div style="${intentRowStyle}">
      <div><strong>Intent</strong></div>
      <div class="choice-row">
        <button class="btn-action live-intent-btn ${state.liveSelectedIntent === "value" ? "active" : ""}" data-intent="value">Value</button>
        <button class="btn-action live-intent-btn ${state.liveSelectedIntent === "bluff" ? "active" : ""}" data-intent="bluff">Bluff</button>
      </div>
    </div>
    <div class="action-row">
      <button id="submitLiveActionBtn" class="btn-primary">Submit Action</button>
    </div>
  `;

  els.liveActions.querySelectorAll(".live-action-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.liveSelectedAction = btn.dataset.action;
      renderLiveActions(hand);
    });
  });
  els.liveActions.querySelectorAll(".live-size-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.liveSelectedSize = Number(btn.dataset.size);
      renderLiveActions(hand);
    });
  });
  els.liveActions.querySelectorAll(".live-intent-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.liveSelectedIntent = btn.dataset.intent;
      renderLiveActions(hand);
    });
  });

  const submitBtn = document.getElementById("submitLiveActionBtn");
  if (submitBtn) submitBtn.addEventListener("click", submitLiveAction);
}

async function submitLiveAction() {
  if (!state.trainingWorkspace) {
    setStatus("Open Friend Training from Trainer tab to submit actions.", true);
    return;
  }
  if (!featureEnabled("allow_live_training")) {
    setStatus("Upgrade to Elite to submit live actions.", true);
    return;
  }
  if (!state.session?.session_id) {
    setStatus("No active session.", true);
    return;
  }
  const hand = state.session.hand || {};
  if (!state.liveSelectedAction) {
    setStatus("Select an action first.", true);
    return;
  }
  const payload = {
    session_id: state.session.session_id,
    action: state.liveSelectedAction,
  };
  if (state.liveSelectedAction === "bet" || state.liveSelectedAction === "raise") {
    if (!state.liveSelectedSize) {
      setStatus("Select a size first.", true);
      return;
    }
    payload.size_bb = Number(state.liveSelectedSize);
    payload.intent = state.liveSelectedIntent || "value";
  }
  try {
    setStatus(`Submitting ${state.liveSelectedAction}...`);
    const result = await apiPost("/api/live/action", payload);
    renderLiveState(result);
    if (result.hand?.hand_over) {
      setStatus(`Hand complete. Hero delta ${Number(result.hand.hero_delta_bb || 0).toFixed(3)}bb.`);
    } else {
      setStatus(`Action processed on ${result.hand?.street || "hand"}.`);
    }
  } catch (err) {
    setStatus(`Action failed: ${err.message}`, true);
    renderLiveActions(hand);
  }
}

async function startDrillHand() {
  if (!state.trainingWorkspace) {
    setStatus("Drill actions are only available in Friend Training workspace.", true);
    return;
  }
  if (!featureEnabled("allow_live_training")) {
    setStatus("Upgrade to Elite to generate drill hands.", true);
    return;
  }
  try {
    toggleCompareConfig(false);
    setOutputView("none");
    setStatus("Generating profile drill hand...");
    const selectedNames = getSelectedAnalyzerPlayers();
    if (selectedNames.length !== 1) {
      throw new Error("Select exactly one friend username before starting a drill.");
    }
    const opponentProfile = await resolveOpponentProfile();
    const mappedArchetype = mapProfileToArchetype(opponentProfile);
    const payload = buildDrillPayload(opponentProfile, mappedArchetype);

    const scenario = await apiPost("/api/generate", payload);
    state.drillScenario = scenario;
    state.drillOpponentProfile = opponentProfile;
    state.drillMappedArchetype = mappedArchetype;

    renderDrillScenario(scenario);
    renderDrillDecisionPanel(scenario);
    renderDrillOpponentSummary(opponentProfile, mappedArchetype, scenario);
    setStatus(`Drill hand ${scenario.scenario_id} ready.`);
  } catch (err) {
    setStatus(`Could not generate drill hand: ${err.message}`, true);
  }
}

function renderDrillScenario(s) {
  setOutputView("drill");
  const mapped = state.drillMappedArchetype;
  els.drillMeta.textContent =
    `ID ${s.scenario_id} | ${titleCase(s.street)} | ${titleCase(s.node_type.replaceAll("_", " "))} | ` +
    `2/2 in hand | Opponent model: ${mapped?.label || "N/A"}`;

  const boardCards = (s.board || []).map(cardNode).join("");
  const heroCards = (s.hero_hand || []).map(cardNode).join("");
  const seatPills = (s.seats || [])
    .map((seat) => {
      const classes = ["seat-pill"];
      if (seat.is_hero) classes.push("hero");
      const status = seat.in_hand ? seat.role : "folded";
      return `
        <div class="${classes.join(" ")}">
          <div class="line-a">${seat.position} ${seat.is_hero ? "(Hero)" : ""}</div>
          <div class="line-b">${seat.archetype_label} | ${seat.stack_bb}bb | ${status}</div>
        </div>
      `;
    })
    .join("");

  const history = (s.action_history || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");

  els.drillTable.classList.remove("empty");
  els.drillTable.innerHTML = `
    <div class="table-headline">
      <span>Pot: ${s.pot_bb}bb</span>
      <span>To call: ${s.to_call_bb}bb</span>
      <span>Eff stack: ${s.effective_stack_bb}bb</span>
    </div>
    <div><strong>Board:</strong> <div class="board-row">${boardCards || "<em>(preflop)</em>"}</div></div>
    <div><strong>Hero:</strong> <div class="board-row">${heroCards}</div></div>
    <div class="seat-pills">${seatPills}</div>
    <div><strong>Action history:</strong><ul>${history}</ul></div>
  `;

  els.drillPrompt.textContent = s.decision_prompt || "Choose one move and explain your exploit logic.";
  els.drillFeedbackSummary.textContent = "Choose one line and submit to score the decision.";
  els.drillEvTableWrap.innerHTML = "";
  els.drillLeakBreakdownWrap.innerHTML = "";
}

function renderDrillDecisionPanel(scenario) {
  const legal = scenario.legal_actions || [];
  const actionButtons = legal
    .map((a) => `<button class="btn-action drill-action-choice" data-action="${a}">${titleCase(a)}</button>`)
    .join("");

  let sizeOptions = scenario.bet_size_options_bb || [];
  if (legal.includes("raise")) {
    sizeOptions = scenario.raise_size_options_bb || [];
  }

  const sizeButtons = sizeOptions
    .map((size) => `<button class="btn-action drill-size-choice" data-size="${size}">${Number(size).toFixed(1)}bb</button>`)
    .join("");

  els.drillDecisionPanel.innerHTML = `
    <div>
      <div><strong>Choose Action</strong></div>
      <div class="choice-row">${actionButtons}</div>
    </div>
    <div id="drillSizeRowWrap" style="display:none;">
      <div><strong>Size</strong></div>
      <div class="choice-row" id="drillSizeChoiceRow">${sizeButtons}</div>
    </div>
    <div id="drillIntentRowWrap" style="display:none;">
      <div><strong>Intent</strong></div>
      <div class="choice-row">
        <button class="btn-action drill-intent-choice" data-intent="value">Value</button>
        <button class="btn-action drill-intent-choice" data-intent="bluff">Bluff</button>
      </div>
    </div>
    <div>
      <label>
        Free response
        <textarea id="drillFreeResponse" placeholder="Describe ranges, blockers, and exploit logic vs this profile."></textarea>
      </label>
    </div>
    <div class="action-row">
      <button id="submitDrillDecisionBtn" class="btn-primary">Submit Decision</button>
    </div>
  `;

  state.drillSelectedAction = legal.includes("call") ? "call" : legal[0];
  if (state.drillSelectedAction === "raise") {
    state.drillSelectedSize = Number((scenario.raise_size_options_bb || [])[0] || 0);
  } else if (state.drillSelectedAction === "bet") {
    state.drillSelectedSize = Number((scenario.bet_size_options_bb || [])[0] || 0);
  } else {
    state.drillSelectedSize = null;
  }
  state.drillSelectedIntent = "value";

  els.drillDecisionPanel.querySelectorAll(".drill-action-choice").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.drillSelectedAction = btn.dataset.action;
      if (state.drillSelectedAction === "raise") {
        state.drillSelectedSize = Number((scenario.raise_size_options_bb || [])[0] || 0);
      } else if (state.drillSelectedAction === "bet") {
        state.drillSelectedSize = Number((scenario.bet_size_options_bb || [])[0] || 0);
      } else {
        state.drillSelectedSize = null;
      }
      updateDrillDecisionButtonStates();
      toggleDrillSizeIntentRows();
    });
  });

  els.drillDecisionPanel.querySelectorAll(".drill-size-choice").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.drillSelectedSize = Number(btn.dataset.size);
      updateDrillDecisionButtonStates();
    });
  });

  els.drillDecisionPanel.querySelectorAll(".drill-intent-choice").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.drillSelectedIntent = btn.dataset.intent;
      updateDrillDecisionButtonStates();
    });
  });

  const submitBtn = els.drillDecisionPanel.querySelector("#submitDrillDecisionBtn");
  if (submitBtn) {
    submitBtn.addEventListener("click", submitDrillDecision);
  }

  updateDrillDecisionButtonStates();
  toggleDrillSizeIntentRows();
}

function toggleDrillSizeIntentRows() {
  const sizeWrap = els.drillDecisionPanel.querySelector("#drillSizeRowWrap");
  const intentWrap = els.drillDecisionPanel.querySelector("#drillIntentRowWrap");
  if (!sizeWrap || !intentWrap) return;
  const needsAggressiveFields = state.drillSelectedAction === "bet" || state.drillSelectedAction === "raise";
  sizeWrap.style.display = needsAggressiveFields ? "block" : "none";
  intentWrap.style.display = needsAggressiveFields ? "block" : "none";
}

function updateDrillDecisionButtonStates() {
  const actionButtons = els.drillDecisionPanel.querySelectorAll(".drill-action-choice");
  actionButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.action === state.drillSelectedAction);
  });

  const sizeButtons = els.drillDecisionPanel.querySelectorAll(".drill-size-choice");
  sizeButtons.forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.size) === Number(state.drillSelectedSize));
  });

  const intentButtons = els.drillDecisionPanel.querySelectorAll(".drill-intent-choice");
  intentButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.intent === state.drillSelectedIntent);
  });
}

async function submitDrillDecision() {
  if (!state.trainingWorkspace) {
    setStatus("Drill actions are only available in Friend Training workspace.", true);
    return;
  }
  if (!featureEnabled("allow_live_training")) {
    setStatus("Upgrade to Elite to submit drill decisions.", true);
    return;
  }
  if (!state.drillScenario) {
    setStatus("Generate a drill hand first.", true);
    return;
  }

  const action = state.drillSelectedAction;
  if (!action) {
    setStatus("Select an action first.", true);
    return;
  }

  const decision = { action };
  if (action === "bet" || action === "raise") {
    if (!state.drillSelectedSize) {
      setStatus("Select a size for bet/raise.", true);
      return;
    }
    decision.size_bb = Number(state.drillSelectedSize);
    decision.intent = state.drillSelectedIntent || "value";
  }

  const freeResponse = els.drillDecisionPanel.querySelector("#drillFreeResponse")?.value || "";

  try {
    setStatus("Scoring drill EV...");
    const result = await apiPost("/api/evaluate", {
      scenario_id: state.drillScenario.scenario_id,
      decision,
      free_response: freeResponse,
      simulations: 360,
    });
    state.drillScenario = result.scenario;
    renderDrillEvaluation(result.evaluation);
    setStatus(`Drill decision saved as attempt #${result.attempt_id}.`);
  } catch (err) {
    setStatus(`Drill evaluation failed: ${err.message}`, true);
  }
}

function actionSig(row) {
  const size = row.size_bb === null || row.size_bb === undefined ? "" : Number(row.size_bb).toFixed(1);
  return `${row.action}|${size}|${row.intent || ""}`;
}

function renderDrillEvaluation(evaluation) {
  const best = evaluation.best_action;
  const chosen = evaluation.chosen_action;
  const tags = evaluation.mistake_tags || [];

  els.drillFeedbackSummary.innerHTML = `
    <div><strong>Verdict:</strong> ${escapeHtml(evaluation.verdict)}</div>
    <div class="stat-pill-row">
      <span class="stat-pill ${evaluation.ev_loss_bb <= 0.2 ? "good" : "bad"}">EV Loss: ${evaluation.ev_loss_bb}bb</span>
      <span class="stat-pill">Chosen EV: ${chosen.ev_bb}bb</span>
      <span class="stat-pill">Best EV: ${best.ev_bb}bb</span>
      <span class="stat-pill">Best line: ${escapeHtml(best.label)}</span>
      ${tags.map((tag) => `<span class="stat-pill bad">${escapeHtml(tag)}</span>`).join("")}
    </div>
  `;

  const rows = evaluation.action_table
    .map((row) => {
      const sig = actionSig(row);
      const classes = [];
      if (sig === actionSig(best)) classes.push("best");
      if (sig === actionSig(chosen)) classes.push("chosen");
      return `
        <tr class="${classes.join(" ")}">
          <td>${escapeHtml(row.label)}</td>
          <td>${row.ev_bb}</td>
          <td>${row.equity}</td>
          <td>${row.fold_equity}</td>
          <td>${row.realization}</td>
          <td>${row.ev_ci_bb}</td>
        </tr>
      `;
    })
    .join("");

  els.drillEvTableWrap.innerHTML = `
    <table class="ev-table">
      <thead>
        <tr>
          <th>Action</th>
          <th>EV (bb)</th>
          <th>Equity</th>
          <th>Fold Equity</th>
          <th>Realization</th>
          <th>EV CI (+/- bb)</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  renderDrillLeakReport(evaluation.leak_report);
}

function renderDrillLeakReport(report) {
  if (!report) {
    els.drillLeakBreakdownWrap.innerHTML = "";
    return;
  }

  const factors = report.factor_breakdown || [];
  const factorRows = factors
    .map(
      (f) => `
      <tr>
        <td>${escapeHtml(f.factor)}</td>
        <td>${Number(f.impact_bb || 0).toFixed(3)}bb</td>
        <td>${Number(f.share_pct || 0).toFixed(1)}%</td>
        <td>${escapeHtml(f.detail || "")}</td>
      </tr>
    `,
    )
    .join("");

  const profile = report.hero_profile_analysis?.hero_profile || {};
  const guidance = report.hero_profile_analysis?.position_guidance || {};
  const notes = guidance.notes || [];
  const recs = report.hero_profile_analysis?.recommendations || [];
  const noteList = notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("");
  const recList = recs.map((n) => `<li>${escapeHtml(n)}</li>`).join("");

  els.drillLeakBreakdownWrap.innerHTML = `
    <div class="leak-block">
      <h3>Leak Breakdown</h3>
      <div>${escapeHtml(report.summary || "")}</div>
      <table class="leak-table">
        <thead>
          <tr>
            <th>Factor</th>
            <th>Impact</th>
            <th>Share</th>
            <th>Why It Lost EV</th>
          </tr>
        </thead>
        <tbody>${factorRows || "<tr><td colspan='4'>No significant leak factors.</td></tr>"}</tbody>
      </table>
      <div class="stat-pill-row">
        <span class="stat-pill">Hero Style: ${escapeHtml(profile.style_label || "N/A")}</span>
        <span class="stat-pill">VPIP: ${Number((profile.vpip || 0) * 100).toFixed(1)}%</span>
        <span class="stat-pill">PFR: ${Number((profile.pfr || 0) * 100).toFixed(1)}%</span>
        <span class="stat-pill">AF: ${Number(profile.af || 0).toFixed(2)}</span>
        <span class="stat-pill">VPIP-PFR Gap: ${Number((profile.vpip_pfr_gap || 0) * 100).toFixed(1)}%</span>
      </div>
      <div style="margin-top:8px;">
        <strong>Position Plan (${escapeHtml(guidance.position || "-")})</strong>
        <div>Target open range: ${formatRange(guidance.target_open_vpip_range)}</div>
        <ul class="leak-note-list">${noteList || "<li>No special note.</li>"}</ul>
      </div>
      <div style="margin-top:8px;">
        <strong>Profile Adjustments</strong>
        <ul class="leak-note-list">${recList || "<li>Profile is in a reasonable baseline zone.</li>"}</ul>
      </div>
    </div>
  `;
}

function renderLiveOpponentSummary(opponent, hand) {
  const range = hand?.villain_range_summary || {};
  const tendencies = (opponent.tendencies || [])
    .slice(0, 6)
    .map((t) => `<li>${escapeHtml(t)}</li>`)
    .join("");
  const exploits = (opponent.exploits || [])
    .slice(0, 4)
    .map(
      (e) =>
        `<li><strong>[${escapeHtml((e.category || "").toUpperCase())}]</strong> ${escapeHtml(e.description || "")} ` +
        `-> ${escapeHtml(e.counter_strategy || "")}</li>`,
    )
    .join("");

  const topHands = (range.top_weighted_hands || [])
    .slice(0, 12)
    .map((hKey) => `<span class="stat-pill">${escapeHtml(hKey)}</span>`)
    .join("");

  els.opponentSummary.innerHTML = `
    <div><strong>${escapeHtml(opponent.name || "Opponent")}</strong> | ${escapeHtml(opponent.style_label || "Unknown")}</div>
    <div class="stat-pill-row">
      <span class="stat-pill">Hands: ${opponent.hands_analyzed || 0}</span>
      <span class="stat-pill">VPIP/PFR: ${pct(opponent.vpip)} / ${pct(opponent.pfr)}</span>
      <span class="stat-pill">3B/Fold3B: ${pct(opponent.three_bet)} / ${pct(opponent.fold_to_3bet)}</span>
      <span class="stat-pill">AF: ${Number(opponent.af || 0).toFixed(2)}</span>
      <span class="stat-pill">WTSD/W$SD: ${pct(opponent.wtsd)} / ${pct(opponent.w_sd)}</span>
    </div>
    <div style="margin-top:8px;">
      <strong>Current Range Model (${escapeHtml(titleCase(String(range.street || hand?.street || "preflop")))})</strong>
      <div class="stat-pill-row">
        <span class="stat-pill">Adherence: ${pct(range.adherence || 0)}</span>
        <span class="stat-pill">Hero Image: ${pct(range.hero_image_score || 0)}</span>
        <span class="stat-pill">Range Width: ${pct(range.range_width_pct || 0)}</span>
        <span class="stat-pill">Value Density: ${pct(range.value_density_pct || 0)}</span>
        <span class="stat-pill">Bluff Density: ${pct(range.bluff_density_pct || 0)}</span>
      </div>
      <div class="stat-pill-row">${topHands || "<span class='stat-pill'>No range snapshot</span>"}</div>
    </div>
    <div style="margin-top:8px;">
      <strong>Key Tendencies</strong>
      <ul class="leak-note-list">${tendencies || "<li>No tendency data.</li>"}</ul>
    </div>
    <div style="margin-top:8px;">
      <strong>Exploit Plan</strong>
      <ul class="leak-note-list">${exploits || "<li>No exploit notes.</li>"}</ul>
    </div>
  `;
}

function renderDrillOpponentSummary(opponent, mapped, scenario) {
  const tendencies = (opponent?.tendencies || [])
    .slice(0, 6)
    .map((t) => `<li>${escapeHtml(t)}</li>`)
    .join("");
  const exploits = (opponent?.exploits || [])
    .slice(0, 4)
    .map(
      (e) =>
        `<li><strong>[${escapeHtml((e.category || "").toUpperCase())}]</strong> ${escapeHtml(e.description || "")} ` +
        `-> ${escapeHtml(e.counter_strategy || "")}</li>`,
    )
    .join("");

  const spot = scenario
    ? `${titleCase(scenario.street || "flop")}, ${titleCase(String(scenario.node_type || "single_raised_pot").replaceAll("_", " "))}, ${titleCase(String(scenario.action_context || "facing_bet").replaceAll("_", " "))}`
    : "Not generated";

  els.opponentSummary.innerHTML = `
    <div><strong>${escapeHtml(opponent?.name || "Opponent")}</strong> | ${escapeHtml(opponent?.style_label || "Unknown")}</div>
    <div class="stat-pill-row">
      <span class="stat-pill">Hands: ${opponent?.hands_analyzed || 0}</span>
      <span class="stat-pill">VPIP/PFR: ${pct(opponent?.vpip)} / ${pct(opponent?.pfr)}</span>
      <span class="stat-pill">3B/Fold3B: ${pct(opponent?.three_bet)} / ${pct(opponent?.fold_to_3bet)}</span>
      <span class="stat-pill">AF: ${Number(opponent?.af || 0).toFixed(2)}</span>
      <span class="stat-pill">WTSD/W$SD: ${pct(opponent?.wtsd)} / ${pct(opponent?.w_sd)}</span>
    </div>
    <div class="stat-pill-row">
      <span class="stat-pill">Drill Spot: ${escapeHtml(spot)}</span>
      <span class="stat-pill">EV Model Archetype: ${escapeHtml(mapped?.label || "TAG Reg")} (${escapeHtml(mapped?.key || "tag_reg")})</span>
    </div>
    <div style="margin-top:8px;">
      <strong>Key Tendencies</strong>
      <ul class="leak-note-list">${tendencies || "<li>No tendency data.</li>"}</ul>
    </div>
    <div style="margin-top:8px;">
      <strong>Exploit Plan</strong>
      <ul class="leak-note-list">${exploits || "<li>No exploit notes.</li>"}</ul>
    </div>
  `;
}

function pct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatRange(rangeValues) {
  if (!Array.isArray(rangeValues) || rangeValues.length !== 2) {
    return "N/A";
  }
  return `${(Number(rangeValues[0]) * 100).toFixed(1)}% - ${(Number(rangeValues[1]) * 100).toFixed(1)}%`;
}

function fillSelect(select, options) {
  if (!select) return;
  select.innerHTML = options.map((o) => `<option value="${o.value}">${escapeHtml(o.label)}</option>`).join("");
}

async function apiGet(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    throw new Error("Authentication required");
  }
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
  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    throw new Error("Authentication required");
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function apiUpload(url, formData) {
  const res = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    throw new Error("Authentication required");
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function cardNode(card) {
  const rank = card[0];
  const suit = card[1];
  const suitMap = { h: "♥", d: "♦", s: "♠", c: "♣" };
  const red = suit === "h" || suit === "d" ? "red" : "";
  return `<div class="card ${red}">${rank}${suitMap[suit] || suit}</div>`;
}

function titleCase(str) {
  return String(str)
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function setStatus(message, isError = false) {
  if (!els.statusLine) return;
  els.statusLine.textContent = message;
  els.statusLine.style.color = isError ? "#e6a1a1" : "#f0dca8";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
