"""
Aggregate statistics and player profile generation.

Combines preflop, postflop, and showdown statistics into
a comprehensive player profile with actionable insights.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from models import ParsedHand
from stats.preflop import PreflopStats, calculate_preflop_stats
from stats.postflop import PostflopStats, calculate_postflop_stats
from stats.showdown import ShowdownStats, calculate_showdown_stats


class PlayStyle(Enum):
    """Basic player style classifications."""
    UNKNOWN = "Unknown"
    
    # Preflop styles
    TIGHT_PASSIVE = "Tight-Passive (Rock)"
    TIGHT_AGGRESSIVE = "Tight-Aggressive (TAG)"
    LOOSE_PASSIVE = "Loose-Passive (Calling Station)"
    LOOSE_AGGRESSIVE = "Loose-Aggressive (LAG)"
    
    # Hybrid descriptions
    MANIAC = "Maniac"
    NIT = "Nit"


@dataclass
class ConditionalRule:
    """
    A conditional rule derived from player data.
    
    Format: "IF [condition] THEN [conclusion] ([confidence]%)"
    """
    condition: str
    conclusion: str
    confidence: float  # 0.0 to 1.0
    sample_size: int
    
    def __str__(self) -> str:
        conf_pct = round(self.confidence * 100, 1)
        return f"IF {self.condition} THEN {self.conclusion} ({conf_pct}% over {self.sample_size} samples)"


@dataclass
class Exploit:
    """
    An exploitable tendency with recommended counter-strategy.
    """
    description: str
    counter_strategy: str
    confidence: float
    category: str  # e.g., "preflop", "postflop", "river"


@dataclass
class PlayerProfile:
    """
    Complete player profile with statistics and insights.
    """
    player_id: str
    hands_analyzed: int
    
    # Raw statistics
    preflop: PreflopStats
    postflop: PostflopStats
    showdown: ShowdownStats
    
    # Derived classifications
    play_style: PlayStyle = PlayStyle.UNKNOWN
    
    # Actionable insights
    tendencies: list[str] = field(default_factory=list)
    conditional_rules: list[ConditionalRule] = field(default_factory=list)
    exploits: list[Exploit] = field(default_factory=list)
    
    # Confidence assessment
    sample_confidence: str = "Low"  # Low/Medium/High


class ProfileAnalyzer:
    """
    Generates comprehensive player profiles from hand histories.
    """
    
    # Thresholds for style classification
    VPIP_TIGHT = 0.20   # < 20% = tight
    VPIP_LOOSE = 0.28   # > 28% = loose
    PFR_PASSIVE = 0.14  # < 14% = passive
    PFR_AGGRESSIVE = 0.22  # > 22% = aggressive

    # Confidence thresholds
    HANDS_LOW_CONFIDENCE = 100
    HANDS_MEDIUM_CONFIDENCE = 300
    HANDS_HIGH_CONFIDENCE = 1000
    
    def analyze(
        self, 
        hands: list[ParsedHand], 
        player_id: str
    ) -> PlayerProfile:
        """
        Generate a complete player profile.
        
        Args:
            hands: List of parsed hands to analyze
            player_id: ID of the player to analyze
            
        Returns:
            PlayerProfile with all statistics and insights
        """
        # Calculate raw statistics
        preflop = calculate_preflop_stats(hands, player_id)
        postflop = calculate_postflop_stats(hands, player_id)
        showdown = calculate_showdown_stats(hands, player_id)
        
        # Create base profile
        profile = PlayerProfile(
            player_id=player_id,
            hands_analyzed=preflop.hands_played,
            preflop=preflop,
            postflop=postflop,
            showdown=showdown
        )
        
        # Classify play style
        profile.play_style = self._classify_style(preflop, postflop)
        
        # Generate tendencies
        profile.tendencies = self._identify_tendencies(preflop, postflop, showdown)
        
        # Generate conditional rules
        profile.conditional_rules = self._generate_rules(preflop, postflop, showdown)
        
        # Identify exploits
        profile.exploits = self._identify_exploits(preflop, postflop, showdown)
        
        # Assess confidence
        profile.sample_confidence = self._assess_confidence(preflop.hands_played)
        
        return profile
    
    def _classify_style(
        self, 
        preflop: PreflopStats, 
        postflop: PostflopStats
    ) -> PlayStyle:
        """Classify player into a basic style category."""
        
        if preflop.hands_played < 20:
            return PlayStyle.UNKNOWN
        
        vpip = preflop.vpip
        pfr = preflop.pfr
        af = postflop.total_aggression_factor
        
        # Extreme cases
        if vpip > 0.45 and af > 3.5:
            return PlayStyle.MANIAC
        if vpip < 0.14 and pfr < 0.10:
            return PlayStyle.NIT
        
        # Standard quadrant classification
        is_loose = vpip > self.VPIP_LOOSE
        is_tight = vpip < self.VPIP_TIGHT
        is_aggressive = pfr > self.PFR_AGGRESSIVE or af > 2.0
        is_passive = pfr < self.PFR_PASSIVE and af < 1.5
        
        if is_tight and is_aggressive:
            return PlayStyle.TIGHT_AGGRESSIVE
        elif is_tight and is_passive:
            return PlayStyle.TIGHT_PASSIVE
        elif is_loose and is_aggressive:
            return PlayStyle.LOOSE_AGGRESSIVE
        elif is_loose and is_passive:
            return PlayStyle.LOOSE_PASSIVE
        
        # In-between cases - use aggression as tiebreaker
        if is_aggressive:
            return PlayStyle.TIGHT_AGGRESSIVE if vpip < 0.26 else PlayStyle.LOOSE_AGGRESSIVE
        else:
            return PlayStyle.TIGHT_PASSIVE if vpip < 0.26 else PlayStyle.LOOSE_PASSIVE
    
    def _identify_tendencies(
        self,
        preflop: PreflopStats,
        postflop: PostflopStats,
        showdown: ShowdownStats
    ) -> list[str]:
        """Generate human-readable tendency descriptions."""
        
        tendencies = []
        
        # Preflop tendencies
        if preflop.vpip > 0.33:
            tendencies.append("Plays very loose preflop (VPIP > 33%)")
        elif preflop.vpip < 0.17:
            tendencies.append("Plays very tight preflop (VPIP < 17%)")

        if preflop.vpip_pfr_gap > 0.10:
            tendencies.append(f"Large VPIP-PFR gap ({preflop.vpip_pfr_gap:.1%}) - calls too much")

        if preflop.limp_rate > 0.08:
            tendencies.append(f"Limps frequently ({preflop.limp_rate:.1%})")

        if preflop.three_bet_frequency > 0.10:
            tendencies.append("Aggressive 3-bettor")
        elif preflop.three_bet_frequency < 0.03 and preflop.three_bet_opportunities >= 20:
            tendencies.append("Rarely 3-bets (value-heavy range)")
        
        # Postflop tendencies
        if postflop.flop.cbet_frequency > 0.70:
            tendencies.append("C-bets very frequently (easy to float)")
        elif postflop.flop.cbet_frequency < 0.45:
            tendencies.append("Rarely c-bets (honest betting)")

        if postflop.double_barrel_frequency > 0.60:
            tendencies.append("Barrels aggressively on turn")
        elif postflop.double_barrel_frequency < 0.35:
            tendencies.append("Gives up easily on turn")

        if postflop.total_aggression_factor > 3.0:
            tendencies.append("Highly aggressive postflop")
        elif postflop.total_aggression_factor < 1.2:
            tendencies.append("Passive postflop (rarely bets without value)")

        if postflop.overbet_frequency > 0.10:
            tendencies.append("Uses overbets frequently")
        
        # Showdown tendencies
        if showdown.wtsd > 0.33:
            tendencies.append("Goes to showdown frequently (sticky)")
        elif showdown.wtsd < 0.22:
            tendencies.append("Rarely goes to showdown (folds a lot)")

        if showdown.w_sd > 0.54:
            tendencies.append("Wins at showdown frequently (selective)")
        elif showdown.w_sd < 0.45:
            tendencies.append("Loses at showdown often (overvalues hands)")

        if showdown.river_bet_value_rate > 0.70:
            tendencies.append("River bets are highly value-weighted")
        elif showdown.river_bet_bluff_rate > 0.35:
            tendencies.append("Bluffs frequently on river")
        
        return tendencies
    
    def _generate_rules(
        self,
        preflop: PreflopStats,
        postflop: PostflopStats,
        showdown: ShowdownStats
    ) -> list[ConditionalRule]:
        """Generate conditional rules from statistics."""
        
        rules = []
        
        # River bet strength rule
        river_analysis = showdown.bet_strength_correlation.get_street_analysis("river")
        for bucket, data in river_analysis.items():
            if data["samples"] >= 8:
                value_rate = data["value_rate"]
                rules.append(ConditionalRule(
                    condition=f"river bet is {bucket}",
                    conclusion=f"value hand (two pair+) {value_rate:.0%} of time",
                    confidence=value_rate,
                    sample_size=data["samples"]
                ))

        # C-bet fold rule
        if postflop.flop.faced_bet_count >= 20:
            fold_rate = postflop.flop.fold_to_bet
            if fold_rate > 0.50:
                rules.append(ConditionalRule(
                    condition="we c-bet flop",
                    conclusion=f"they fold {fold_rate:.0%} of time",
                    confidence=fold_rate,
                    sample_size=postflop.flop.faced_bet_count
                ))

        # 3-bet fold rule
        if preflop.fold_to_3bet_opportunities >= 15:
            fold_rate = preflop.fold_to_3bet
            rules.append(ConditionalRule(
                condition="we 3-bet their open",
                conclusion=f"they fold {fold_rate:.0%} of time",
                confidence=fold_rate,
                sample_size=preflop.fold_to_3bet_opportunities
            ))

        # Barrel giving up rule
        if postflop.double_barrel_opportunities >= 20:
            give_up_rate = 1 - postflop.double_barrel_frequency
            if give_up_rate > 0.40:
                rules.append(ConditionalRule(
                    condition="they c-bet flop and we call",
                    conclusion=f"they check turn {give_up_rate:.0%} of time",
                    confidence=give_up_rate,
                    sample_size=postflop.double_barrel_opportunities
                ))
        
        return rules
    
    def _identify_exploits(
        self,
        preflop: PreflopStats,
        postflop: PostflopStats,
        showdown: ShowdownStats
    ) -> list[Exploit]:
        """Identify exploitable weaknesses and counter-strategies."""
        
        exploits = []
        
        # Preflop exploits
        if preflop.fold_to_3bet > 0.70 and preflop.fold_to_3bet_opportunities >= 15:
            exploits.append(Exploit(
                description=f"Folds to 3-bets {preflop.fold_to_3bet:.0%} of time",
                counter_strategy="3-bet bluff their opens frequently",
                confidence=0.8,
                category="preflop"
            ))

        if preflop.limp_rate > 0.12:
            exploits.append(Exploit(
                description=f"Limps {preflop.limp_rate:.0%} of hands",
                counter_strategy="Raise their limps aggressively for easy profit",
                confidence=0.7,
                category="preflop"
            ))

        if preflop.vpip_pfr_gap > 0.12:
            exploits.append(Exploit(
                description=f"Large VPIP-PFR gap ({preflop.vpip_pfr_gap:.1%})",
                counter_strategy="Value bet thinner - they call too wide",
                confidence=0.75,
                category="preflop"
            ))
        
        # Postflop exploits
        if postflop.flop.cbet_frequency > 0.70:
            exploits.append(Exploit(
                description=f"C-bets {postflop.flop.cbet_frequency:.0%} of flops",
                counter_strategy="Float flops wider, raise bluff occasionally",
                confidence=0.7,
                category="postflop"
            ))

        if postflop.flop.fold_to_bet > 0.55 and postflop.flop.faced_bet_count >= 20:
            exploits.append(Exploit(
                description=f"Folds to flop bets {postflop.flop.fold_to_bet:.0%}",
                counter_strategy="Bluff flop liberally",
                confidence=0.8,
                category="postflop"
            ))

        if postflop.double_barrel_frequency < 0.40 and postflop.double_barrel_opportunities >= 20:
            exploits.append(Exploit(
                description=f"Double barrels only {postflop.double_barrel_frequency:.0%}",
                counter_strategy="Call flop c-bets wide, expect turn check",
                confidence=0.75,
                category="postflop"
            ))

        if postflop.check_raise_frequency > 0.15 and postflop.check_raise_opportunities >= 15:
            exploits.append(Exploit(
                description=f"Check-raises {postflop.check_raise_frequency:.0%}",
                counter_strategy="Check back marginal hands for pot control",
                confidence=0.7,
                category="postflop"
            ))
        
        # River exploits
        if showdown.river_bet_value_rate > 0.70 and len(showdown.river_bet_strength_samples) >= 8:
            exploits.append(Exploit(
                description=f"River bets are {showdown.river_bet_value_rate:.0%} value",
                counter_strategy="Overfold river to their bets",
                confidence=0.85,
                category="river"
            ))

        if showdown.river_bet_bluff_rate > 0.35 and len(showdown.river_bet_strength_samples) >= 8:
            exploits.append(Exploit(
                description=f"River bluff rate is {showdown.river_bet_bluff_rate:.0%}",
                counter_strategy="Call down lighter on river",
                confidence=0.75,
                category="river"
            ))

        # Showdown exploits
        if showdown.wtsd > 0.33 and showdown.w_sd < 0.45:
            exploits.append(Exploit(
                description="Goes to showdown too often and loses",
                counter_strategy="Value bet relentlessly, cut bluffs on river",
                confidence=0.8,
                category="showdown"
            ))
        
        return exploits
    
    def _assess_confidence(self, hands: int) -> str:
        """Assess overall confidence in the analysis."""
        if hands < self.HANDS_LOW_CONFIDENCE:
            return "Low"
        elif hands < self.HANDS_MEDIUM_CONFIDENCE:
            return "Medium"
        elif hands < self.HANDS_HIGH_CONFIDENCE:
            return "High"
        else:
            return "Very High"


def generate_profile(
    hands: list[ParsedHand], 
    player_id: str
) -> PlayerProfile:
    """
    Convenience function to generate a player profile.
    
    Args:
        hands: List of parsed hands
        player_id: Player to analyze
        
    Returns:
        PlayerProfile object
    """
    analyzer = ProfileAnalyzer()
    return analyzer.analyze(hands, player_id)
