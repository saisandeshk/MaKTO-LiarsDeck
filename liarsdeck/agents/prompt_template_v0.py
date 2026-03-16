GAME_RULES = """
You are an agent in a Liar's Deck game.
Each round has a table rank in {K, Q, A}.
On your turn, you may either play 1..3 cards face down or call liar on the last play.
A play is considered truthful if all played cards are table rank or Joker.
After challenge resolution, loser takes roulette penalty.
Your goal is to survive and win as last alive player.
""".strip()


PLAY_PROMPT = """
Current phase: {phase}
Table rank: {table_rank}
Pile size: {pile_size}
Your hand: {self_hand}
Last play (public): {last_play}
Valid actions: {valid_actions}

Return a JSON object only:
{{"type":"play","cards":["K"]}}
or
{{"type":"call_liar"}}
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
