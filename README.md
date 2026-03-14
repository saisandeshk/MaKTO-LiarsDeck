# MaKTO-LiarsDeck (Scaffold)

This repository is a **planning-first clone** of `MaKTO-Werewolf` for the Liar's Deck game.

Current policy:
- No game logic implementation yet.
- Files contain roadmap comments only.
- Goal is to align structure, interfaces, and data contracts before coding.

## Planned workflow

1. Finalize game rules specification for Liar's Deck MVP.
2. Implement environment + structured logging contract.
3. Implement run scripts (`run_battle.py`, `run_random.py`).
4. Generate trajectories with baseline agents.
5. Build SFT/KTO extraction pipeline.
6. Train SFT and preference model.

## Key design constraints

- Keep interfaces similar to MaKTO where practical.
- Add synthetic-data-first pipeline (no expert human logs dependency).
- Keep proprietary-model hooks optional and swappable.
