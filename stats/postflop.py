"""
Postflop statistics calculation.

Computes key postflop metrics that reveal player tendencies:
- C-bet frequency (continuation bet)
- Aggression Factor and Frequency
- Bet sizing patterns by street
- Fold to bet percentages
- Barreling tendencies
"""

from dataclasses import dataclass, field
from typing import Optional

from models import ActionType, Street, ParsedHand, PlayerAction


@dataclass
class StreetStats:
    """Statistics for a single street (flop/turn/river)."""
    
    # Opportunity and action counts
    opportunities: int = 0  # Times player saw this street
    bets: int = 0
    raises: int = 0
    calls: int = 0
    checks: int = 0
    folds: int = 0
    
    # C-bet tracking
    cbet_opportunities: int = 0  # Was aggressor preflop and first to act
    cbets_made: int = 0
    
    # Facing bets
    faced_bet_count: int = 0
    fold_to_bet_count: int = 0
    
    # Bet sizing (as ratio of pot)
    bet_sizes: list[float] = field(default_factory=list)
    
    @property
    def aggression_actions(self) -> int:
        """Total aggressive actions (bets + raises)."""
        return self.bets + self.raises
    
    @property
    def passive_actions(self) -> int:
        """Total passive actions (calls + checks)."""
        return self.calls + self.checks
    
    @property
    def aggression_factor(self) -> float:
        """
        Aggression Factor = (bets + raises) / calls
        
        Higher = more aggressive
        1.0 = balanced
        < 1.0 = passive
        """
        if self.calls == 0:
            return float('inf') if self.aggression_actions > 0 else 0.0
        return self.aggression_actions / self.calls
    
    @property
    def aggression_frequency(self) -> float:
        """
        Aggression Frequency = (bets + raises) / total actions
        
        More reliable than AF for small samples.
        """
        total = self.bets + self.raises + self.calls + self.checks
        if total == 0:
            return 0.0
        return self.aggression_actions / total
    
    @property
    def cbet_frequency(self) -> float:
        """C-bet percentage when given opportunity."""
        if self.cbet_opportunities == 0:
            return 0.0
        return self.cbets_made / self.cbet_opportunities
    
    @property
    def fold_to_bet(self) -> float:
        """Fold to bet percentage."""
        if self.faced_bet_count == 0:
            return 0.0
        return self.fold_to_bet_count / self.faced_bet_count
    
    @property
    def avg_bet_size(self) -> float:
        """Average bet size as pot ratio."""
        if not self.bet_sizes:
            return 0.0
        return sum(self.bet_sizes) / len(self.bet_sizes)
    
    @property
    def min_bet_size(self) -> float:
        """Minimum bet size."""
        return min(self.bet_sizes) if self.bet_sizes else 0.0
    
    @property
    def max_bet_size(self) -> float:
        """Maximum bet size."""
        return max(self.bet_sizes) if self.bet_sizes else 0.0


@dataclass
class PostflopStats:
    """
    Postflop statistics for a player across all streets.
    """
    flop: StreetStats = field(default_factory=StreetStats)
    turn: StreetStats = field(default_factory=StreetStats)
    river: StreetStats = field(default_factory=StreetStats)
    
    # Cross-street patterns
    double_barrel_opportunities: int = 0
    double_barrels: int = 0
    triple_barrel_opportunities: int = 0
    triple_barrels: int = 0
    
    # Check-raise tracking
    check_raise_opportunities: int = 0
    check_raises: int = 0
    
    # Delayed c-bet (check flop, bet turn)
    delayed_cbet_opportunities: int = 0
    delayed_cbets: int = 0
    
    # Overbet tracking (> 100% pot)
    overbet_count: int = 0
    total_bets: int = 0
    
    @property
    def total_aggression_factor(self) -> float:
        """Overall postflop aggression factor."""
        total_aggressive = (
            self.flop.aggression_actions + 
            self.turn.aggression_actions + 
            self.river.aggression_actions
        )
        total_calls = self.flop.calls + self.turn.calls + self.river.calls
        
        if total_calls == 0:
            return float('inf') if total_aggressive > 0 else 0.0
        return total_aggressive / total_calls
    
    @property
    def total_aggression_frequency(self) -> float:
        """Overall postflop aggression frequency."""
        total_aggressive = (
            self.flop.aggression_actions + 
            self.turn.aggression_actions + 
            self.river.aggression_actions
        )
        total_passive = (
            self.flop.passive_actions + 
            self.turn.passive_actions + 
            self.river.passive_actions
        )
        total = total_aggressive + total_passive
        
        if total == 0:
            return 0.0
        return total_aggressive / total
    
    @property
    def double_barrel_frequency(self) -> float:
        """Double barrel percentage."""
        if self.double_barrel_opportunities == 0:
            return 0.0
        return self.double_barrels / self.double_barrel_opportunities
    
    @property
    def triple_barrel_frequency(self) -> float:
        """Triple barrel percentage."""
        if self.triple_barrel_opportunities == 0:
            return 0.0
        return self.triple_barrels / self.triple_barrel_opportunities
    
    @property
    def check_raise_frequency(self) -> float:
        """Check-raise percentage."""
        if self.check_raise_opportunities == 0:
            return 0.0
        return self.check_raises / self.check_raise_opportunities
    
    @property
    def overbet_frequency(self) -> float:
        """Percentage of bets that are overbets."""
        if self.total_bets == 0:
            return 0.0
        return self.overbet_count / self.total_bets


class PostflopAnalyzer:
    """
    Analyzes postflop actions to compute player statistics.
    """
    
    def analyze(
        self, 
        hands: list[ParsedHand], 
        player_id: str
    ) -> PostflopStats:
        """
        Compute postflop statistics for a player.
        
        Args:
            hands: List of parsed hands to analyze
            player_id: ID of the player to analyze
            
        Returns:
            PostflopStats object with computed statistics
        """
        stats = PostflopStats()
        
        for hand in hands:
            # Skip if player not in hand
            if not hand.get_player_by_id(player_id):
                continue
            
            # Determine if player was preflop aggressor
            preflop_aggressor = self._get_preflop_aggressor(hand)
            is_aggressor = preflop_aggressor == player_id
            
            # Analyze each street
            for street in [Street.FLOP, Street.TURN, Street.RIVER]:
                street_actions = hand.get_actions_on_street(street)
                
                if not street_actions:
                    continue
                
                # Check if player saw this street (didn't fold earlier)
                if self._player_folded_before(hand, player_id, street):
                    continue
                
                street_stats = self._get_street_stats(stats, street)
                street_stats.opportunities += 1
                
                self._analyze_street(
                    stats, street_stats, street_actions,
                    player_id, is_aggressor, street, hand
                )
            
            # Analyze multi-street patterns
            self._analyze_barreling(stats, hand, player_id)
            self._analyze_check_raises(stats, hand, player_id)
        
        return stats
    
    def _get_street_stats(self, stats: PostflopStats, street: Street) -> StreetStats:
        """Get the StreetStats object for a given street."""
        if street == Street.FLOP:
            return stats.flop
        elif street == Street.TURN:
            return stats.turn
        elif street == Street.RIVER:
            return stats.river
        raise ValueError(f"Invalid street: {street}")
    
    def _get_preflop_aggressor(self, hand: ParsedHand) -> Optional[str]:
        """
        Identify the preflop aggressor (last raiser).
        
        Returns player_id of aggressor, or None if no raises.
        """
        preflop_actions = hand.get_actions_on_street(Street.PREFLOP)
        aggressor = None
        
        for action in preflop_actions:
            if action.action_type == ActionType.BET_RAISE:
                aggressor = action.player_id
        
        return aggressor
    
    def _player_folded_before(
        self, 
        hand: ParsedHand, 
        player_id: str, 
        current_street: Street
    ) -> bool:
        """Check if player folded before the given street."""
        street_order = [Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER]
        current_idx = street_order.index(current_street)
        
        for i in range(current_idx):
            street = street_order[i]
            for action in hand.get_actions_on_street(street):
                if action.player_id == player_id and action.action_type == ActionType.FOLD:
                    return True
        return False
    
    def _analyze_street(
        self,
        stats: PostflopStats,
        street_stats: StreetStats,
        actions: list[PlayerAction],
        player_id: str,
        is_aggressor: bool,
        street: Street,
        hand: ParsedHand
    ):
        """Analyze actions on a single street."""
        
        # Track if player has acted and what they did first
        player_first_action = None
        faced_bet_before_acting = False
        first_to_act = True
        
        for action in actions:
            # Track if anyone bet before our first action
            if action.player_id != player_id:
                if action.action_type in (ActionType.BET_RAISE,):
                    if player_first_action is None:
                        faced_bet_before_acting = True
                    first_to_act = False
                elif action.action_type == ActionType.CHECK:
                    first_to_act = False
                continue
            
            # This is our action
            if player_first_action is None:
                player_first_action = action
            
            # Count action types
            if action.action_type == ActionType.BET_RAISE:
                if action.pot_before > 0:
                    # Check if it's a bet or raise
                    if self._is_first_bet_of_street(actions, action):
                        street_stats.bets += 1
                    else:
                        street_stats.raises += 1
                else:
                    street_stats.bets += 1
                
                # Track bet sizing
                if action.pot_before > 0 and action.amount > 0:
                    ratio = action.amount / action.pot_before
                    street_stats.bet_sizes.append(ratio)
                    stats.total_bets += 1
                    
                    if ratio > 1.0:
                        stats.overbet_count += 1
                
            elif action.action_type == ActionType.CALL:
                street_stats.calls += 1
                
            elif action.action_type == ActionType.CHECK:
                street_stats.checks += 1
                
            elif action.action_type == ActionType.FOLD:
                street_stats.folds += 1
        
        # C-bet tracking
        if is_aggressor and first_to_act and player_first_action:
            street_stats.cbet_opportunities += 1
            if player_first_action.action_type == ActionType.BET_RAISE:
                street_stats.cbets_made += 1
        
        # Fold to bet tracking
        if faced_bet_before_acting and player_first_action:
            street_stats.faced_bet_count += 1
            if player_first_action.action_type == ActionType.FOLD:
                street_stats.fold_to_bet_count += 1
    
    def _is_first_bet_of_street(
        self, 
        actions: list[PlayerAction], 
        current: PlayerAction
    ) -> bool:
        """Check if this is the first bet on this street."""
        for action in actions:
            if action is current:
                return True
            if action.action_type == ActionType.BET_RAISE:
                return False
        return True
    
    def _analyze_barreling(
        self, 
        stats: PostflopStats, 
        hand: ParsedHand, 
        player_id: str
    ):
        """Analyze double and triple barrel patterns."""
        
        flop_actions = hand.get_actions_on_street(Street.FLOP)
        turn_actions = hand.get_actions_on_street(Street.TURN)
        river_actions = hand.get_actions_on_street(Street.RIVER)
        
        # Check if player c-bet flop
        cbet_flop = any(
            a.player_id == player_id and a.action_type == ActionType.BET_RAISE
            for a in flop_actions
        )
        
        if not cbet_flop:
            return
        
        # Double barrel opportunity
        if turn_actions:
            player_saw_turn = not self._player_folded_before(
                hand, player_id, Street.TURN
            )
            if player_saw_turn:
                stats.double_barrel_opportunities += 1
                
                bet_turn = any(
                    a.player_id == player_id and a.action_type == ActionType.BET_RAISE
                    for a in turn_actions
                )
                
                if bet_turn:
                    stats.double_barrels += 1
                    
                    # Triple barrel opportunity
                    if river_actions:
                        player_saw_river = not self._player_folded_before(
                            hand, player_id, Street.RIVER
                        )
                        if player_saw_river:
                            stats.triple_barrel_opportunities += 1
                            
                            bet_river = any(
                                a.player_id == player_id and 
                                a.action_type == ActionType.BET_RAISE
                                for a in river_actions
                            )
                            
                            if bet_river:
                                stats.triple_barrels += 1
    
    def _analyze_check_raises(
        self, 
        stats: PostflopStats, 
        hand: ParsedHand, 
        player_id: str
    ):
        """Analyze check-raise patterns."""
        
        for street in [Street.FLOP, Street.TURN, Street.RIVER]:
            actions = hand.get_actions_on_street(street)
            
            player_checked_first = False
            opponent_bet_after = False
            player_raised_after = False
            
            check_seen = False
            
            for action in actions:
                if action.player_id == player_id:
                    if not check_seen and action.action_type == ActionType.CHECK:
                        player_checked_first = True
                        check_seen = True
                    elif (player_checked_first and opponent_bet_after and 
                          action.action_type == ActionType.BET_RAISE):
                        player_raised_after = True
                        break
                else:
                    if player_checked_first and action.action_type == ActionType.BET_RAISE:
                        opponent_bet_after = True
            
            if player_checked_first and opponent_bet_after:
                stats.check_raise_opportunities += 1
                if player_raised_after:
                    stats.check_raises += 1


def calculate_postflop_stats(
    hands: list[ParsedHand], 
    player_id: str
) -> PostflopStats:
    """
    Convenience function to calculate postflop stats.
    
    Args:
        hands: List of parsed hands
        player_id: Player to analyze
        
    Returns:
        PostflopStats object
    """
    analyzer = PostflopAnalyzer()
    return analyzer.analyze(hands, player_id)
