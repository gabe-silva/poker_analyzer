"""
Core data models for poker hand analysis.

This module defines the fundamental data structures used throughout
the poker analyzer, including enums for action types and streets,
and dataclasses for representing hands, actions, and player states.
"""

from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Optional


class ActionType(IntEnum):
    """
    Poker action types as encoded in the hand history JSON.
    
    These values are derived from the observed patterns in the data:
    - type: 0 → check
    - type: 2 → big blind (forced)
    - type: 3 → small blind (forced)
    - type: 7 → call
    - type: 8 → bet / raise
    - type: 9 → board dealt (street transition)
    - type: 10 → pot awarded
    - type: 11 → fold
    """
    CHECK = 0
    BIG_BLIND = 2
    SMALL_BLIND = 3
    CALL = 7
    BET_RAISE = 8
    BOARD_DEALT = 9
    POT_AWARDED = 10
    FOLD = 11


class Street(Enum):
    """Poker streets/betting rounds."""
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


class HandStrength(IntEnum):
    """
    Numeric hand strength buckets for analysis.
    
    Higher values = stronger hands.
    Used for correlating bet sizes with hand strength.
    """
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


# Mapping from common hand description strings to HandStrength
HAND_DESCRIPTION_MAP = {
    "high card": HandStrength.HIGH_CARD,
    "highcard": HandStrength.HIGH_CARD,
    "pair": HandStrength.PAIR,
    "one pair": HandStrength.PAIR,
    "two pair": HandStrength.TWO_PAIR,
    "twopair": HandStrength.TWO_PAIR,
    "three of a kind": HandStrength.THREE_OF_A_KIND,
    "trips": HandStrength.THREE_OF_A_KIND,
    "set": HandStrength.THREE_OF_A_KIND,
    "straight": HandStrength.STRAIGHT,
    "flush": HandStrength.FLUSH,
    "full house": HandStrength.FULL_HOUSE,
    "fullhouse": HandStrength.FULL_HOUSE,
    "boat": HandStrength.FULL_HOUSE,
    "four of a kind": HandStrength.FOUR_OF_A_KIND,
    "quads": HandStrength.FOUR_OF_A_KIND,
    "straight flush": HandStrength.STRAIGHT_FLUSH,
    "royal flush": HandStrength.ROYAL_FLUSH,
}


def parse_hand_strength(description: str) -> Optional[HandStrength]:
    """
    Convert a hand description string to a HandStrength enum.
    
    Args:
        description: Natural language hand description (e.g., "Two Pair")
        
    Returns:
        HandStrength enum value, or None if unrecognized
    """
    if not description:
        return None
    normalized = description.lower().strip()
    return HAND_DESCRIPTION_MAP.get(normalized)


@dataclass
class PlayerAction:
    """
    Represents a single action taken by a player.
    
    Attributes:
        player_id: Unique identifier for the player
        seat: Table seat number
        action_type: Type of action (bet, call, fold, etc.)
        street: Which betting round this occurred on
        amount: Bet/raise amount (0 for checks/folds)
        pot_before: Pot size before this action
        is_all_in: Whether this action put the player all-in
        stack_before: Player's stack before this action
    """
    player_id: str
    seat: int
    action_type: ActionType
    street: Street
    amount: int = 0
    pot_before: int = 0
    is_all_in: bool = False
    stack_before: int = 0
    
    @property
    def is_voluntary(self) -> bool:
        """Returns True if this action voluntarily put money in the pot."""
        return self.action_type in (ActionType.BET_RAISE, ActionType.CALL)
    
    @property
    def is_aggressive(self) -> bool:
        """Returns True if this is an aggressive action (bet or raise)."""
        return self.action_type == ActionType.BET_RAISE
    
    @property
    def pot_ratio(self) -> float:
        """Returns the bet amount as a ratio of the pot."""
        if self.pot_before <= 0:
            return 0.0
        return self.amount / self.pot_before


@dataclass
class PlayerInHand:
    """
    Represents a player's participation in a single hand.
    
    Attributes:
        player_id: Unique identifier
        seat: Table seat number
        stack: Starting stack for this hand
        hole_cards: Player's hole cards if known (e.g., ["Ah", "Kd"])
        position: Position relative to dealer (0=dealer, 1=SB, 2=BB, etc.)
        is_dealer: Whether this player is the dealer
    """
    player_id: str
    seat: int
    stack: int
    hole_cards: Optional[list[str]] = None
    position: Optional[int] = None
    is_dealer: bool = False


@dataclass 
class HandResult:
    """
    Represents the outcome of a hand for a specific player.
    
    Attributes:
        player_id: Unique identifier
        reached_showdown: Whether player went to showdown
        won_pot: Whether player won (any part of) the pot
        amount_won: Total amount won
        hand_strength: Numeric hand strength at showdown
        hand_description: Text description of final hand
        hole_cards: Revealed hole cards
    """
    player_id: str
    reached_showdown: bool = False
    won_pot: bool = False
    amount_won: int = 0
    hand_strength: Optional[HandStrength] = None
    hand_description: Optional[str] = None
    hole_cards: Optional[list[str]] = None


@dataclass
class ParsedHand:
    """
    A fully parsed poker hand with all relevant information.
    
    Attributes:
        hand_id: Unique hand identifier
        players: List of players in the hand
        actions: Chronological list of all actions
        board: Community cards (up to 5)
        dealer_seat: Seat number of the dealer
        small_blind: Small blind amount
        big_blind: Big blind amount
        results: Outcome for each player
        timestamp: When the hand occurred (if available)
    """
    hand_id: str
    players: list[PlayerInHand]
    actions: list[PlayerAction]
    board: list[str] = field(default_factory=list)
    dealer_seat: int = 0
    small_blind: int = 0
    big_blind: int = 0
    results: dict[str, HandResult] = field(default_factory=dict)
    timestamp: Optional[str] = None
    
    def get_player_by_id(self, player_id: str) -> Optional[PlayerInHand]:
        """Find a player by their ID."""
        for player in self.players:
            if player.player_id == player_id:
                return player
        return None
    
    def get_player_by_seat(self, seat: int) -> Optional[PlayerInHand]:
        """Find a player by their seat number."""
        for player in self.players:
            if player.seat == seat:
                return player
        return None
    
    def get_actions_for_player(self, player_id: str) -> list[PlayerAction]:
        """Get all actions taken by a specific player."""
        return [a for a in self.actions if a.player_id == player_id]
    
    def get_actions_on_street(self, street: Street) -> list[PlayerAction]:
        """Get all actions on a specific street."""
        return [a for a in self.actions if a.street == street]
    
    def player_reached_showdown(self, player_id: str) -> bool:
        """Check if a player reached showdown."""
        if player_id in self.results:
            return self.results[player_id].reached_showdown
        return False
    
    def player_won(self, player_id: str) -> bool:
        """Check if a player won the pot."""
        if player_id in self.results:
            return self.results[player_id].won_pot
        return False
