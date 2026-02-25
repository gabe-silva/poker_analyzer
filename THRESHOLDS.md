# Poker Analyzer - All Classification Thresholds & Assumptions

This document lists every threshold, assumption, and classification rule used by the poker analyzer.

---

## 1. PLAY STYLE CLASSIFICATION

### Minimum Sample Size
- **Unknown Style**: Less than 20 hands analyzed

### VPIP (Voluntarily Put money In Pot) Thresholds
- **Tight**: VPIP < 20%
- **Loose**: VPIP > 28%
- **Middle Ground**: 20% ≤ VPIP ≤ 28%

### PFR (Pre-Flop Raise) Thresholds
- **Passive**: PFR < 14%
- **Aggressive**: PFR > 22%
- **Middle Ground**: 14% ≤ PFR ≤ 22%

### Aggression Factor Thresholds
- **Passive**: AF < 1.5
- **Aggressive**: AF > 2.0
- **Middle Ground**: 1.5 ≤ AF ≤ 2.0

### Extreme Classifications
- **Maniac**: VPIP > 45% AND Aggression Factor > 3.5
- **Nit**: VPIP < 14% AND PFR < 10%

### Style Decision Tree
1. **Tight-Aggressive (TAG)**: VPIP < 20% AND (PFR > 22% OR AF > 2.0)
2. **Tight-Passive (Rock)**: VPIP < 20% AND PFR < 14% AND AF < 1.5
3. **Loose-Aggressive (LAG)**: VPIP > 28% AND (PFR > 22% OR AF > 2.0)
4. **Loose-Passive (Calling Station)**: VPIP > 28% AND PFR < 14% AND AF < 1.5
5. **Tiebreaker**: For middle-ground VPIP (20-28%), use VPIP = 24% as cutoff

---

## 2. SAMPLE CONFIDENCE LEVELS

Based on number of hands analyzed:
- **Low Confidence**: < 100 hands
- **Medium Confidence**: 100-299 hands
- **High Confidence**: 300-999 hands
- **Very High Confidence**: ≥ 1000 hands

---

## 3. PREFLOP TENDENCIES

### VPIP Classifications
- **Very Loose**: VPIP > 33%
- **Very Tight**: VPIP < 17%
- **Normal Range**: 17% ≤ VPIP ≤ 33%

### VPIP-PFR Gap (Calling Tendency)
- **Large Gap** (Calls too much): Gap > 10%
- **Normal Gap**: Gap ≤ 10%

### Limp Rate
- **Limps Frequently**: Limp Rate > 8%
- **Rarely Limps**: Limp Rate ≤ 8%

### 3-Bet Frequency
- **Aggressive 3-Bettor**: 3-Bet% > 10%
- **Rarely 3-Bets**: 3-Bet% < 3% (with ≥20 opportunities)
- **Normal Range**: 3% ≤ 3-Bet% ≤ 10%

### Fold to 3-Bet
- **Exploitable**: Folds to 3-Bet > 70% (with ≥15 opportunities)
- **Normal Range**: Fold to 3-Bet ≤ 70%

---

## 4. POSTFLOP TENDENCIES

### Aggression Factor
- **Highly Aggressive**: AF > 3.0
- **Passive**: AF < 1.2
- **Normal Range**: 1.2 ≤ AF ≤ 3.0

### Flop C-Bet Frequency
- **C-Bets Very Frequently**: C-Bet% > 70%
- **Rarely C-Bets**: C-Bet% < 45%
- **Normal Range**: 45% ≤ C-Bet% ≤ 70%

### Turn Double Barrel Frequency
- **Barrels Aggressively**: Double Barrel% > 60%
- **Gives Up Easily**: Double Barrel% < 35% (with ≥20 opportunities)
- **Exploitable**: Double Barrel% < 40% (with ≥20 opportunities)
- **Normal Range**: 35% ≤ Double Barrel% ≤ 60%

### Overbet Frequency
- **Uses Overbets Frequently**: Overbet% > 10%
- **Normal Range**: Overbet% ≤ 10%

### Check-Raise Frequency
- **Frequent Check-Raiser**: Check-Raise% > 15% (with ≥15 opportunities)
- **Normal Range**: Check-Raise% ≤ 15%

### Fold to Flop Bet
- **Folds Too Much**: Fold to Bet > 55% (with ≥20 opportunities)
- **Normal Range**: Fold to Bet ≤ 55%

---

## 5. SHOWDOWN TENDENCIES

### WTSD (Went To ShowDown)
- **Goes to Showdown Frequently** (Sticky): WTSD > 33%
- **Rarely Goes to Showdown**: WTSD < 22%
- **Normal Range**: 22% ≤ WTSD ≤ 33%

### W$SD (Won Money at ShowDown)
- **Wins at Showdown Frequently** (Selective): W$SD > 54%
- **Loses at Showdown Often** (Overvalues): W$SD < 45%
- **Normal Range**: 45% ≤ W$SD ≤ 54%

### Showdown + Win Combination
- **Major Exploit**: WTSD > 33% AND W$SD < 45%
  - Interpretation: Goes to showdown too often with weak hands

---

## 6. BET SIZING CLASSIFICATIONS

### Bet Size Buckets (as % of pot)
- **Tiny**: 0% - 30% of pot
- **Small**: 30% - 45% of pot
- **Medium**: 45% - 70% of pot
- **Large**: 70% - 100% of pot
- **Overbet**: > 100% of pot

---

## 7. HAND STRENGTH CLASSIFICATIONS

### Hand Strength Values (1-10 scale)
1. **High Card** = 1
2. **Pair** = 2
3. **Two Pair** = 3
4. **Three of a Kind** (Trips/Set) = 4
5. **Straight** = 5
6. **Flush** = 6
7. **Full House** (Boat) = 7
8. **Four of a Kind** (Quads) = 8
9. **Straight Flush** = 9
10. **Royal Flush** = 10

### Bluff vs Value Classification
- **Bluff**: Hand Strength ≤ 2 (Pair or worse)
- **Medium Strength**: Hand Strength = 3 (Two Pair)
- **Value**: Hand Strength ≥ 3 (Two Pair or better)

### River Bet Classifications
- **Value-Heavy River Bets**: Value Rate > 70% (with ≥8 samples)
- **Bluff-Heavy River Bets**: Bluff Rate > 35% (with ≥8 samples)

---

## 8. EXPLOITS & COUNTER-STRATEGIES

### Preflop Exploits

#### Fold to 3-Bet Exploit
- **Trigger**: Fold to 3-Bet > 70% with ≥15 opportunities
- **Counter**: "3-bet bluff their opens frequently"
- **Confidence**: 80%

#### Limp Exploit
- **Trigger**: Limp Rate > 12%
- **Counter**: "Raise their limps aggressively for easy profit"
- **Confidence**: 70%

#### VPIP-PFR Gap Exploit
- **Trigger**: VPIP-PFR Gap > 12%
- **Counter**: "Value bet thinner - they call too wide"
- **Confidence**: 75%

### Postflop Exploits

#### High C-Bet Exploit
- **Trigger**: Flop C-Bet% > 70%
- **Counter**: "Float flops wider, raise bluff occasionally"
- **Confidence**: 70%

#### Fold to Flop Bet Exploit
- **Trigger**: Fold to Flop Bet > 55% with ≥20 opportunities
- **Counter**: "Bluff flop liberally"
- **Confidence**: 80%

#### Low Double Barrel Exploit
- **Trigger**: Double Barrel% < 40% with ≥20 opportunities
- **Counter**: "Call flop c-bets wide, expect turn check"
- **Confidence**: 75%

#### Check-Raise Exploit
- **Trigger**: Check-Raise% > 15% with ≥15 opportunities
- **Counter**: "Check back marginal hands for pot control"
- **Confidence**: 70%

### River Exploits

#### Value-Heavy River Exploit
- **Trigger**: River Bet Value Rate > 70% with ≥8 samples
- **Counter**: "Overfold river to their bets"
- **Confidence**: 85%

#### Bluff-Heavy River Exploit
- **Trigger**: River Bet Bluff Rate > 35% with ≥8 samples
- **Counter**: "Call down lighter on river"
- **Confidence**: 75%

### Showdown Exploits

#### Calling Station Exploit
- **Trigger**: WTSD > 33% AND W$SD < 45%
- **Counter**: "Value bet relentlessly, cut bluffs on river"
- **Confidence**: 80%

---

## 9. CONDITIONAL RULES

### Minimum Sample Sizes for Rules
- **River Bet Strength Analysis**: ≥8 samples per bet size bucket
- **Flop C-Bet Fold Analysis**: ≥20 times facing flop bets
- **3-Bet Fold Analysis**: ≥15 3-bet opportunities
- **Turn Barrel Analysis**: ≥20 double barrel opportunities
- **Turn Give-Up Rule**: ≥40% give-up rate with ≥20 opportunities

---

## 10. STATISTICAL SIGNIFICANCE

### Minimum Sample Sizes for Metrics
- **3-Bet Frequency Classification**: ≥20 opportunities to 3-bet
- **Fold to 3-Bet Analysis**: ≥15 times facing 3-bets
- **C-Bet Analysis**: ≥1 c-bet opportunity (any sample)
- **Fold to Bet Analysis**: ≥20 times facing bets
- **Double Barrel Analysis**: ≥20 opportunities
- **Check-Raise Analysis**: ≥15 opportunities
- **River Bet Strength**: ≥8 samples

---

## 11. REPORTING DISPLAY LIMITS

### Tendency List
- **Maximum Tendencies Shown in Dashboard**: Top 5

### Exploit List
- **Maximum Exploits Shown in Dashboard**: Top 3

---

## Summary

All thresholds are based on modern poker theory and solver-based strategies:

- **VPIP ~20%**: Standard tight range for 6-max
- **PFR ~22%**: Aggressive opening standard
- **WTSD ~28%**: Typical for balanced play
- **W$SD ~50%**: Expected with proper hand selection
- **AF ~2.0**: Balanced aggression

The analyzer uses these benchmarks to identify deviations and exploitable patterns in player behavior.
