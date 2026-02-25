const LIVE_SESSION_KEY = "trainer:liveSessionId";
const SETUP_STORAGE_KEY = "trainer:setupConfigV1";
const PLAY_MODE_KEY = "trainer:playModeV1";

const state = {
  config: null,
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

async function bootstrap() {
  mapIds([
    "playModeFull",
    "playModeDrill",
    "opponentSource",
    "presetKey",
    "analyzerPlayer",
    "startingStackBb",
    "liveSeed",
    "customName",
    "cVpip",
    "cPfr",
    "c3bet",
    "cF3b",
    "cLimp",
    "cAf",
    "cFlopCbet",
    "cTurnCbet",
    "cRiverCbet",
    "cWtsd",
    "cWsd",
    "cXr",
    "targetedMode",
    "targetedModeWrap",
    "useSetupDraft",
    "useSetupDraftWrap",
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
    "liveTable",
    "liveActions",
    "drillMeta",
    "drillTable",
    "drillPrompt",
    "drillDecisionPanel",
    "drillFeedbackSummary",
    "drillEvTableWrap",
    "drillLeakBreakdownWrap",
    "opponentSummary",
    "statusLine",
  ]);

  const config = await apiGet("/api/config");
  state.config = config;
  initControls(config);
  bindEvents();

  const savedMode = localStorage.getItem(PLAY_MODE_KEY);
  if (savedMode === "single_hand_drill") {
    setPlayMode("single_hand_drill");
  } else {
    setPlayMode("full_match");
  }

  const existing = localStorage.getItem(LIVE_SESSION_KEY);
  if (existing) {
    try {
      const restored = await apiGet(`/api/live/state?session_id=${encodeURIComponent(existing)}`);
      renderLiveState(restored);
      if (state.playMode === "full_match") {
        setStatus(`Restored live session ${existing}.`);
      }
    } catch {
      localStorage.removeItem(LIVE_SESSION_KEY);
    }
  }

  if (!state.session && state.playMode === "full_match") {
    setStatus("Ready. Start a full match to play against profile.");
  }
  if (!state.drillScenario && state.playMode === "single_hand_drill") {
    setStatus("Ready. Start a single-hand drill for full EV feedback.");
  }
}

function initControls(config) {
  const presets = config.live?.presets || [];
  fillSelect(
    els.presetKey,
    presets.map((p) => ({ value: p.key, label: `${p.name} (${p.style_label})` })),
  );

  const players = config.live?.analyzer_players || [];
  fillSelect(
    els.analyzerPlayer,
    players.map((name) => ({ value: name, label: name.toUpperCase() })),
  );

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

  const defaults = config.live?.defaults || {};
  els.opponentSource.value = defaults.opponent_source || "preset";
  els.presetKey.value = defaults.preset_key || "charlie";
  els.startingStackBb.value = Number(defaults.starting_stack_bb || 100);
  els.targetedMode.checked = !!defaults.targeted_mode;

  const t = defaults.target_config || {};
  if (t.street) els.tStreet.value = t.street;
  if (t.node_type) els.tNodeType.value = t.node_type;
  if (t.action_context) els.tActionContext.value = t.action_context;
  if (t.hero_position && (t.hero_position === "BTN" || t.hero_position === "BB")) {
    els.tHeroPosition.value = t.hero_position;
  }

  const charlie = presets.find((p) => p.key === "charlie") || presets[0];
  if (charlie) {
    populateCustomFromProfile(charlie);
  }

  updateOpponentSourceUi();
  updateTargetModeUi();
}

function bindEvents() {
  if (els.playModeFull) {
    els.playModeFull.addEventListener("change", () => {
      if (els.playModeFull.checked) setPlayMode("full_match");
    });
  }
  if (els.playModeDrill) {
    els.playModeDrill.addEventListener("change", () => {
      if (els.playModeDrill.checked) setPlayMode("single_hand_drill");
    });
  }

  els.opponentSource.addEventListener("change", updateOpponentSourceUi);
  els.targetedMode.addEventListener("change", updateTargetModeUi);

  els.startLiveBtn.addEventListener("click", startLiveMatch);
  els.nextHandBtn.addEventListener("click", nextHand);
  els.startDrillBtn.addEventListener("click", startDrillHand);
  els.newDrillBtn.addEventListener("click", startDrillHand);

  els.presetKey.addEventListener("change", () => {
    const presets = state.config.live?.presets || [];
    const selected = presets.find((p) => p.key === els.presetKey.value);
    if (selected && els.opponentSource.value === "preset") {
      populateCustomFromProfile(selected);
    }
  });
}

function setPlayMode(mode) {
  state.playMode = mode === "single_hand_drill" ? "single_hand_drill" : "full_match";
  if (els.playModeFull) els.playModeFull.checked = state.playMode === "full_match";
  if (els.playModeDrill) els.playModeDrill.checked = state.playMode === "single_hand_drill";
  localStorage.setItem(PLAY_MODE_KEY, state.playMode);
  updateModeUi();
}

function updateModeUi() {
  const full = state.playMode === "full_match";

  if (els.fullModeActions) els.fullModeActions.style.display = full ? "flex" : "none";
  if (els.drillModeActions) els.drillModeActions.style.display = full ? "none" : "flex";
  if (els.fullModePanel) els.fullModePanel.style.display = full ? "block" : "none";
  if (els.drillModePanel) els.drillModePanel.style.display = full ? "none" : "block";

  if (els.targetedModeWrap) els.targetedModeWrap.style.display = full ? "inline-flex" : "none";
  if (els.targetedMode) els.targetedMode.disabled = !full;

  updateTargetModeUi();

  if (full) {
    if (state.session) {
      renderLiveOpponentSummary(state.session.match?.opponent || {}, state.session.hand || {});
    } else {
      els.opponentSummary.textContent = "Opponent summary appears after match start.";
      setStatus("Full Match mode selected. Start a match to play a full heads-up hand flow.");
    }
  } else {
    if (state.drillOpponentProfile) {
      renderDrillOpponentSummary(state.drillOpponentProfile, state.drillMappedArchetype, state.drillScenario);
    } else {
      els.opponentSummary.textContent = "Opponent summary appears after drill hand generation.";
      setStatus("Single Hand Drill mode selected. Generate a hand for EV and leak feedback.");
    }
  }
}

function updateOpponentSourceUi() {
  const source = els.opponentSource.value;
  els.presetKey.disabled = source !== "preset";
  els.analyzerPlayer.disabled = source !== "analyzer";

  const customDisabled = source !== "custom";
  [
    "customName",
    "cVpip",
    "cPfr",
    "c3bet",
    "cF3b",
    "cLimp",
    "cAf",
    "cFlopCbet",
    "cTurnCbet",
    "cRiverCbet",
    "cWtsd",
    "cWsd",
    "cXr",
  ].forEach((id) => {
    if (els[id]) els[id].disabled = customDisabled;
  });
}

function updateTargetModeUi() {
  const full = state.playMode === "full_match";
  const enabled = full ? !!els.targetedMode.checked : true;
  if (els.targetConfigWrap) {
    els.targetConfigWrap.style.display = enabled ? "block" : "none";
  }
}

function parseNumber(id, fallback) {
  const value = Number(els[id]?.value);
  if (!Number.isFinite(value)) return fallback;
  return value;
}

function asRatePercent(value) {
  return Number(value) / 100;
}

function normalizeHeadsUpPosition(value) {
  return value === "BB" ? "BB" : "BTN";
}

function buildCustomProfile() {
  return {
    name: String(els.customName.value || "CUSTOM OPPONENT").trim() || "CUSTOM OPPONENT",
    source: "custom",
    style_label: "Custom",
    vpip: asRatePercent(parseNumber("cVpip", 30)),
    pfr: asRatePercent(parseNumber("cPfr", 20)),
    three_bet: asRatePercent(parseNumber("c3bet", 8)),
    fold_to_3bet: asRatePercent(parseNumber("cF3b", 45)),
    limp_rate: asRatePercent(parseNumber("cLimp", 12)),
    af: parseNumber("cAf", 2.2),
    flop_cbet: asRatePercent(parseNumber("cFlopCbet", 58)),
    turn_cbet: asRatePercent(parseNumber("cTurnCbet", 44)),
    river_cbet: asRatePercent(parseNumber("cRiverCbet", 32)),
    wtsd: asRatePercent(parseNumber("cWtsd", 30)),
    w_sd: asRatePercent(parseNumber("cWsd", 51)),
    check_raise: asRatePercent(parseNumber("cXr", 9)),
  };
}

function populateCustomFromProfile(profile) {
  if (!profile) return;
  els.customName.value = profile.name || "CUSTOM OPPONENT";
  els.cVpip.value = Number((profile.vpip || 0) * 100).toFixed(1);
  els.cPfr.value = Number((profile.pfr || 0) * 100).toFixed(1);
  els.c3bet.value = Number((profile.three_bet || 0) * 100).toFixed(1);
  els.cF3b.value = Number((profile.fold_to_3bet || 0) * 100).toFixed(1);
  els.cLimp.value = Number((profile.limp_rate || 0) * 100).toFixed(1);
  els.cAf.value = Number(profile.af || 2.2).toFixed(2);
  els.cFlopCbet.value = Number((profile.flop_cbet || 0) * 100).toFixed(1);
  els.cTurnCbet.value = Number((profile.turn_cbet || 0) * 100).toFixed(1);
  els.cRiverCbet.value = Number((profile.river_cbet || 0) * 100).toFixed(1);
  els.cWtsd.value = Number((profile.wtsd || 0) * 100).toFixed(1);
  els.cWsd.value = Number((profile.w_sd || 0) * 100).toFixed(1);
  els.cXr.value = Number((profile.check_raise || 0) * 100).toFixed(1);
}

function buildTargetConfig(force = false) {
  if (!force && !els.targetedMode.checked) return null;

  if (els.useSetupDraft.checked) {
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

function getPresetProfileByKey(key) {
  const presets = state.config?.live?.presets || [];
  return presets.find((p) => p.key === key) || presets.find((p) => p.key === "charlie") || presets[0] || null;
}

async function resolveOpponentProfile() {
  const source = els.opponentSource.value;
  if (source === "custom") {
    return buildCustomProfile();
  }
  if (source === "analyzer") {
    const name = String(els.analyzerPlayer.value || "").trim();
    if (!name) throw new Error("Select an analyzer player first");
    return apiGet(`/api/opponent_profile?name=${encodeURIComponent(name)}`);
  }
  const preset = getPresetProfileByKey(els.presetKey.value);
  if (!preset) throw new Error("No preset profiles available");
  return preset;
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
  const draft = loadSetupDraft();
  const defaultHero = state.config?.defaults?.hero_profile || {};

  const heroProfile = {
    vpip: Number(draft?.hero_profile?.vpip ?? Number(defaultHero.vpip || 0.3) * 100),
    pfr: Number(draft?.hero_profile?.pfr ?? Number(defaultHero.pfr || 0.22) * 100),
    af: Number(draft?.hero_profile?.af ?? Number(defaultHero.af || 2.8)),
    three_bet: Number(draft?.hero_profile?.three_bet ?? Number(defaultHero.three_bet || 0.09) * 100),
    fold_to_3bet: Number(
      draft?.hero_profile?.fold_to_3bet ?? Number(defaultHero.fold_to_3bet || 0.54) * 100,
    ),
  };

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
    randomize_hero_profile: !!draft?.randomize_hero_profile,
    randomize_archetypes: false,
    hero_profile: heroProfile,
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

  const seedText = String(els.liveSeed.value || "").trim();
  if (seedText) {
    payload.seed = Number(seedText);
  }
  return payload;
}

async function startLiveMatch() {
  try {
    setStatus("Starting live match...");
    const payload = {
      opponent_source: els.opponentSource.value,
      preset_key: els.presetKey.value,
      analyzer_player: els.analyzerPlayer.value,
      starting_stack_bb: parseNumber("startingStackBb", 100),
      targeted_mode: !!els.targetedMode.checked,
      target_config: buildTargetConfig(false),
    };
    if (els.opponentSource.value === "custom") {
      payload.opponent_profile = buildCustomProfile();
    }
    const seedText = String(els.liveSeed.value || "").trim();
    if (seedText) payload.seed = Number(seedText);

    const result = await apiPost("/api/live/start", payload);
    localStorage.setItem(LIVE_SESSION_KEY, result.session_id);
    renderLiveState(result);
    setStatus(`Live match started: ${result.session_id}.`);
  } catch (err) {
    setStatus(`Could not start live match: ${err.message}`, true);
  }
}

async function nextHand() {
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
  const m = data.match || {};
  const h = data.hand || {};
  const opponent = m.opponent || {};

  els.liveMeta.textContent =
    `Session ${data.session_id} | Hands: ${m.hands_played || 0} | Net: ${(m.hero_net_bb || 0).toFixed(3)}bb | ` +
    `Mode: ${titleCase(String(m.mode || "full_game").replaceAll("_", " "))}`;

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
  try {
    setStatus("Generating profile drill hand...");
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
  const mapped = state.drillMappedArchetype;
  const randFlags = s.randomization || {};
  els.drillMeta.textContent =
    `ID ${s.scenario_id} | ${titleCase(s.street)} | ${titleCase(s.node_type.replaceAll("_", " "))} | ` +
    `2/2 in hand | Opponent model: ${mapped?.label || "N/A"} | Hero random: ${!!randFlags.hero_profile}`;

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
  const heroStats = s.hero_profile || {};

  els.drillTable.classList.remove("empty");
  els.drillTable.innerHTML = `
    <div class="table-headline">
      <span>Pot: ${s.pot_bb}bb</span>
      <span>To call: ${s.to_call_bb}bb</span>
      <span>Eff stack: ${s.effective_stack_bb}bb</span>
    </div>
    <div class="table-headline">
      <span>Hero VPIP/PFR/AF: ${Number((heroStats.vpip || 0) * 100).toFixed(1)} / ${Number((heroStats.pfr || 0) * 100).toFixed(1)} / ${Number(heroStats.af || 0).toFixed(2)}</span>
      <span>Style: ${escapeHtml(heroStats.style_label || "N/A")}</span>
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
