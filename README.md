<div align="center">

# Durak vs AI

**Durak, the Russian card game, for 2-4 players against a self-taught AI. The AI never sees your cards: its code only gets what a player at the table can see, and a law test checks it.**

[Русская версия](README.ru.md)

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

<img src="docs/preview_game2.png" width="880" alt="Two-player game: you are defending; on the right, AI thoughts show where each opponent card may be">

</div>

In tic-tac-toe or checkers the AI sees the whole board. In Durak it does not: the
opponents' cards are face down, and an honest AI has to infer them as the game goes, like
a person. Peeking would be the easy way, so the main rule of the project is that the AI
only receives `observation(state, player)`: its own hand and public information (table,
discard pile, trump, deck size, card counts, who picked up what).

## Features

- **Throw-in Durak** by default, **transfer Durak** as a switch. 36-card deck.
- Two simplifications compared with a live table: cards go down one at a time, and you can
  throw in only when everything on the table is beaten or the defender has said "take".
- **2 to 4 players**: one human, the rest are AI.
- Three AI levels: **novice**, **medium**, **strong**, plus an **AI vs AI** demo with open cards.
- **AI thoughts**: a 4 × 9 grid per opponent and for the deck with the probability of each card, and the strong AI's score of each of your moves.
- Cards are drawn by our own code (suits are built from circles and polygons); no third-party decks.
- Paint themes (dark and light) with a matching table cloth, Russian and English, the window reopens where it was closed.

## Honesty, tested

`tests/test_honesty.py` takes a random position, reshuffles every card the player cannot
see (the unknown part of the opponents' hands and the closed deck) and deals it again with
the same hand sizes. Then the player's observation must be identical, and every AI level
must choose the same move with the same seed. Publicly known cards (picked up from the
table, the face-up trump taken by the last drawer) stay where they are. The test was
written before the observation code; five mutants that break honesty on purpose are all
caught.

The window keeps it honest too: in a game against the AI, "AI thoughts" are computed from
**your** observation only (the AI's own grid would reveal its hand through zeros), face-down
opponent cards fly from the centre of the fan rather than from a position that would leak
their order, and "nothing to throw" looks exactly like "don't want to throw".

## How the AI plays

1. **Card tracking**: for each unseen card, the probability of being in each opponent's
   hand or in the deck (rows sum to 1, columns match card counts, Sinkhorn balancing). A
   defender who picked up a card is unlikely to hold cards that beat it (weight 0.15, not
   zero: taking can be deliberate).
2. **Determinization (PIMC)**: the unseen cards are dealt many times according to the
   tracker, never contradicting what is known.
3. **Search in each deal**: try each move, finish the current bout with simple rules for
   everyone, score the position at the bout boundary, pick the best average.
4. **A numpy value network** scores bout-boundary positions: 164 inputs (suits rotated so
   the trump is always in the same place), hidden layers 256 and 128, tanh output.
   75,265 weights.
5. **Exact endgame**: with an empty deck and two players nothing is unknown, so the game is
   solved by memoized minimax.

| Level | How it plays |
|---|---|
| Novice | rules: lead the lowest card, beat with the lowest card that works, save trumps |
| Medium | card tracking, 8 deals, formula evaluation |
| Strong | card tracking, 24 deals, network evaluation, exact endgame |

## Model passport

1000 games per check (`game/models/durak-value.json`). Two players: score share (win 1,
draw 1/2) over paired deals with seats swapped. Three and four players: how often the AI
ends up the fool; equal play gives 1/3 and 1/4. Tests replay the first games of every check
with the same seeds.

| Level | vs random | vs novice | vs medium | 3 players (fool) | 4 players (fool) |
|---|---|---|---|---|---|
| Strong | 99.5% | 75.7% | 82.6% | 12.1% | 7.6% |
| Medium | 96.5% | 53.7% | - | 23.2% | 16.6% |
| Novice | 97.9% | - | - | 0.2% | 0.1% |

With 3-4 players the strong and medium AIs sit with novices; the novice sits with random players.

## Training

`python -m game.train` runs only on command: 4 worker processes with one BLAS thread each,
a JSON log line and a snapshot (weights and Adam state) after every round, `--resume` to
continue, `--trial` to estimate the full run. The model took 20 rounds of 30,000 games -
600,000 games, 20.7 million positions, **34 minutes**. The score against the novice
plateaued by round 5, so training stopped at round 20.

What did not work: a first version learned from self-play where every player looked one
bout ahead with full card visibility. Search with that network scored only 55% against the
novice, and fine-tuning a good network that way dropped it from 77% to 63-66%. The search
finishes each bout with simple rules, so its leaf evaluation has to know the value of a
position under that kind of play. Training on the outcomes of simple-rule games (with 10%
random moves) gave 75-77% at once.

## What the pre-release review found (1.0.0)

Before the release a second agent read the code, and the AI game room shell held the game in
a tab next to other games for the first time. Found and fixed, each with a test and a mutant:

| In 0.9.0 | Risk | Now |
|---|---|---|
| The game widget called `gc.freeze()` | The garbage collector is per process: inside the shell every object alive at that moment (about 625 thousand in the benchmark) moved to the permanent generation and could never be freed, even as garbage | No call; a law test checks that creating the widget and playing do not change the frozen count, the enabled flag or the thresholds, and that `game/` and `aikit/` contain no `gc.freeze`, `disable` or `set_threshold` |
| Each AI request is its own QThread, a child of the widget | Threads were kept until the window closed, with their agent and observation: 51, 92, 136 objects after three two-player games | A finished thread is deleted (`deleteLater`); after a game at most one thread object is left |
| The "Play" and "New game" buttons passed `clicked(False)` as the seed | Every game started from a button had the same deal (seed 0); the N key worked, so the tests missed it | The buttons call `start_game` without arguments |
| Space and T worked on every page | From the menu, stats or settings they played "Done" or "Take" for the human in the hidden game, which then played out in the background and went into the stats | Human moves are accepted only on the table page |
| The exact endgame solver ignored the stop flag and the move time limit | The strong AI thought up to 2.8 s with a 1.5 s limit, and closing the window could miss the 2 s contract | The flag and the deadline are checked every 64 nodes, then regular search takes over |
| No deal animation (spec §5) | Cards appeared in the hands at once | Cards fly from the deck one after another; the AI's first move waits for the last one |
| `tests/test_privacy.py` banned the origin host | In a clone from GitHub the origin is `github.com`, which the publish script legitimately contains: the check would fail on GitHub CI | Public hosts (github.com and similar) are not treated as private |

**Pause in a tab.** The shell calls `pause()` when a tab is hidden and `resume()` when it is
shown again. The game now has its own: the AI stops thinking and moving, timers stop, card
flights end at once; after resume the game continues from the same place. Without them the
shell only stopped timers, and an AI answer arriving from its thread still made a move in
the hidden tab.

**Why `gc.freeze()` is not needed.** It came from ChessCheckersAi: a full collection holds
the GIL and the window stalls during search. Benchmark `tools/gc_bench.py`: the strong AI
without a time limit chooses a move in the same 600 positions, measured in thread CPU time
(other jobs were running on the machine, so wall time is noisy).

| In memory | Search, CPU s for 600 moves | Full collections during search |
|---|---|---|
| game only, with `gc.freeze` | 14.7 | 4, 31 ms total |
| game only, without | 14.9 | 4, 94 ms total |
| game plus 300 thousand "shell" objects, with `gc.freeze` | 15.3 / 15.2 / 15.3 | 4, 31-47 ms total |
| same, without | 14.7 / 15.2 / 15.2 | 1, 94-125 ms |

Search speed is the same, the difference is within run-to-run noise. Without the freeze the
window may stall for about 0.1 s once per 15 seconds of pure AI computation, and only in a
large shell; the game alone holds about 35 thousand objects, and a full collection takes
less than 16 ms, one Windows timer tick. The freeze cost the shell memory for good.

## Known limits

- **AI reply time is not equalized.** A forced move (pass when there is nothing to throw)
  comes right after the pause from the settings, a move with a choice comes after search.
  Usually the gap is small: the strong AI computes half of its moves in 0.02 s and 90% in
  under 0.12 s. But 1% of moves take over 1.3 s, and an attentive player can tell it had a
  choice.
- After a transfer the draw order starts from the player who transferred, not from the first
  attacker. Table rules differ here; it only matters with 3-4 players in transfer Durak when
  the deck is almost empty.

## Tests

229 pytest checks; the window is tested offscreen only, mouse input uses synthetic events,
AI waits have timeouts. Rules are covered by hand-built deals for every rule plus
property tests on random games (all 36 cards always accounted for). `tools/mutate.py`
breaks the product on purpose in 67 places (rules, honesty, tracking, search, network,
training, window, and since 1.0.0 life in a tab: collector, pause, threads, deal) - every
mutant is caught. `python main.py --selftest out.txt` checks a
built exe without a screen.

## Running and building

```
uv venv --python 3.13 .venv
uv pip install -r requirements-dev.txt
.venv\Scripts\python main.py
```

`python build.py` builds `dist/DurakAi`, a portable zip and an NSIS installer. PySide6 and
numpy only - no pygame, no PyTorch. The game follows the AI game room contract: everything
game-specific lives in `game/`, shared code in `aikit/`.

MIT license.
