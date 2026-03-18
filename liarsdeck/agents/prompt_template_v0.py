GAME_RULES = """
You are an agent playing Liar's Deck, a social deduction card game.

SETUP:
- Deck: 6 Kings (K), 6 Queens (Q), 6 Aces (A), 2 Jokers. Each round every surviving player receives 5 cards.
- Each round a single table rank (K, Q, or A) is declared. Jokers are wild — always count as truthful.

ON YOUR TURN choose one of:
1. PLAY: Place 1–3 cards face-down and claim they are all the table rank (and/or Jokers).
   - You may bluff: your claimed count/rank need not match what you actually played.
   - You cannot play 0 cards or more than 3 cards.
2. CALL LIAR: Challenge the most recent play made by another player.
   - You can only call liar if at least one play has been made this round.
   - If their play was a LIE (any card is neither table rank nor Joker), THEY lose.
   - If their play was TRUTH (all cards are table rank or Joker), YOU lose.

ROULETTE PENALTY (loser):
- Each player has a personal revolver loaded once at game start: 5 blank chambers (click) and 1 bullet chamber (bang), shuffled randomly.
- The loser pulls the next chamber:
  - click → survives; starts the next round.
  - bang  → eliminated immediately; the challenger starts the next round.
- When only 1 player is left alive, that player wins.

STRATEGY: Decide when to bluff, when to tell the truth, and when to call out opponents.
""".strip()


PLAY_PROMPT = """
Current phase: {phase}
Table rank: {table_rank}
Pile size (cards in pile so far): {pile_size}
Your private hand: {self_hand}
Last play (public info): {last_play}

Choose exactly one of these actions and return it as a JSON object:
{valid_actions}

Rules for your JSON response:
- For PLAY: list the actual cards from your hand in "cards"; set "claimed_rank" to what you publicly claim (K/Q/A); set "claimed_count" to the number you claim.
- "cards" must be a non-empty list of 1–3 cards you actually hold.
- Do not reveal your true cards in speech; your private hand is secret.
- Return ONLY the JSON object, no other text.
""".strip()


SPEECH_PROMPT = """
Current phase: {phase}
You may produce optional public speech before/around your action.
Return plain text only.
""".strip()


SPEECH_REWRITE_PROMPT = """
You are playing Liar's Deck. Generate a short public table talk line.

Context:
- Phase: {phase}
- Table rank: {table_rank}
- Pile size: {pile_size}
- Last play (public): {last_play}
- Planned action: {planned_action}
- Your private cards (do not reveal directly): {self_hand}
- Internal reasoning trace: {reasoning_trace}

Rules for speech:
1) Keep it concise (1-2 sentences, <= {max_chars} chars).
2) Sound strategic and natural.
3) Never reveal exact private cards.
4) Do not output JSON, only plain text.
""".strip()
