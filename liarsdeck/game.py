import random
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class LiarsDeckGame:
    """
    Core game engine for Liar's Deck with structured event emission.
    This class is intentionally model-agnostic and can be wrapped by gym-like envs.
    """

    def __init__(
        self,
        num_players: int = 4,
        seed: Optional[int] = None,
        ruleset: str = "basic",
        env_version: str = "v0.1",
    ):
        if num_players < 2:
            raise ValueError("num_players must be >= 2")

        self.num_players = num_players
        self.ruleset = ruleset
        self.env_version = env_version
        self.seed = seed
        self.rng = random.Random(seed)

        self.base_deck = ["K"] * 6 + ["Q"] * 6 + ["A"] * 6 + ["Joker"] * 2
        self.table_ranks = ["K", "Q", "A"]

        self.game_id: str = ""
        self.players: Dict[int, Dict[str, Any]] = {}
        self.events: List[Dict[str, Any]] = []
        self.event_id: int = 0
        self.turn_index: int = 0
        self.round: int = 0
        self.current_turn: int = 1
        self.table_rank: str = "K"
        self.pile_size: int = 0
        self.last_play: Optional[Dict[str, Any]] = None
        self.game_over: bool = False
        self.winner: Optional[int] = None
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None

    def reset(self, game_id: Optional[str] = None) -> Dict[str, Any]:
        self.game_id = game_id or f"ld_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.events = []
        self.event_id = 0
        self.turn_index = 0
        self.round = 0
        self.game_over = False
        self.winner = None
        self.start_time = self._utc_now()
        self.end_time = None

        self.players = {}
        for player_id in range(1, self.num_players + 1):
            revolver = [False] * 5 + [True]
            self.rng.shuffle(revolver)
            self.players[player_id] = {
                "hand": [],
                "revolver": revolver,
                "is_alive": True,
            }

        self.current_turn = 1
        self._emit(
            phase="setup",
            event="game_setting",
            source=-1,
            target=-1,
            visibility="public",
            content={
                "num_players": self.num_players,
                "ruleset": self.ruleset,
                "deck_spec": {"K": 6, "Q": 6, "A": 6, "Joker": 2},
            },
            outcome={},
        )

        self._emit(
            phase="setup",
            event="god_view",
            source=-1,
            target=-1,
            visibility="omniscient",
            content={
                str(player_id): {
                    "initial_revolver": ["bang" if chamber else "click" for chamber in p["revolver"]]
                }
                for player_id, p in self.players.items()
            },
            outcome={},
        )

        self._start_new_round(starter=1)
        return self.get_public_state()

    def _start_new_round(self, starter: int) -> None:
        self.round += 1
        deck = deepcopy(self.base_deck)
        self.rng.shuffle(deck)

        for player_id, player in self.players.items():
            if player["is_alive"]:
                player["hand"] = [deck.pop() for _ in range(5)]
            else:
                player["hand"] = []

        self.table_rank = self.rng.choice(self.table_ranks)
        self.pile_size = 0
        self.last_play = None
        self.current_turn = starter
        if not self.players[self.current_turn]["is_alive"]:
            self.current_turn = self._next_alive_player(self.current_turn)

        self._emit(
            phase=f"r{self.round}_start",
            event="round_start",
            source=-1,
            target=-1,
            visibility="public",
            content={
                "starter": self.current_turn,
                "table_rank": self.table_rank,
                "alive_players": self.get_alive_players(),
            },
            outcome={},
        )

        self._emit(
            phase=f"r{self.round}_start",
            event="round_start",
            source=-1,
            target=-1,
            visibility="omniscient",
            content={
                "hands": {str(player_id): deepcopy(self.players[player_id]["hand"]) for player_id in self.players}
            },
            outcome={},
        )

    def get_alive_players(self) -> List[int]:
        return [player_id for player_id, player in self.players.items() if player["is_alive"]]

    def _next_alive_player(self, current: int) -> int:
        player_id = current
        for _ in range(self.num_players):
            player_id = (player_id % self.num_players) + 1
            if self.players[player_id]["is_alive"]:
                return player_id
        raise RuntimeError("No alive players available")

    def add_speech(self, player_id: int, text: str) -> None:
        if not text:
            return
        self._emit(
            phase=f"r{self.round}_turn{self.turn_index}_speech",
            event="speech",
            source=player_id,
            target=-1,
            visibility="public",
            content={"speech_content": text},
            outcome={},
        )

    def get_valid_actions(self, player_id: int) -> List[Dict[str, Any]]:
        if self.game_over:
            return []
        if player_id != self.current_turn:
            return []

        actions = [{"type": "play"}]
        if self.last_play is not None:
            actions.append({"type": "call_liar"})
        return actions

    def step(self, player_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        if self.game_over:
            raise ValueError("Game already ended")
        if player_id != self.current_turn:
            raise ValueError(f"Not player {player_id}'s turn")
        if not self.players[player_id]["is_alive"]:
            raise ValueError(f"Player {player_id} is eliminated")

        action_type = action.get("type")
        if action_type == "speech":
            self.add_speech(player_id, action.get("text", ""))
            return self.get_public_state()

        if action_type == "play":
            cards_played = action.get("cards", [])
            if not isinstance(cards_played, list) or len(cards_played) == 0 or len(cards_played) > 3:
                raise ValueError("play.cards must be a list of length 1..3")

            current_hand = deepcopy(self.players[player_id]["hand"])
            for card in cards_played:
                if card not in current_hand:
                    raise ValueError(f"Player {player_id} does not have card {card}")
                current_hand.remove(card)
            self.players[player_id]["hand"] = current_hand

            claimed_rank = action.get("claimed_rank", self.table_rank)
            claimed_count = int(action.get("claimed_count", len(cards_played)))

            self.last_play = {
                "player_id": player_id,
                "cards_played": cards_played,
                "claimed_rank": claimed_rank,
                "claimed_count": claimed_count,
            }
            self.pile_size += len(cards_played)

            phase = f"r{self.round}_turn{self.turn_index}_play"
            self._emit(
                phase=phase,
                event="play_claim",
                source=player_id,
                target=-1,
                visibility="public",
                content={
                    "claimed_rank": claimed_rank,
                    "claimed_count": claimed_count,
                    "pile_size": self.pile_size,
                },
                outcome={},
            )
            self._emit(
                phase=phase,
                event="play_claim",
                source=player_id,
                target=-1,
                visibility="omniscient",
                content={
                    "claimed_rank": claimed_rank,
                    "claimed_count": claimed_count,
                    "actual_cards": deepcopy(cards_played),
                    "pile_size": self.pile_size,
                },
                outcome={},
            )

            self.current_turn = self._next_alive_player(self.current_turn)
            self.turn_index += 1
            self._emit_turn_end()
            return self.get_public_state()

        if action_type == "call_liar":
            if self.last_play is None:
                raise ValueError("Cannot call liar without a previous play")

            challenged_player = self.last_play["player_id"]
            actual_cards = self.last_play["cards_played"]

            self._emit(
                phase=f"r{self.round}_turn{self.turn_index}_challenge",
                event="challenge_call",
                source=player_id,
                target=challenged_player,
                visibility="public",
                content={"challenged_player": challenged_player},
                outcome={},
            )

            truthful = all(card == self.table_rank or card == "Joker" for card in actual_cards)
            verdict = "truth" if truthful else "lie"
            loser = player_id if truthful else challenged_player

            self._emit(
                phase=f"r{self.round}_resolve",
                event="challenge_resolve",
                source=-1,
                target=loser,
                visibility="public",
                content={
                    "challenger": player_id,
                    "challenged_player": challenged_player,
                    "verdict": verdict,
                },
                outcome={"loser": loser},
            )

            self._emit(
                phase=f"r{self.round}_resolve",
                event="challenge_resolve",
                source=-1,
                target=loser,
                visibility="omniscient",
                content={
                    "challenger": player_id,
                    "challenged_player": challenged_player,
                    "verdict": verdict,
                    "actual_cards": deepcopy(actual_cards),
                    "table_rank": self.table_rank,
                },
                outcome={"loser": loser},
            )

            roulette = self.players[loser]["revolver"]
            if len(roulette) == 0:
                raise RuntimeError("invalid roulette state: no chambers left")
            chamber = roulette.pop(0)
            chamber_result = "bang" if chamber else "click"
            eliminated = False
            if chamber:
                self.players[loser]["is_alive"] = False
                eliminated = True

            self._emit(
                phase=f"r{self.round}_resolve",
                event="penalty_resolve",
                source=-1,
                target=loser,
                visibility="public",
                content={
                    "loser": loser,
                    "chamber_result": chamber_result,
                    "eliminated": eliminated,
                    "chambers_left": len(self.players[loser]["revolver"]),
                },
                outcome={},
            )

            alive = self.get_alive_players()
            self._emit(
                phase=f"r{self.round}_end",
                event="round_end",
                source=-1,
                target=-1,
                visibility="public",
                content={
                    "reason": "challenge_resolved",
                    "alive_players": alive,
                },
                outcome={},
            )

            if len(alive) == 1:
                self.game_over = True
                self.winner = alive[0]
                self.end_time = self._utc_now()
                self._emit(
                    phase="terminal",
                    event="end_game",
                    source=-1,
                    target=self.winner,
                    visibility="public",
                    content={"winner": self.winner, "termination_reason": "last_player_alive"},
                    outcome={"winner": self.winner},
                )
                return self.get_public_state()

            # starter follows frozen v0.1 rule
            starter = loser if not eliminated else player_id
            self.turn_index += 1
            self._start_new_round(starter=starter)
            self._emit_turn_end()
            return self.get_public_state()

        raise ValueError(f"Unsupported action type: {action_type}")

    def _emit_turn_end(self) -> None:
        self._emit(
            phase=f"r{self.round}_turn{self.turn_index}_end",
            event="turn_end",
            source=-1,
            target=-1,
            visibility="public",
            content={
                "current_turn": self.current_turn,
                "table_rank": self.table_rank,
                "pile_size": self.pile_size,
                "players_status": {
                    str(pid): {
                        "is_alive": player["is_alive"],
                        "chambers_left": len(player["revolver"]) if player["is_alive"] else 0,
                        "card_count": len(player["hand"]),
                    }
                    for pid, player in self.players.items()
                },
            },
            outcome={},
        )

    def _emit(
        self,
        phase: str,
        event: str,
        source: int,
        target: int,
        visibility: str,
        content: Dict[str, Any],
        outcome: Dict[str, Any],
    ) -> None:
        self.event_id += 1
        self.events.append(
            {
                "game_id": self.game_id,
                "event_id": self.event_id,
                "round": self.round,
                "turn_index": self.turn_index,
                "phase": phase,
                "event": event,
                "source": source,
                "target": target,
                "visibility": visibility,
                "time": self._utc_now(),
                "content": content,
                "outcome": outcome,
            }
        )

    def get_visible_events(self, player_id: int) -> List[Dict[str, Any]]:
        visible_events: List[Dict[str, Any]] = []
        for event in self.events:
            if event["visibility"] == "public":
                visible_events.append(event)
                continue
            if event["visibility"] == "private":
                if event["target"] == player_id or event["source"] == player_id:
                    visible_events.append(event)
        return visible_events

    def get_public_state(self) -> Dict[str, Any]:
        return {
            "table_rank": self.table_rank,
            "pile_size": self.pile_size,
            "current_turn": self.current_turn,
            "last_play": {
                "player_id": self.last_play["player_id"],
                "claimed_rank": self.last_play["claimed_rank"],
                "claimed_count": self.last_play["claimed_count"],
            }
            if self.last_play is not None
            else None,
            "players_status": {
                str(pid): {
                    "chambers_left": len(player["revolver"]) if player["is_alive"] else 0,
                    "is_alive": player["is_alive"],
                    "card_count": len(player["hand"]),
                }
                for pid, player in self.players.items()
            },
            "game_over": self.game_over,
            "winner": self.winner,
        }

    def get_private_state(self, player_id: int) -> Dict[str, Any]:
        state = self.get_public_state()
        state["self_hand"] = deepcopy(self.players[player_id]["hand"])
        state["self_player_id"] = player_id
        return state

    def dump_game_log(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "env_version": self.env_version,
            "events": self.events,
        }

    def dump_game_meta(self, player_meta: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "env_version": self.env_version,
            "ruleset": self.ruleset,
            "seed": self.seed,
            "num_players": self.num_players,
            "start_time": self.start_time,
            "end_time": self.end_time or self._utc_now(),
            "winner": self.winner,
            "termination_reason": "last_player_alive" if self.game_over else "incomplete",
            "players": player_meta or [],
            "files": {
                "game_log": "game_log.json",
                "player_traces": [f"Player_{player_id}.jsonl" for player_id in range(1, self.num_players + 1)],
            },
        }

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
