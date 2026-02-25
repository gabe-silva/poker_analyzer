"""
Showdown statistics calculation.

Computes key showdown metrics:
- WTSD (Went To ShowDown)
- W$SD (Won money at ShowDown)
- Showdown hand strength distribution
- Bluff frequency estimation
- Bet-to-strength correlation
"""

from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

from models import (
    ActionType, Street, ParsedHand, PlayerAction,
    HandStrength, HandResult
)


# Bet size buckets for analysis
BET_SIZE_BUCKETS = {
    "tiny": (0.0, 0.30),      # < 30% pot
    "small": (0.30, 0.45),    # 30-45% pot
    "medium": (0.45, 0.70),   # 45-70% pot
    "large": (0.70, 1.0),     # 70-100% pot
    "overbet": (1.0, float('inf'))  # > pot
}


def get_bet_size_bucket(pot_ratio: float) -> str:
    """Classify a bet size ratio into a bucket."""
    for bucket_name, (low, high) in BET_SIZE_BUCKETS.items():
        if low <= pot_ratio < high:
            return bucket_name
    return "overbet"


@dataclass
class BetStrengthCorrelation:
    """
    Tracks correlation between bet sizes and hand strength.
    
    This is the "killer stat" - reveals if bets are value-heavy or bluff-heavy.
    """
    # Map: size_bucket -> list of hand strengths
    strengths_by_bet_size: dict[str, list[int]] = field(
        default_factory=lambda: defaultdict(list)
    )
    
    # Map: street -> size_bucket -> list of hand strengths
    strengths_by_street_and_size: dict[str, dict[str, list[int]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )
    
    def add_sample(
        self, 
        pot_ratio: float, 
        hand_strength: HandStrength,
        street: Street
    ):
        """Record a bet with its resulting hand strength."""
        bucket = get_bet_size_bucket(pot_ratio)
        strength_val = int(hand_strength)
        
        self.strengths_by_bet_size[bucket].append(strength_val)
        self.strengths_by_street_and_size[street.value][bucket].append(strength_val)
    
    def avg_strength_for_size(self, bucket: str) -> float:
        """Average hand strength for a bet size bucket."""
        samples = self.strengths_by_bet_size.get(bucket, [])
        if not samples:
            return 0.0
        return sum(samples) / len(samples)
    
    def bluff_rate_for_size(
        self, 
        bucket: str, 
        bluff_threshold: int = 2
    ) -> float:
        """
        Estimate bluff frequency for a bet size.
        
        Args:
            bucket: Bet size bucket
            bluff_threshold: Max hand strength to consider a "bluff"
                           (default 2 = pair or worse)
        """
        samples = self.strengths_by_bet_size.get(bucket, [])
        if not samples:
            return 0.0
        
        bluffs = sum(1 for s in samples if s <= bluff_threshold)
        return bluffs / len(samples)
    
    def get_street_analysis(self, street: str) -> dict[str, dict]:
        """Get detailed analysis for a specific street."""
        result = {}
        street_data = self.strengths_by_street_and_size.get(street, {})
        
        for bucket, strengths in street_data.items():
            if not strengths:
                continue
            
            result[bucket] = {
                "samples": len(strengths),
                "avg_strength": sum(strengths) / len(strengths),
                "bluff_rate": sum(1 for s in strengths if s <= 2) / len(strengths),
                "value_rate": sum(1 for s in strengths if s >= 3) / len(strengths),
            }
        
        return result


@dataclass
class ShowdownStats:
    """
    Showdown statistics for a player.
    """
    # Core counts
    hands_played: int = 0
    saw_showdown: int = 0
    won_at_showdown: int = 0
    
    # Went to showdown after seeing each street
    saw_flop: int = 0
    wtsd_after_flop: int = 0
    saw_turn: int = 0
    wtsd_after_turn: int = 0
    saw_river: int = 0
    wtsd_after_river: int = 0
    
    # Hand strength at showdown
    showdown_strengths: list[int] = field(default_factory=list)
    winning_strengths: list[int] = field(default_factory=list)
    losing_strengths: list[int] = field(default_factory=list)
    
    # Bet-strength correlation
    bet_strength_correlation: BetStrengthCorrelation = field(
        default_factory=BetStrengthCorrelation
    )
    
    # River-specific stats (most honest street)
    river_bets_to_showdown: int = 0
    river_bet_strength_samples: list[int] = field(default_factory=list)
    
    @property
    def wtsd(self) -> float:
        """Went to showdown percentage (of hands played)."""
        if self.hands_played == 0:
            return 0.0
        return self.saw_showdown / self.hands_played
    
    @property
    def wtsd_flop(self) -> float:
        """WTSD given saw flop."""
        if self.saw_flop == 0:
            return 0.0
        return self.wtsd_after_flop / self.saw_flop
    
    @property
    def wtsd_turn(self) -> float:
        """WTSD given saw turn."""
        if self.saw_turn == 0:
            return 0.0
        return self.wtsd_after_turn / self.saw_turn
    
    @property
    def wtsd_river(self) -> float:
        """WTSD given saw river."""
        if self.saw_river == 0:
            return 0.0
        return self.wtsd_after_river / self.saw_river
    
    @property
    def w_sd(self) -> float:
        """Won money at showdown percentage."""
        if self.saw_showdown == 0:
            return 0.0
        return self.won_at_showdown / self.saw_showdown
    
    @property
    def avg_showdown_strength(self) -> float:
        """Average hand strength at showdown."""
        if not self.showdown_strengths:
            return 0.0
        return sum(self.showdown_strengths) / len(self.showdown_strengths)
    
    @property
    def avg_winning_strength(self) -> float:
        """Average strength of winning hands."""
        if not self.winning_strengths:
            return 0.0
        return sum(self.winning_strengths) / len(self.winning_strengths)
    
    @property
    def avg_losing_strength(self) -> float:
        """Average strength of losing hands."""
        if not self.losing_strengths:
            return 0.0
        return sum(self.losing_strengths) / len(self.losing_strengths)
    
    @property
    def river_bet_bluff_rate(self) -> float:
        """Estimated bluff rate on river bets (bucket ≤ pair)."""
        if not self.river_bet_strength_samples:
            return 0.0
        bluffs = sum(1 for s in self.river_bet_strength_samples if s <= 2)
        return bluffs / len(self.river_bet_strength_samples)
    
    @property
    def river_bet_value_rate(self) -> float:
        """Estimated value rate on river bets (bucket ≥ two pair)."""
        if not self.river_bet_strength_samples:
            return 0.0
        value = sum(1 for s in self.river_bet_strength_samples if s >= 3)
        return value / len(self.river_bet_strength_samples)


class ShowdownAnalyzer:
    """
    Analyzes showdown outcomes to compute player statistics.
    """
    
    def analyze(
        self, 
        hands: list[ParsedHand], 
        player_id: str
    ) -> ShowdownStats:
        """
        Compute showdown statistics for a player.
        
        Args:
            hands: List of parsed hands to analyze
            player_id: ID of the player to analyze
            
        Returns:
            ShowdownStats object with computed statistics
        """
        stats = ShowdownStats()
        
        for hand in hands:
            # Skip if player not in hand
            player = hand.get_player_by_id(player_id)
            if not player:
                continue
            
            stats.hands_played += 1
            
            # Check which streets player saw
            saw_flop = self._saw_street(hand, player_id, Street.FLOP)
            saw_turn = self._saw_street(hand, player_id, Street.TURN)
            saw_river = self._saw_street(hand, player_id, Street.RIVER)
            
            if saw_flop:
                stats.saw_flop += 1
            if saw_turn:
                stats.saw_turn += 1
            if saw_river:
                stats.saw_river += 1
            
            # Check showdown result
            result = hand.results.get(player_id)
            reached_showdown = result and result.reached_showdown
            
            if reached_showdown:
                stats.saw_showdown += 1
                
                if saw_flop:
                    stats.wtsd_after_flop += 1
                if saw_turn:
                    stats.wtsd_after_turn += 1
                if saw_river:
                    stats.wtsd_after_river += 1
                
                # Track showdown strength
                if result.hand_strength:
                    strength_val = int(result.hand_strength)
                    stats.showdown_strengths.append(strength_val)
                    
                    if result.won_pot:
                        stats.won_at_showdown += 1
                        stats.winning_strengths.append(strength_val)
                    else:
                        stats.losing_strengths.append(strength_val)
                    
                    # Correlate bets with strength
                    self._analyze_bet_strength_correlation(
                        stats, hand, player_id, result
                    )
                elif result.won_pot:
                    stats.won_at_showdown += 1
        
        return stats
    
    def _saw_street(
        self, 
        hand: ParsedHand, 
        player_id: str, 
        street: Street
    ) -> bool:
        """Check if player saw a given street (didn't fold before)."""
        # Check for any action on this street
        street_actions = hand.get_actions_on_street(street)
        if not street_actions:
            return False
        
        # Check if player folded before this street
        street_order = [Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER]
        current_idx = street_order.index(street)
        
        for i in range(current_idx):
            prev_street = street_order[i]
            for action in hand.get_actions_on_street(prev_street):
                if (action.player_id == player_id and 
                    action.action_type == ActionType.FOLD):
                    return False
        
        return True
    
    def _analyze_bet_strength_correlation(
        self,
        stats: ShowdownStats,
        hand: ParsedHand,
        player_id: str,
        result: HandResult
    ):
        """
        Correlate bet sizes with hand strength at showdown.
        
        This is crucial for understanding if a player's bets are
        value-heavy or bluff-heavy.
        """
        if not result.hand_strength:
            return
        
        strength = result.hand_strength
        
        # Analyze bets on each street
        for street in [Street.FLOP, Street.TURN, Street.RIVER]:
            actions = hand.get_actions_on_street(street)
            
            for action in actions:
                if action.player_id != player_id:
                    continue
                
                if action.action_type == ActionType.BET_RAISE:
                    if action.pot_before > 0 and action.amount > 0:
                        pot_ratio = action.amount / action.pot_before
                        
                        stats.bet_strength_correlation.add_sample(
                            pot_ratio, strength, street
                        )
                        
                        # Special tracking for river bets
                        if street == Street.RIVER:
                            stats.river_bets_to_showdown += 1
                            stats.river_bet_strength_samples.append(
                                int(strength)
                            )


def calculate_showdown_stats(
    hands: list[ParsedHand], 
    player_id: str
) -> ShowdownStats:
    """
    Convenience function to calculate showdown stats.
    
    Args:
        hands: List of parsed hands
        player_id: Player to analyze
        
    Returns:
        ShowdownStats object
    """
    analyzer = ShowdownAnalyzer()
    return analyzer.analyze(hands, player_id)
