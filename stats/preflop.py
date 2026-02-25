"""
Preflop statistics calculation.

Computes key preflop metrics that reveal player tendencies:
- VPIP (Voluntarily Put money In Pot)
- PFR (Preflop Raise percentage)
- 3-bet frequency
- Limp rate
- Open raise frequency by position
"""

from dataclasses import dataclass, field
from typing import Optional

from models import ActionType, Street, ParsedHand, PlayerAction


@dataclass
class PreflopStats:
    """
    Preflop statistics for a player.
    
    All percentages are stored as floats (0.0 to 1.0).
    Raw counts are also stored for confidence assessment.
    """
    # Core stats
    hands_played: int = 0
    vpip_count: int = 0
    pfr_count: int = 0
    
    # Advanced stats
    limp_count: int = 0
    open_raise_count: int = 0
    three_bet_count: int = 0
    three_bet_opportunities: int = 0
    fold_to_3bet_count: int = 0
    fold_to_3bet_opportunities: int = 0
    cold_call_count: int = 0
    
    # Position tracking
    hands_by_position: dict[int, int] = field(default_factory=dict)
    vpip_by_position: dict[int, int] = field(default_factory=dict)
    pfr_by_position: dict[int, int] = field(default_factory=dict)
    
    # Sizing
    open_raise_sizes: list[float] = field(default_factory=list)
    three_bet_sizes: list[float] = field(default_factory=list)
    
    @property
    def vpip(self) -> float:
        """VPIP percentage (0.0 to 1.0)."""
        if self.hands_played == 0:
            return 0.0
        return self.vpip_count / self.hands_played
    
    @property
    def pfr(self) -> float:
        """PFR percentage (0.0 to 1.0)."""
        if self.hands_played == 0:
            return 0.0
        return self.pfr_count / self.hands_played
    
    @property
    def vpip_pfr_gap(self) -> float:
        """
        Gap between VPIP and PFR.
        
        High gap indicates passive/calling tendency.
        Low gap indicates tight-aggressive style.
        """
        return self.vpip - self.pfr
    
    @property
    def limp_rate(self) -> float:
        """Percentage of hands limped preflop."""
        if self.hands_played == 0:
            return 0.0
        return self.limp_count / self.hands_played
    
    @property
    def three_bet_frequency(self) -> float:
        """3-bet percentage when given the opportunity."""
        if self.three_bet_opportunities == 0:
            return 0.0
        return self.three_bet_count / self.three_bet_opportunities
    
    @property
    def fold_to_3bet(self) -> float:
        """Fold to 3-bet percentage."""
        if self.fold_to_3bet_opportunities == 0:
            return 0.0
        return self.fold_to_3bet_count / self.fold_to_3bet_opportunities
    
    @property
    def avg_open_raise_size(self) -> float:
        """Average open raise size in big blinds."""
        if not self.open_raise_sizes:
            return 0.0
        return sum(self.open_raise_sizes) / len(self.open_raise_sizes)
    
    def vpip_at_position(self, position: int) -> float:
        """VPIP at a specific position."""
        hands = self.hands_by_position.get(position, 0)
        vpip = self.vpip_by_position.get(position, 0)
        if hands == 0:
            return 0.0
        return vpip / hands
    
    def pfr_at_position(self, position: int) -> float:
        """PFR at a specific position."""
        hands = self.hands_by_position.get(position, 0)
        pfr = self.pfr_by_position.get(position, 0)
        if hands == 0:
            return 0.0
        return pfr / hands


class PreflopAnalyzer:
    """
    Analyzes preflop actions to compute player statistics.
    
    Usage:
        analyzer = PreflopAnalyzer()
        stats = analyzer.analyze(hands, player_id)
    """
    
    def analyze(
        self, 
        hands: list[ParsedHand], 
        player_id: str,
        min_bb: int = 0
    ) -> PreflopStats:
        """
        Compute preflop statistics for a player across multiple hands.
        
        Args:
            hands: List of parsed hands to analyze
            player_id: ID of the player to analyze
            min_bb: Minimum big blind filter (0 = all hands)
            
        Returns:
            PreflopStats object with computed statistics
        """
        stats = PreflopStats()
        
        for hand in hands:
            # Skip if player not in hand
            player = hand.get_player_by_id(player_id)
            if not player:
                continue
            
            # Optional BB filter
            if min_bb > 0 and hand.big_blind < min_bb:
                continue
            
            # Get preflop actions only
            preflop_actions = hand.get_actions_on_street(Street.PREFLOP)
            player_actions = [a for a in preflop_actions if a.player_id == player_id]
            
            if not player_actions:
                # Player was in hand but took no preflop action (unusual)
                continue
            
            # Track this hand
            stats.hands_played += 1
            
            # Track position
            if player.position is not None:
                pos = player.position
                stats.hands_by_position[pos] = stats.hands_by_position.get(pos, 0) + 1
            
            # Analyze actions
            self._analyze_hand_preflop(
                stats, player_actions, preflop_actions, 
                player_id, player.position, hand.big_blind
            )
        
        return stats
    
    def _analyze_hand_preflop(
        self,
        stats: PreflopStats,
        player_actions: list[PlayerAction],
        all_preflop_actions: list[PlayerAction],
        player_id: str,
        position: Optional[int],
        big_blind: int
    ):
        """Analyze a single hand's preflop actions."""
        
        voluntarily_invested = False
        raised_preflop = False
        limped = False
        three_betted = False
        
        # Track raise count before our first action
        raises_before_us = 0
        our_first_action_seen = False
        our_raise_count = 0
        
        for action in all_preflop_actions:
            is_our_action = action.player_id == player_id
            
            # Skip forced blinds for analysis
            if action.action_type in (ActionType.SMALL_BLIND, ActionType.BIG_BLIND):
                continue
            
            if not our_first_action_seen and not is_our_action:
                if action.action_type == ActionType.BET_RAISE:
                    raises_before_us += 1
            
            if is_our_action:
                our_first_action_seen = True
                
                if action.action_type == ActionType.BET_RAISE:
                    voluntarily_invested = True
                    raised_preflop = True
                    our_raise_count += 1
                    
                    # Determine if this is a limp, open, or 3-bet
                    if raises_before_us == 0:
                        # This is an open raise
                        stats.open_raise_count += 1
                        if big_blind > 0:
                            size_in_bb = action.amount / big_blind
                            stats.open_raise_sizes.append(size_in_bb)
                    elif raises_before_us == 1 and our_raise_count == 1:
                        # This is a 3-bet (re-raise of first raiser)
                        three_betted = True
                        stats.three_bet_count += 1
                        if big_blind > 0:
                            size_in_bb = action.amount / big_blind
                            stats.three_bet_sizes.append(size_in_bb)
                
                elif action.action_type == ActionType.CALL:
                    voluntarily_invested = True
                    
                    if raises_before_us == 0:
                        # Calling without a raise = limp
                        limped = True
                        stats.limp_count += 1
                    else:
                        # Cold call (calling a raise)
                        stats.cold_call_count += 1
        
        # Update main counts
        if voluntarily_invested:
            stats.vpip_count += 1
            if position is not None:
                stats.vpip_by_position[position] = \
                    stats.vpip_by_position.get(position, 0) + 1
        
        if raised_preflop:
            stats.pfr_count += 1
            if position is not None:
                stats.pfr_by_position[position] = \
                    stats.pfr_by_position.get(position, 0) + 1
        
        # Track 3-bet opportunities
        # (facing a raise without anyone already 3-betting)
        if raises_before_us == 1:
            stats.three_bet_opportunities += 1
        
        # Track fold to 3-bet
        # (we raised, someone 3-bet, we folded)
        if our_raise_count > 0:
            faced_3bet = False
            folded_to_3bet = False
            
            raises_after_our_first = 0
            past_our_raise = False
            
            for action in all_preflop_actions:
                if action.action_type in (ActionType.SMALL_BLIND, ActionType.BIG_BLIND):
                    continue
                    
                if action.player_id == player_id and action.action_type == ActionType.BET_RAISE:
                    past_our_raise = True
                    continue
                
                if past_our_raise and action.player_id != player_id:
                    if action.action_type == ActionType.BET_RAISE:
                        faced_3bet = True
                        break
            
            if faced_3bet:
                stats.fold_to_3bet_opportunities += 1
                
                # Check if we folded after
                for action in all_preflop_actions:
                    if action.player_id == player_id and action.action_type == ActionType.FOLD:
                        stats.fold_to_3bet_count += 1
                        break


def calculate_preflop_stats(
    hands: list[ParsedHand], 
    player_id: str
) -> PreflopStats:
    """
    Convenience function to calculate preflop stats.
    
    Args:
        hands: List of parsed hands
        player_id: Player to analyze
        
    Returns:
        PreflopStats object
    """
    analyzer = PreflopAnalyzer()
    return analyzer.analyze(hands, player_id)
