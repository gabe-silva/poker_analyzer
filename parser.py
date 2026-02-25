"""
Parser for poker hand history JSON files.

This module handles loading and parsing raw hand history data
into the structured format defined in models.py.

Expected JSON structure:
{
    "hands": [
        {
            "id": "hand_id",
            "dealerSeat": 1,
            "players": [
                {"id": "player_id", "seat": 1, "stack": 1000, "cards": ["Ah", "Kd"]},
                ...
            ],
            "events": [
                {"payload": {"type": 8, "seat": 1, "amount": 50}},
                ...
            ]
        },
        ...
    ]
}
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union

from models import (
    ActionType, Street, ParsedHand, PlayerAction, 
    PlayerInHand, HandResult, parse_hand_strength
)

logger = logging.getLogger(__name__)


class HandParser:
    """
    Parses raw JSON hand histories into structured ParsedHand objects.
    
    Handles the quirks and variations in hand history formats,
    tracking pot size and street transitions throughout each hand.
    """
    
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
    
    def load_file(self, file_path: Union[str, Path]) -> list[ParsedHand]:
        """
        Load and parse a hand history JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            List of ParsedHand objects
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            json.JSONDecodeError: If the file is not valid JSON
        """
        file_path = Path(file_path)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return self.parse_data(data)
    
    def load_json_string(self, json_str: str) -> list[ParsedHand]:
        """
        Parse hand history from a JSON string.
        
        Args:
            json_str: JSON string containing hand history
            
        Returns:
            List of ParsedHand objects
        """
        data = json.loads(json_str)
        return self.parse_data(data)
    
    def parse_data(self, data: dict) -> list[ParsedHand]:
        """
        Parse a hand history data structure.
        
        Args:
            data: Dictionary containing hand history data
            
        Returns:
            List of ParsedHand objects
        """
        self.errors = []
        self.warnings = []
        
        hands = []
        
        # Handle both {"hands": [...]} and direct list format
        raw_hands = data.get("hands", data) if isinstance(data, dict) else data
        
        if not isinstance(raw_hands, list):
            self.errors.append("Expected 'hands' to be a list")
            return hands
        
        for i, raw_hand in enumerate(raw_hands):
            try:
                parsed = self._parse_single_hand(raw_hand, index=i)
                if parsed:
                    hands.append(parsed)
            except Exception as e:
                self.errors.append(f"Error parsing hand {i}: {str(e)}")
                logger.exception(f"Failed to parse hand {i}")
        
        return hands
    
    def _parse_single_hand(self, raw_hand: dict, index: int = 0) -> Optional[ParsedHand]:
        """
        Parse a single hand from raw data.
        
        Args:
            raw_hand: Dictionary containing single hand data
            index: Hand index for error reporting
            
        Returns:
            ParsedHand object or None if parsing failed
        """
        # Extract basic hand info
        hand_id = str(raw_hand.get("id", f"hand_{index}"))
        dealer_seat = raw_hand.get("dealerSeat", 0)
        timestamp = raw_hand.get("timestamp")
        
        # Parse players
        players = self._parse_players(raw_hand.get("players", []), dealer_seat)
        if not players:
            self.warnings.append(f"Hand {hand_id}: No players found")
            return None
        
        # Create seat -> player mapping for quick lookups
        seat_to_player = {p.seat: p for p in players}
        
        # Parse events into actions
        events = raw_hand.get("events", [])
        actions, board, results, blinds = self._parse_events(
            events, seat_to_player, hand_id
        )
        
        return ParsedHand(
            hand_id=hand_id,
            players=players,
            actions=actions,
            board=board,
            dealer_seat=dealer_seat,
            small_blind=blinds.get("sb", 0),
            big_blind=blinds.get("bb", 0),
            results=results,
            timestamp=timestamp
        )
    
    def _parse_players(
        self, 
        raw_players: list, 
        dealer_seat: int
    ) -> list[PlayerInHand]:
        """Parse player list from raw data."""
        players = []
        
        for raw_player in raw_players:
            player_id = raw_player.get("id", raw_player.get("playerId", ""))
            seat = raw_player.get("seat", 0)
            stack = raw_player.get("stack", raw_player.get("chips", 0))
            
            # Parse hole cards if available
            hole_cards = None
            cards_data = raw_player.get("cards", raw_player.get("holeCards"))
            if cards_data:
                if isinstance(cards_data, list):
                    hole_cards = [self._normalize_card(c) for c in cards_data]
                elif isinstance(cards_data, str):
                    hole_cards = [self._normalize_card(c) for c in cards_data.split()]
            
            players.append(PlayerInHand(
                player_id=str(player_id),
                seat=seat,
                stack=stack,
                hole_cards=hole_cards,
                is_dealer=(seat == dealer_seat)
            ))
        
        # Calculate positions based on dealer
        self._assign_positions(players, dealer_seat)
        
        return players
    
    def _assign_positions(self, players: list[PlayerInHand], dealer_seat: int):
        """Assign position numbers to players relative to dealer."""
        if not players:
            return
            
        # Sort by seat
        seats = sorted(p.seat for p in players)
        
        # Find dealer index
        dealer_idx = 0
        for i, seat in enumerate(seats):
            if seat == dealer_seat:
                dealer_idx = i
                break
        
        # Assign positions (0=dealer, 1=SB, 2=BB, etc.)
        n = len(seats)
        for player in players:
            seat_idx = seats.index(player.seat)
            position = (seat_idx - dealer_idx) % n
            player.position = position
    
    def _parse_events(
        self,
        events: list,
        seat_to_player: dict[int, PlayerInHand],
        hand_id: str
    ) -> tuple[list[PlayerAction], list[str], dict[str, HandResult], dict]:
        """
        Parse event list into actions, board cards, and results.
        
        Tracks:
        - Current street
        - Running pot size
        - Player stacks
        
        Returns:
            Tuple of (actions, board, results, blinds)
        """
        actions = []
        board = []
        results = {}
        blinds = {"sb": 0, "bb": 0}
        
        current_street = Street.PREFLOP
        pot = 0
        
        # Track stacks for each seat
        stacks = {seat: player.stack for seat, player in seat_to_player.items()}
        
        for event in events:
            payload = event.get("payload", event)
            
            # Some formats nest differently
            if isinstance(payload, dict):
                action_type_raw = payload.get("type")
                seat = payload.get("seat")
                # Try both "amount" and "value" field names
                amount = payload.get("amount") or payload.get("value", 0)
            else:
                continue
            
            if action_type_raw is None:
                continue
            
            # Convert to ActionType enum
            try:
                action_type = ActionType(action_type_raw)
            except ValueError:
                # Unknown action type, skip
                self.warnings.append(
                    f"Hand {hand_id}: Unknown action type {action_type_raw}"
                )
                continue
            
            # Handle street transitions (board dealt)
            if action_type == ActionType.BOARD_DEALT:
                board_cards = payload.get("cards", [])
                if board_cards:
                    board.extend([self._normalize_card(c) for c in board_cards])
                
                # Advance street
                if current_street == Street.PREFLOP:
                    current_street = Street.FLOP
                elif current_street == Street.FLOP:
                    current_street = Street.TURN
                elif current_street == Street.TURN:
                    current_street = Street.RIVER
                continue
            
            # Handle pot awarded (showdown/hand end)
            if action_type == ActionType.POT_AWARDED:
                winner_seat = seat
                win_amount = amount
                
                if winner_seat in seat_to_player:
                    player = seat_to_player[winner_seat]
                    
                    # Extract showdown info if available
                    hand_desc = payload.get("handDescription", payload.get("hand"))
                    hand_strength = parse_hand_strength(hand_desc) if hand_desc else None
                    shown_cards = payload.get("cards", payload.get("holeCards"))
                    
                    if shown_cards:
                        shown_cards = [self._normalize_card(c) for c in shown_cards]
                    
                    results[player.player_id] = HandResult(
                        player_id=player.player_id,
                        reached_showdown=True,
                        won_pot=True,
                        amount_won=win_amount,
                        hand_strength=hand_strength,
                        hand_description=hand_desc,
                        hole_cards=shown_cards
                    )
                continue
            
            # Skip if no seat (shouldn't happen for player actions)
            if seat is None:
                continue
            
            # Get player for this seat
            player = seat_to_player.get(seat)
            if not player:
                continue
            
            # Track blinds
            if action_type == ActionType.SMALL_BLIND:
                blinds["sb"] = amount
            elif action_type == ActionType.BIG_BLIND:
                blinds["bb"] = amount
            
            # Calculate pot before action
            pot_before = pot
            
            # Check for all-in
            is_all_in = False
            if amount > 0 and seat in stacks:
                is_all_in = amount >= stacks[seat]
            
            stack_before = stacks.get(seat, 0)
            
            # Create action record
            action = PlayerAction(
                player_id=player.player_id,
                seat=seat,
                action_type=action_type,
                street=current_street,
                amount=amount,
                pot_before=pot_before,
                is_all_in=is_all_in,
                stack_before=stack_before
            )
            actions.append(action)
            
            # Update pot and stacks
            if amount > 0:
                pot += amount
                if seat in stacks:
                    stacks[seat] = max(0, stacks[seat] - amount)
        
        # Mark showdown for players who didn't fold and hand reached showdown
        if results:  # If anyone won, we had a showdown
            folded_players = {
                a.player_id for a in actions 
                if a.action_type == ActionType.FOLD
            }
            for player in seat_to_player.values():
                if player.player_id not in results and player.player_id not in folded_players:
                    # Player was in at showdown but didn't win
                    results[player.player_id] = HandResult(
                        player_id=player.player_id,
                        reached_showdown=True,
                        won_pot=False,
                        amount_won=0
                    )
        
        return actions, board, results, blinds
    
    def _normalize_card(self, card: Union[str, dict]) -> str:
        """
        Normalize card representation to standard format (e.g., "Ah").
        
        Handles various input formats:
        - String: "Ah", "AH", "ah", "A♥"
        - Dict: {"rank": "A", "suit": "h"}
        """
        if isinstance(card, dict):
            rank = card.get("rank", card.get("r", "?"))
            suit = card.get("suit", card.get("s", "?"))
            card = f"{rank}{suit}"
        
        if not isinstance(card, str) or len(card) < 2:
            return "??"
        
        # Normalize rank
        rank = card[0].upper()
        
        # Normalize suit
        suit_char = card[-1].lower()
        suit_map = {
            '♠': 's', '♥': 'h', '♦': 'd', '♣': 'c',
            'spades': 's', 'hearts': 'h', 'diamonds': 'd', 'clubs': 'c'
        }
        suit = suit_map.get(suit_char, suit_char)
        
        return f"{rank}{suit}"


def load_hands(file_path: Union[str, Path]) -> list[ParsedHand]:
    """
    Convenience function to load hands from a file.
    
    Args:
        file_path: Path to JSON hand history file
        
    Returns:
        List of ParsedHand objects
    """
    parser = HandParser()
    hands = parser.load_file(file_path)
    
    if parser.errors:
        logger.warning(f"Parsing errors: {parser.errors}")
    
    return hands
