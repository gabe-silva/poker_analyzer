# LAG Cash Game Mastery Plan + Trainer Build Roadmap

## Objective
Build a dedicated training app that helps you master profitable Loose-Aggressive (LAG) cash play, with emphasis on:
- Position-aware preflop and postflop decisions
- Exploiting calling stations and risk-averse players
- Avoiding large downswings through bankroll and session controls
- Measuring decision quality using EV by action and sizing

This trainer is separate from the current analyzer, but should reuse existing profiling logic where possible.

## Success Metrics
- Decision EV loss versus best action <= 0.10 bb/decision in core drill packs
- Position accuracy (BTN/CO/SB/BB) >= 85% in preflop quizzes
- Postflop line selection accuracy >= 75% in single-raised and 3-bet pots
- Stable bankroll protocol adherence >= 95% sessions
- App latency for EV feedback <= 2 seconds for standard scenarios

## Player Archetype Library (Initial v1)
Use these as selectable opponent profiles and as nodelock presets in the scenario engine.

| Archetype | Typical Stats (VPIP / PFR / AF) | Core Behavior | Main Exploit |
|---|---|---|---|
| Nit | 10-16 / 8-13 / 1.2-2.0 | Waits for strong hands, overfolds pressure nodes | Steal blinds, overfold vs river aggression |
| TAG Reg | 18-24 / 15-21 / 2.0-3.0 | Balanced, fundamentally sound | Attack capped lines, deny realization OOP |
| LAG Reg | 28-40 / 22-32 / 2.5-4.0 | High pressure, wide open/3-bet, barrels | Trap stronger bluff-catchers, widen value check-raises |
| Loose-Passive Calling Station | 35-55 / 5-15 / <1.5 | Calls too much, under-bluffs | Value bet thinner, reduce pure bluffs |
| Maniac | 45+ / 30+ / 4.0+ | Excessive aggression and overbluffing | Bluff-catch wider, let them punt |
| Weak-Tight (Scared Money) | 14-22 / 10-16 / 1.4-2.2 | Avoids high-variance spots | Apply multi-street pressure, size up turn/river |
| Fit-or-Fold Flop Player | 22-30 / 16-22 / 1.5-2.3 | Continues only when connected | High flop c-bet frequency on favorable boards |
| One-and-Done C-Bettor | 20-28 / 16-24 / 1.6-2.4 | C-bets wide, low turn barrel | Float flop, stab turn when checked to |
| Trappy Slow-Player | 18-26 / 12-20 / 1.3-2.0 | Under-raises monsters, deceptive checks | Pot-control medium strength, avoid punt bluffs |
| Overfolder vs 3-Bets | 18-30 / 15-24 / any | Folds too much after opening | 3-bet bluff more in blocker-heavy combos |
| Overcaller Preflop | 30-45 / 12-20 / 1.5-2.5 | Calls opens/3-bets too wide | Isolate bigger preflop, value-heavy postflop |
| Short-Stack Jammer | 20-35 / 14-24 / 2.0-3.5 | Push/fold bias at low SPR | Tighten opens vs reshove, call jams by pot odds |

Note: Keep these as editable profiles. Real opponents drift by stake and pool.

## LAG Operating Principles (To Avoid Blowups)
1. Position is your edge multiplier: widen aggression in late position, tighten early position.
2. Pressure capped ranges, not random people: identify who cannot defend.
3. Build pots with equity + initiative, not ego.
4. Avoid low-EV hero wars OOP versus strong ranges.
5. Track red flags in real time: tilt triggers, stack-off drift, overbluff runouts.
6. Bankroll and stop-loss rules are part of strategy, not optional.

## Product Scope (What the App Must Do)
1. Choose table size: 2 to 7 total seats (Hero + 1 to 6 opponents).
2. Select format/street node:
   - Preflop
   - Flop
   - Turn
   - River
   - Single-raised pot / 3-bet pot / 4-bet pot
3. Select Hero position: UTG, HJ/LJ, CO, BTN, SB, BB (available positions vary with seat count).
4. Select opponent archetypes for each seat from library above.
5. Stack setup:
   - Equal stacks toggle (default 100bb)
   - Custom per-player stacks
   - Constant blinds (default 1bb/2bb in trainer units)
6. Generate scenario table with:
   - Board, pot, stacks, action history, SPR, ranges summary
7. Ask one targeted decision prompt:
   - Fold / Check / Call / Bet / Raise
   - If bet/raise: size selection + intent tag (`Value` or `Bluff`)
8. Free-response text field:
   - "Explain your line and expected folds/calls from each villain."
9. EV feedback:
   - EV for all legal actions
   - Best action, EV delta, and confidence interval
   - Raise-size comparison heatmap (small/medium/large/overbet)
10. Progress tracking:
   - Accuracy by position, street, and opponent type
   - Leak dashboard and spaced-repetition queue

## Scenario Data Model (v1)
```json
{
  "scenario_id": "btn_flop_mw_0001",
  "game_type": "cash_nlhe_6max",
  "blinds": {"sb": 1, "bb": 2},
  "street": "flop",
  "hero": {"seat": 5, "position": "BTN", "stack_bb": 100, "hand": "AhQh"},
  "players": [
    {"seat": 1, "position": "SB", "archetype": "CallingStation", "stack_bb": 120},
    {"seat": 2, "position": "BB", "archetype": "WeakTight", "stack_bb": 95}
  ],
  "pot_bb": 14.5,
  "board": ["Qs", "8d", "4c"],
  "action_history": [
    "SB bet 5.0bb",
    "BB call 5.0bb"
  ],
  "decision_prompt": "BTN to act: choose best action and size."
}
```

## EV Engine Design (v1 -> v2)
### v1 (Fast Approximation)
- Use predefined range templates by position/archetype/street.
- Estimate fold equity from profile tendencies and line constraints.
- EV formulas:
  - `EV_fold = 0` (from decision point baseline)
  - `EV_call = equity_vs_continue * final_pot_if_call - call_cost`
  - `EV_raise = FE * pot_now + (1 - FE) * (equity_vs_continue * final_pot_if_called - raise_risk)`
- Run Monte Carlo board rollouts for unresolved runouts.

### v2 (Higher Fidelity)
- Add node-locked exploit engine with range updates after each action.
- Add multi-opponent EV decomposition for multiway pots.
- Add confidence bands and sensitivity analysis for villain assumptions.

## UX Blueprint (Focused on Drills)
### Main Controls
- Seats slider: 2-7
- Street selector
- Hero position selector
- Opponent profile selectors per seat
- Stack mode toggle (`Equal` / `Custom`)
- Blinds fixed panel

### Scenario Panel
- Table visualization (seats, stacks, pot, action line)
- Board and Hero cards
- Prompt + free response box

### Action Panel
- Buttons: Fold / Check / Call / Bet / Raise
- Bet/Raise size presets: 33%, 50%, 75%, 125% pot + custom input
- Intent toggle: `Value` / `Bluff`
- Submit and receive EV report

### Feedback Panel
- EV table by action
- "Best action" banner with EV delta
- Why-it-works explanation (range and blocker summary)
- Mistake tags (`Overbluff`, `Underbluff`, `TooThinValue`, `MissedValue`, `Overfold`)

## Example Scenario (Your Requested Format)
- Setup: 6-max cash, blinds fixed at 1/2, Hero on BTN, postflop, 2 villains still in hand.
- Stacks: Hero 100bb, SB 120bb (Calling Station), BB 95bb (Weak-Tight).
- Pot: 14.5bb on flop.
- Board: Qs 8d 4c.
- Action: SB bets 5bb, BB calls 5bb, Hero to act.
- Prompt: "Choose one move. If raising, choose size and mark as Value or Bluff."
- App feedback after submit:
  - EV(Fold)
  - EV(Call)
  - EV(Raise 16bb Value)
  - EV(Raise 22bb Value)
  - EV(Raise 22bb Bluff)
  - EV delta vs best line + short exploit explanation

## Build Plan (8 Weeks)
### Week 1: Foundation
- Create new module folder: `trainer/`
- Define scenario, archetype, and decision schemas
- Add seed archetype JSON and initial range templates

### Week 2: Scenario Generator
- Build spot generator for preflop/flop/turn/river nodes
- Add controls for seat count, position, stacks, archetypes
- Implement reproducible random seed mode

### Week 3: EV Engine v1
- Integrate `eval7` for hand strength/equity simulation
- Implement action EV calculation and raise size presets
- Add value/bluff intent branch to feedback

### Week 4: UI v1
- Build trainer page with table, prompt, action buttons, free response
- Add result card with EV table and line explanation

### Week 5: Tracking + Standings
- Save attempts in SQLite
- Add personal standings dashboard:
  - EV loss per decision
  - Position heatmap
  - Opponent-type performance

### Week 6: Curriculum Packs
- Add targeted drill packs:
  - BTN vs blinds single-raised pots
  - CO open vs blind defense
  - Turn barrel decisions vs stations and nits

### Week 7: Validation + Test Suite
- Unit tests for EV formulas and action legality
- Regression tests for scenario reproducibility
- Calibration checks against solved benchmark spots

### Week 8: Polish + Release
- UX polish and mobile responsive adjustments
- Export/import for study sessions
- "Play 20-hand exam mode" with report card

## Delegated Workstreams (Parallel)
### Workstream A: Strategy Content
- Own archetype definitions, range templates, scenario packs
- Deliver benchmark answer keys and exploit notes

### Workstream B: Engine
- Own scenario generator, EV service, and simulation performance
- Deliver deterministic API and confidence intervals

### Workstream C: Frontend
- Own trainer UX, action controls, EV visualization, responsiveness
- Deliver low-friction drill loop for high repetition

### Workstream D: Analytics + QA
- Own attempt tracking, standings dashboard, testing, calibration
- Deliver reliability gates before each release

## Integration with Existing Project
Reuse where possible:
- `/Users/gabe/Desktop/poker_analyzer/models.py` for shared domain concepts
- `/Users/gabe/Desktop/poker_analyzer/stats/aggregate.py` for style heuristics
- `/Users/gabe/Desktop/poker_analyzer/dashboard.py` patterns for simple Python-to-HTML output

Keep trainer separated:
- New app namespace under `trainer/`
- No breaking changes to current hand-history analyzer workflows

## Personal Study Protocol (12-Week Loop)
### Daily (60-90 min)
- 20 scenario reps in one focused node (example: BTN flop vs 2 players)
- Tag errors by category, review top 3 mistakes
- 10-minute review of one key concept (range advantage, blockers, sizing)

### Weekly
- 1 deep hand review session from your own database
- 1 focused preflop calibration session by position
- 1 bankroll and mental-game audit (tilt, stop-loss adherence)

### Monthly
- Leak report by position and opponent type
- Re-benchmark against fixed "exam pack" of scenarios
- Promote to harder packs only if EV-loss threshold is met

## Hard Risk Controls (Non-Negotiable)
- Use a dedicated bankroll and separate life-expense funds.
- Session stop-loss: 3 buy-ins.
- Forced cooldown after stop-loss hit.
- Move down stakes when bankroll floor is breached.
- No high-variance bluff lines while emotionally compromised.
- No volume grind if A-game checklist fails pre-session.

## Literature and Tools to Study First
1. Modern Poker Theory (Michael Acevedo)  
   https://www.simonandschuster.com/books/Modern-Poker-Theory/Michael-Acevedo/9781909457898
2. Applications of No-Limit Hold'em (Matthew Janda)  
   https://books.apple.com/us/book/applications-of-no-limit-holdem/id1018955714
3. Free 6-max cash preflop ranges (PokerCoaching)  
   https://pokercoaching.com/preflop-charts
4. Free cash preflop charts (Upswing)  
   https://upswingpoker.com/charts/
5. Current solver capabilities and simplification approaches (GTO Wizard)  
   https://blog.gtowizard.com/status-and-info-about-our-solutions/  
   https://blog.gtowizard.com/simplified-solutions-and-a-new-interface/
6. Optional Python EV library  
   https://pypi.org/project/eval7/

## Immediate Next Build Step
Implement Week 1 now:
- Create `trainer/` skeleton
- Add archetype schema + seed data
- Add scenario schema + validator
- Add CLI command to generate one scenario from selected filters
