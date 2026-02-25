const SETUP_STORAGE_KEY = "trainer:setupConfigV1";
const LAST_SCENARIO_KEY = "trainer:lastScenarioId";

const state = {
  page: null,
  config: null,
  scenario: null,
  selectedAction: null,
  selectedSize: null,
  selectedIntent: "value",
  seatDraft: {},
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  state.page = document.body.dataset.page || "setup";
  if (state.page === "setup") {
    bootstrapSetup().catch((err) => setStatus(`Setup init failed: ${err.message}`, true));
    return;
  }
  if (state.page === "trainer") {
    bootstrapTrainer().catch((err) => setStatus(`Trainer init failed: ${err.message}`, true));
    return;
  }
  if (state.page === "standings") {
    bootstrapStandings().catch((err) => setStatus(`Standings init failed: ${err.message}`, true));
  }
});

function mapIds(ids) {
  ids.forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function cloneObject(value) {
  return JSON.parse(JSON.stringify(value));
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

function saveSetupDraft(payload) {
  localStorage.setItem(SETUP_STORAGE_KEY, JSON.stringify(payload));
}

function defaultSetupDraftFromConfig(config) {
  return {
    num_players: config.defaults.num_players,
    street: config.defaults.street,
    node_type: config.defaults.node_type,
    action_context: config.defaults.action_context,
    hero_position: config.defaults.hero_position,
    players_in_hand: config.defaults.players_in_hand,
    equal_stacks: !!config.defaults.equal_stacks,
    default_stack_bb: Number(config.defaults.default_stack_bb),
    sb: Number(config.defaults.sb || 1),
    bb: Number(config.defaults.bb || 2),
    randomize_hero_profile: !!config.defaults.randomize_hero_profile,
    randomize_archetypes: !!config.defaults.randomize_archetypes,
    hero_profile: {
      vpip: Number((config.defaults.hero_profile?.vpip || 0.3) * 100),
      pfr: Number((config.defaults.hero_profile?.pfr || 0.22) * 100),
      af: Number(config.defaults.hero_profile?.af || 2.8),
      three_bet: Number((config.defaults.hero_profile?.three_bet || 0.09) * 100),
      fold_to_3bet: Number((config.defaults.hero_profile?.fold_to_3bet || 0.54) * 100),
    },
    seats: [],
  };
}

async function bootstrapSetup() {
  mapIds([
    "numPlayers",
    "street",
    "nodeType",
    "actionContext",
    "heroPosition",
    "playersInHand",
    "defaultStack",
    "seed",
    "equalStacks",
    "randomizeHeroProfile",
    "randomizeArchetypes",
    "heroVpip",
    "heroPfr",
    "heroAf",
    "hero3bet",
    "heroFold3bet",
    "seatConfigTable",
    "generateBtn",
    "statusLine",
  ]);

  const config = await apiGet("/api/config");
  state.config = config;
  initSetupControls(config);

  const stored = loadSetupDraft();
  if (stored) {
    applySetupDraftToControls(stored);
    setStatus("Restored previous setup draft.");
  } else {
    renderSeatConfigTable();
    saveSetupDraft(buildSetupPayloadFromInputs());
  }

  bindSetupEvents();
  syncHeroProfileInputState();

  const previousScenario = localStorage.getItem(LAST_SCENARIO_KEY);
  if (previousScenario) {
    setStatus(`Last scenario: ${previousScenario}. Setup is preserved.`);
  }
}

function initSetupControls(config) {
  fillSelect(els.numPlayers, [2, 3, 4, 5, 6, 7].map((n) => ({ value: n, label: `${n}` })));
  fillSelect(els.street, config.streets.map((v) => ({ value: v, label: titleCase(v) })));
  fillSelect(
    els.nodeType,
    config.node_types.map((v) => ({ value: v, label: titleCase(v.replaceAll("_", " ")) })),
  );
  fillSelect(
    els.actionContext,
    config.action_contexts.map((v) => ({
      value: v,
      label: titleCase(v.replaceAll("_", " ")),
    })),
  );

  els.numPlayers.value = String(config.defaults.num_players);
  els.street.value = config.defaults.street;
  els.nodeType.value = config.defaults.node_type;
  els.actionContext.value = config.defaults.action_context;
  els.playersInHand.value = String(config.defaults.players_in_hand);
  els.defaultStack.value = String(config.defaults.default_stack_bb);
  els.equalStacks.checked = !!config.defaults.equal_stacks;
  els.randomizeHeroProfile.checked = !!config.defaults.randomize_hero_profile;
  els.randomizeArchetypes.checked = !!config.defaults.randomize_archetypes;

  els.heroVpip.value = Number((config.defaults.hero_profile?.vpip || 0.3) * 100).toFixed(1);
  els.heroPfr.value = Number((config.defaults.hero_profile?.pfr || 0.22) * 100).toFixed(1);
  els.heroAf.value = Number(config.defaults.hero_profile?.af || 2.8).toFixed(1);
  els.hero3bet.value = Number((config.defaults.hero_profile?.three_bet || 0.09) * 100).toFixed(1);
  els.heroFold3bet.value = Number((config.defaults.hero_profile?.fold_to_3bet || 0.54) * 100).toFixed(1);

  refreshHeroPositionOptions();
}

function applySetupDraftToControls(draft) {
  const defaults = defaultSetupDraftFromConfig(state.config);
  const merged = { ...defaults, ...draft };
  const positionsForDraft = state.config.position_sets[Number(merged.num_players)] || [];

  els.numPlayers.value = String(merged.num_players);
  refreshHeroPositionOptions();
  if (positionsForDraft.includes(merged.hero_position)) {
    els.heroPosition.value = merged.hero_position;
  }

  els.street.value = merged.street || defaults.street;
  els.nodeType.value = merged.node_type || defaults.node_type;
  els.actionContext.value = merged.action_context || defaults.action_context;
  els.playersInHand.value = String(merged.players_in_hand || defaults.players_in_hand);
  els.defaultStack.value = String(merged.default_stack_bb || defaults.default_stack_bb);
  els.equalStacks.checked = !!merged.equal_stacks;
  els.randomizeHeroProfile.checked = !!merged.randomize_hero_profile;
  els.randomizeArchetypes.checked = !!merged.randomize_archetypes;
  els.seed.value = merged.seed ? String(merged.seed) : "";

  els.heroVpip.value = Number(merged.hero_profile?.vpip ?? defaults.hero_profile.vpip).toFixed(1);
  els.heroPfr.value = Number(merged.hero_profile?.pfr ?? defaults.hero_profile.pfr).toFixed(1);
  els.heroAf.value = Number(merged.hero_profile?.af ?? defaults.hero_profile.af).toFixed(1);
  els.hero3bet.value = Number(merged.hero_profile?.three_bet ?? defaults.hero_profile.three_bet).toFixed(1);
  els.heroFold3bet.value = Number(merged.hero_profile?.fold_to_3bet ?? defaults.hero_profile.fold_to_3bet).toFixed(1);

  state.seatDraft = {};
  for (const seat of merged.seats || []) {
    if (!seat || !seat.position) continue;
    state.seatDraft[seat.position] = {
      archetype_key: seat.archetype_key || "tag_reg",
      stack_bb: Number(seat.stack_bb || merged.default_stack_bb || defaults.default_stack_bb),
      in_hand: seat.in_hand !== false,
    };
  }
  renderSeatConfigTable();
}

function bindSetupEvents() {
  els.numPlayers.addEventListener("change", () => {
    refreshHeroPositionOptions();
    renderSeatConfigTable();
    persistSetupDraftFromInputs();
  });
  els.heroPosition.addEventListener("change", () => {
    renderSeatConfigTable();
    persistSetupDraftFromInputs();
  });
  els.equalStacks.addEventListener("change", () => {
    renderSeatConfigTable();
    persistSetupDraftFromInputs();
  });
  els.defaultStack.addEventListener("change", () => {
    renderSeatConfigTable();
    persistSetupDraftFromInputs();
  });
  els.randomizeArchetypes.addEventListener("change", () => {
    renderSeatConfigTable();
    persistSetupDraftFromInputs();
  });
  els.randomizeHeroProfile.addEventListener("change", () => {
    syncHeroProfileInputState();
    persistSetupDraftFromInputs();
  });

  [
    els.street,
    els.nodeType,
    els.actionContext,
    els.playersInHand,
    els.seed,
    els.heroVpip,
    els.heroPfr,
    els.heroAf,
    els.hero3bet,
    els.heroFold3bet,
  ].forEach((input) => {
    if (!input) return;
    input.addEventListener("change", persistSetupDraftFromInputs);
    input.addEventListener("input", persistSetupDraftFromInputs);
  });

  if (els.seatConfigTable) {
    els.seatConfigTable.addEventListener("change", () => {
      captureSeatDraft();
      persistSetupDraftFromInputs();
    });
    els.seatConfigTable.addEventListener("input", () => {
      captureSeatDraft();
      persistSetupDraftFromInputs();
    });
  }

  els.generateBtn.addEventListener("click", generateScenarioFromSetup);
}

function positionsForCurrentTable() {
  const n = Number(els.numPlayers.value);
  return state.config.position_sets[n] || [];
}

function refreshHeroPositionOptions() {
  const positions = positionsForCurrentTable();
  const previous = els.heroPosition.value;
  fillSelect(els.heroPosition, positions.map((p) => ({ value: p, label: p })));
  if (positions.includes(previous)) {
    els.heroPosition.value = previous;
  } else if (positions.includes("BTN")) {
    els.heroPosition.value = "BTN";
  } else {
    els.heroPosition.value = positions[0];
  }
  const maxInHand = Math.max(2, positions.length);
  els.playersInHand.max = String(maxInHand);
  if (Number(els.playersInHand.value) > maxInHand) {
    els.playersInHand.value = String(maxInHand);
  }
}

function archetypeOptionsHtml(selected) {
  return state.config.archetypes
    .map((a) => `<option value="${a.key}" ${a.key === selected ? "selected" : ""}>${a.label}</option>`)
    .join("");
}

function syncHeroProfileInputState() {
  const disabled = !!els.randomizeHeroProfile.checked;
  ["heroVpip", "heroPfr", "heroAf", "hero3bet", "heroFold3bet"].forEach((id) => {
    if (els[id]) els[id].disabled = disabled;
  });
}

function captureSeatDraft() {
  if (!els.seatConfigTable) return;
  const rows = els.seatConfigTable.querySelectorAll("tr[data-position]");
  rows.forEach((row) => {
    const pos = row.dataset.position;
    const archetype = row.querySelector(".archetype-select")?.value || state.seatDraft[pos]?.archetype_key || "tag_reg";
    const stack = Number(row.querySelector(".stack-input")?.value || 100);
    const inHand = !!row.querySelector(".inhand-input")?.checked;
    state.seatDraft[pos] = { archetype_key: archetype, stack_bb: stack, in_hand: inHand };
  });
}

function renderSeatConfigTable() {
  captureSeatDraft();
  const positions = positionsForCurrentTable();
  const heroPosition = els.heroPosition.value;
  const equalStacks = !!els.equalStacks.checked;
  const randomizeArchetypes = !!els.randomizeArchetypes.checked;
  const defaultStack = Number(els.defaultStack.value || 100);

  const rows = positions
    .map((pos, idx) => {
      const draft = state.seatDraft[pos] || {};
      const isHero = pos === heroPosition;
      const archetype = draft.archetype_key || "tag_reg";
      const stack = Number(draft.stack_bb || defaultStack);
      const inHand = draft.in_hand !== undefined ? draft.in_hand : true;

      if (isHero) {
        return `
          <tr data-position="${pos}">
            <td>${idx + 1}</td>
            <td class="hero-cell">${pos}</td>
            <td>Hero</td>
            <td><input class="stack-input" type="number" min="10" max="500" step="1" value="${defaultStack}" ${equalStacks ? "disabled" : ""}></td>
            <td><input class="inhand-input" type="checkbox" checked disabled></td>
            <td>hero_to_act</td>
          </tr>
        `;
      }
      return `
        <tr data-position="${pos}">
          <td>${idx + 1}</td>
          <td>${pos}</td>
          <td>
            <select class="archetype-select" ${randomizeArchetypes ? "disabled" : ""}>
              ${archetypeOptionsHtml(archetype)}
            </select>
          </td>
          <td><input class="stack-input" type="number" min="10" max="500" step="1" value="${equalStacks ? defaultStack : stack}" ${equalStacks ? "disabled" : ""}></td>
          <td><input class="inhand-input" type="checkbox" ${inHand ? "checked" : ""}></td>
          <td>${randomizeArchetypes ? "randomized" : "custom"}</td>
        </tr>
      `;
    })
    .join("");

  els.seatConfigTable.innerHTML = `
    <table class="seat-table">
      <thead>
        <tr>
          <th>Seat</th>
          <th>Position</th>
          <th>Archetype</th>
          <th>Stack (bb)</th>
          <th>In Hand</th>
          <th>Mode</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function collectSeatPayload() {
  const rows = els.seatConfigTable.querySelectorAll("tr[data-position]");
  const seats = [];
  rows.forEach((row) => {
    const position = row.dataset.position;
    const isHero = row.querySelector(".hero-cell") !== null;
    const stackInput = row.querySelector(".stack-input");
    const inHandInput = row.querySelector(".inhand-input");
    const archetypeSelect = row.querySelector(".archetype-select");

    seats.push({
      position,
      stack_bb: Number(stackInput?.value || 100),
      in_hand: isHero ? true : !!inHandInput?.checked,
      archetype_key: isHero ? "hero" : archetypeSelect?.value || state.seatDraft[position]?.archetype_key || "tag_reg",
    });
  });
  return seats;
}

function buildSetupPayloadFromInputs() {
  captureSeatDraft();
  const payload = {
    num_players: Number(els.numPlayers.value),
    street: els.street.value,
    node_type: els.nodeType.value,
    action_context: els.actionContext.value,
    hero_position: els.heroPosition.value,
    players_in_hand: Number(els.playersInHand.value),
    equal_stacks: !!els.equalStacks.checked,
    default_stack_bb: Number(els.defaultStack.value),
    sb: 1,
    bb: 2,
    randomize_hero_profile: !!els.randomizeHeroProfile.checked,
    randomize_archetypes: !!els.randomizeArchetypes.checked,
    hero_profile: {
      vpip: Number(els.heroVpip.value || 30),
      pfr: Number(els.heroPfr.value || 22),
      af: Number(els.heroAf.value || 2.8),
      three_bet: Number(els.hero3bet.value || 9),
      fold_to_3bet: Number(els.heroFold3bet.value || 54),
    },
    seats: collectSeatPayload(),
  };
  const seedText = String(els.seed.value || "").trim();
  if (seedText) {
    payload.seed = Number(seedText);
  }
  return payload;
}

function persistSetupDraftFromInputs() {
  if (state.page !== "setup") return;
  const payload = buildSetupPayloadFromInputs();
  saveSetupDraft(payload);
}

async function generateScenarioFromPayload(payload, options = {}) {
  const scenario = await apiPost("/api/generate", payload);
  localStorage.setItem(LAST_SCENARIO_KEY, scenario.scenario_id);
  if (options.navigateToTrainer) {
    window.location.href = `/trainer.html?scenario_id=${encodeURIComponent(scenario.scenario_id)}`;
    return scenario;
  }

  state.scenario = scenario;
  renderScenario(scenario);
  renderDecisionPanel(scenario);
  if (els.feedbackSummary) {
    els.feedbackSummary.textContent = "Choose one line and submit to score the decision.";
  }
  if (els.evTableWrap) els.evTableWrap.innerHTML = "";
  if (els.leakBreakdownWrap) els.leakBreakdownWrap.innerHTML = "";
  return scenario;
}

async function generateScenarioFromSetup() {
  try {
    setStatus("Generating scenario...");
    const payload = buildSetupPayloadFromInputs();
    saveSetupDraft(payload);
    const scenario = await generateScenarioFromPayload(payload, { navigateToTrainer: true });
    if (scenario) {
      setStatus(`Scenario ${scenario.scenario_id} ready. Opening trainer page...`);
    }
  } catch (err) {
    setStatus(`Generate failed: ${err.message}`, true);
  }
}

async function bootstrapTrainer() {
  mapIds([
    "scenarioMeta",
    "tableView",
    "decisionPrompt",
    "decisionPanel",
    "feedbackSummary",
    "leakBreakdownWrap",
    "evTableWrap",
    "regenerateBtn",
    "statusLine",
  ]);

  if (els.regenerateBtn) {
    els.regenerateBtn.addEventListener("click", regenerateSameSetupScenario);
  }

  const scenarioId = getScenarioIdFromLocation();
  if (!scenarioId) {
    els.scenarioMeta.textContent = "No scenario selected. Click New Setup to generate from your saved setup.";
    setStatus("No scenario loaded. Using saved setup draft for next generation.");
    return;
  }

  setStatus(`Loading scenario ${scenarioId}...`);
  const scenario = await apiGet(`/api/scenario?scenario_id=${encodeURIComponent(scenarioId)}`);
  state.scenario = scenario;
  localStorage.setItem(LAST_SCENARIO_KEY, scenario.scenario_id);

  renderScenario(scenario);
  renderDecisionPanel(scenario);
  els.feedbackSummary.textContent = "Choose one line and submit to score the decision.";
  els.evTableWrap.innerHTML = "";
  els.leakBreakdownWrap.innerHTML = "";
  setStatus(`Scenario ${scenario.scenario_id} loaded.`);
}

async function regenerateSameSetupScenario() {
  try {
    setStatus("Generating new example from saved setup...");
    const draft = loadSetupDraft();
    if (!draft) {
      setStatus("No saved setup found. Configure setup first.", true);
      return;
    }
    const payload = cloneObject(draft);
    delete payload.seed; // Ensure a new example while keeping same setup configuration.
    const scenario = await generateScenarioFromPayload(payload, { navigateToTrainer: false });
    setStatus(`Loaded new scenario ${scenario.scenario_id} from saved setup.`);
  } catch (err) {
    setStatus(`Could not generate new setup scenario: ${err.message}`, true);
  }
}

function getScenarioIdFromLocation() {
  const url = new URL(window.location.href);
  const queryId = url.searchParams.get("scenario_id");
  if (queryId) return queryId;
  return localStorage.getItem(LAST_SCENARIO_KEY);
}

function renderScenario(s) {
  const randFlags = s.randomization || {};
  els.scenarioMeta.textContent =
    `ID ${s.scenario_id} | ${titleCase(s.street)} | ${titleCase(s.node_type.replaceAll("_", " "))} | ` +
    `${s.players_in_hand}/${s.num_players} in hand | Hero random: ${!!randFlags.hero_profile} | Opponents random: ${!!randFlags.archetypes}`;

  const boardCards = s.board.map(cardNode).join("");
  const heroCards = s.hero_hand.map(cardNode).join("");
  const seatPills = s.seats
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

  const history = s.action_history.map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  const heroStats = s.hero_profile || {};
  els.tableView.classList.remove("empty");
  els.tableView.innerHTML = `
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

  els.decisionPrompt.textContent = s.decision_prompt;
}

function renderDecisionPanel(scenario) {
  const legal = scenario.legal_actions || [];
  const actionButtons = legal
    .map((a) => `<button class="btn-action action-choice" data-action="${a}">${titleCase(a)}</button>`)
    .join("");

  let sizeOptions = scenario.bet_size_options_bb || [];
  if (legal.includes("raise")) {
    sizeOptions = scenario.raise_size_options_bb || [];
  }

  const sizeButtons = sizeOptions
    .map((size) => `<button class="btn-action size-choice" data-size="${size}">${Number(size).toFixed(1)}bb</button>`)
    .join("");

  els.decisionPanel.innerHTML = `
    <div>
      <div><strong>Choose Action</strong></div>
      <div class="choice-row">${actionButtons}</div>
    </div>
    <div id="sizeRowWrap" style="display:none;">
      <div><strong>Size</strong></div>
      <div class="choice-row" id="sizeChoiceRow">${sizeButtons}</div>
    </div>
    <div id="intentRowWrap" style="display:none;">
      <div><strong>Intent</strong></div>
      <div class="choice-row">
        <button class="btn-action intent-choice" data-intent="value">Value</button>
        <button class="btn-action intent-choice" data-intent="bluff">Bluff</button>
      </div>
    </div>
    <div>
      <label>
        Free response
        <textarea id="freeResponse" placeholder="Describe ranges, blockers, and why your line exploits these opponents."></textarea>
      </label>
    </div>
    <div class="action-row">
      <button id="submitDecisionBtn" class="btn-primary">Submit Decision</button>
    </div>
  `;

  const actionChoiceButtons = els.decisionPanel.querySelectorAll(".action-choice");
  const sizeChoiceButtons = els.decisionPanel.querySelectorAll(".size-choice");
  const intentChoiceButtons = els.decisionPanel.querySelectorAll(".intent-choice");

  state.selectedAction = legal.includes("call") ? "call" : legal[0];
  if (state.selectedAction === "raise") {
    state.selectedSize = Number((scenario.raise_size_options_bb || [])[0] || 0);
  } else if (state.selectedAction === "bet") {
    state.selectedSize = Number((scenario.bet_size_options_bb || [])[0] || 0);
  } else {
    state.selectedSize = null;
  }
  state.selectedIntent = "value";

  actionChoiceButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedAction = btn.dataset.action;
      if (state.selectedAction === "raise") {
        state.selectedSize = Number((scenario.raise_size_options_bb || [])[0] || 0);
      } else if (state.selectedAction === "bet") {
        state.selectedSize = Number((scenario.bet_size_options_bb || [])[0] || 0);
      } else {
        state.selectedSize = null;
      }
      updateDecisionButtonStates();
      toggleSizeIntentRows();
    });
  });

  sizeChoiceButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedSize = Number(btn.dataset.size);
      updateDecisionButtonStates();
    });
  });

  intentChoiceButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedIntent = btn.dataset.intent;
      updateDecisionButtonStates();
    });
  });

  els.decisionPanel.querySelector("#submitDecisionBtn").addEventListener("click", submitDecision);
  updateDecisionButtonStates();
  toggleSizeIntentRows();
}

function toggleSizeIntentRows() {
  const sizeWrap = els.decisionPanel.querySelector("#sizeRowWrap");
  const intentWrap = els.decisionPanel.querySelector("#intentRowWrap");
  if (!sizeWrap || !intentWrap) return;
  const needsAggressiveFields = state.selectedAction === "bet" || state.selectedAction === "raise";
  sizeWrap.style.display = needsAggressiveFields ? "block" : "none";
  intentWrap.style.display = needsAggressiveFields ? "block" : "none";
}

function updateDecisionButtonStates() {
  const actionButtons = els.decisionPanel.querySelectorAll(".action-choice");
  actionButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.action === state.selectedAction);
  });
  const sizeButtons = els.decisionPanel.querySelectorAll(".size-choice");
  sizeButtons.forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.size) === Number(state.selectedSize));
  });
  const intentButtons = els.decisionPanel.querySelectorAll(".intent-choice");
  intentButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.intent === state.selectedIntent);
  });
}

async function submitDecision() {
  if (!state.scenario) return;
  const action = state.selectedAction;
  if (!action) {
    setStatus("Select an action first.", true);
    return;
  }
  const decision = { action };
  if (action === "bet" || action === "raise") {
    if (!state.selectedSize) {
      setStatus("Select a size for bet/raise.", true);
      return;
    }
    decision.size_bb = Number(state.selectedSize);
    decision.intent = state.selectedIntent || "value";
  }

  const freeResponse = els.decisionPanel.querySelector("#freeResponse")?.value || "";
  try {
    setStatus("Scoring EV...");
    const result = await apiPost("/api/evaluate", {
      scenario_id: state.scenario.scenario_id,
      decision,
      free_response: freeResponse,
      simulations: 360,
    });
    renderEvaluation(result.evaluation);
    setStatus(`Decision saved as attempt #${result.attempt_id}.`);
  } catch (err) {
    setStatus(`Evaluation failed: ${err.message}`, true);
  }
}

function actionSig(row) {
  const size = row.size_bb === null || row.size_bb === undefined ? "" : Number(row.size_bb).toFixed(1);
  return `${row.action}|${size}|${row.intent || ""}`;
}

function renderEvaluation(evaluation) {
  const best = evaluation.best_action;
  const chosen = evaluation.chosen_action;
  const tags = evaluation.mistake_tags || [];

  els.feedbackSummary.innerHTML = `
    <div><strong>Verdict:</strong> ${escapeHtml(evaluation.verdict)}</div>
    <div class="stat-pill-row">
      <span class="stat-pill ${evaluation.ev_loss_bb <= 0.2 ? "good" : "bad"}">EV Loss: ${evaluation.ev_loss_bb}bb</span>
      <span class="stat-pill">Chosen EV: ${chosen.ev_bb}bb</span>
      <span class="stat-pill">Best EV: ${best.ev_bb}bb</span>
      <span class="stat-pill">Best line: ${escapeHtml(best.label)}</span>
      ${tags.map((tag) => `<span class="stat-pill bad">${escapeHtml(tag)}</span>`).join("")}
    </div>
  `;
  renderLeakReport(evaluation.leak_report);

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

  els.evTableWrap.innerHTML = `
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
}

function renderLeakReport(report) {
  if (!report) {
    els.leakBreakdownWrap.innerHTML = "";
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

  els.leakBreakdownWrap.innerHTML = `
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

async function bootstrapStandings() {
  mapIds(["progressWrap", "refreshProgressBtn", "clearSavedBtn", "statusLine"]);
  if (els.refreshProgressBtn) {
    els.refreshProgressBtn.addEventListener("click", refreshProgress);
  }
  if (els.clearSavedBtn) {
    els.clearSavedBtn.addEventListener("click", clearSavedHands);
  }
  await refreshProgress();
}

async function clearSavedHands() {
  const ok = window.confirm("Clear all saved hands, scenarios, and standings attempts?");
  if (!ok) return;
  try {
    setStatus("Clearing saved hands...");
    const result = await apiPost("/api/clear_saved_hands", {});
    localStorage.removeItem(LAST_SCENARIO_KEY);
    await refreshProgress();
    setStatus(
      `Cleared ${result.scenarios_deleted || 0} scenarios and ${result.attempts_deleted || 0} attempts.`,
    );
  } catch (err) {
    setStatus(`Clear failed: ${err.message}`, true);
  }
}

async function refreshProgress() {
  if (!els.progressWrap) return;
  try {
    setStatus("Loading standings...");
    const p = await apiGet("/api/progress");
    const totals = p.totals || {};
    const header = `
      <div class="stat-pill-row">
        <span class="stat-pill">Attempts: ${totals.attempts || 0}</span>
        <span class="stat-pill">Avg EV Loss: ${totals.avg_ev_loss_bb || 0}bb</span>
        <span class="stat-pill">Accuracy (<=0.2bb): ${formatPct(totals.accuracy || 0)}</span>
        <span class="stat-pill">Avg Chosen EV: ${totals.avg_chosen_ev_bb || 0}bb</span>
      </div>
    `;

    const posRows = (p.by_position || [])
      .map((r) => `<tr><td>${escapeHtml(r.label)}</td><td>${r.attempts}</td><td>${r.avg_ev_loss_bb}</td><td>${formatPct(r.accuracy)}</td></tr>`)
      .join("");
    const streetRows = (p.by_street || [])
      .map((r) => `<tr><td>${escapeHtml(r.label)}</td><td>${r.attempts}</td><td>${r.avg_ev_loss_bb}</td><td>${formatPct(r.accuracy)}</td></tr>`)
      .join("");

    const recentRows = (p.recent_attempts || [])
      .slice(0, 20)
      .map((r) => {
        const size = r.chosen_size_bb !== null && r.chosen_size_bb !== undefined ? ` ${r.chosen_size_bb}bb` : "";
        const intent = r.chosen_intent ? ` (${r.chosen_intent})` : "";
        return `<tr><td>#${r.attempt_id}</td><td>${escapeHtml(r.hero_position)}</td><td>${escapeHtml(r.street)}</td><td>${escapeHtml(r.chosen_action)}${size}${intent}</td><td>${r.ev_loss_bb}</td><td>${escapeHtml(r.verdict)}</td></tr>`;
      })
      .join("");

    els.progressWrap.innerHTML = `
      ${header}
      <h3>By Position</h3>
      <table class="mini-table">
        <thead><tr><th>Position</th><th>Attempts</th><th>Avg EV Loss</th><th>Accuracy</th></tr></thead>
        <tbody>${posRows || "<tr><td colspan='4'>No data</td></tr>"}</tbody>
      </table>
      <h3>By Street</h3>
      <table class="mini-table">
        <thead><tr><th>Street</th><th>Attempts</th><th>Avg EV Loss</th><th>Accuracy</th></tr></thead>
        <tbody>${streetRows || "<tr><td colspan='4'>No data</td></tr>"}</tbody>
      </table>
      <h3>Recent Attempts</h3>
      <table class="mini-table">
        <thead><tr><th>ID</th><th>Pos</th><th>Street</th><th>Chosen</th><th>EV Loss</th><th>Verdict</th></tr></thead>
        <tbody>${recentRows || "<tr><td colspan='6'>No attempts yet</td></tr>"}</tbody>
      </table>
    `;
    setStatus("Standings loaded.");
  } catch (err) {
    els.progressWrap.textContent = `Could not load progress: ${err.message}`;
    setStatus(`Progress load failed: ${err.message}`, true);
  }
}

function fillSelect(select, options) {
  if (!select) return;
  select.innerHTML = options.map((o) => `<option value="${o.value}">${o.label}</option>`).join("");
}

async function apiGet(url) {
  const res = await fetch(url, { credentials: "same-origin" });
  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    throw new Error("Authentication required");
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
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
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
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
  return str
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatPct(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function formatRange(rangeValues) {
  if (!Array.isArray(rangeValues) || rangeValues.length !== 2) {
    return "N/A";
  }
  return `${(Number(rangeValues[0]) * 100).toFixed(1)}% - ${(Number(rangeValues[1]) * 100).toFixed(1)}%`;
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
