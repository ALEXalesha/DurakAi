# Мутанты движка и ИИ для tools/mutate.py: (имя, файл, было, стало, проверки).
E = "game/core/durak.py"
TD = "tests/test_durak.py"
MUTANTS = [
    ("rules: бьёт младшей", E, "if c % 9 > a % 9:", "if c % 9 != a % 9:", TD),
    ("rules: козырь бьёт козырь любой", E, "if sa != trump:", "if True:", TD),
    ("rules: подкинуть любую", E, "(ATTACK, c, -1) for c in C.cards_of(hand & self.table_ranks())",
     "(ATTACK, c, -1) for c in C.cards_of(hand)", TD),
    ("rules: первый отбой 6", E, "return 5 if (self.rules.first_bout_five and self.bout == 0) else 6",
     "return 6", TD),
    ("rules: стол 7", E, "return 5 if (self.rules.first_bout_five and self.bout == 0) else 6",
     "return 5 if (self.rules.first_bout_five and self.bout == 0) else 7", TD),
    ("rules: не побитых больше карт", E,
     "self.undefended() < self.hands[self.defender].bit_count())",
     "self.undefended() <= self.hands[self.defender].bit_count())", TD),
    ("rules: защитник подкидывает", E, "if q != self.defender and q not in self.out:",
     "if q not in self.out:", TD),
    ("rules: взявший ходит", E, "att = self.next_active(d)", "att = d", TD),
    ("rules: после бито не защитник", E, "att = d if d not in self.out else self.next_active(d)",
     "att = self.next_active(d)", TD),
    ("rules: добор защитник первым", E, "for q in order + [d]:\n            need",
     "for q in [d] + order:\n            need", TD),
    ("rules: подкинутая не даёт новый круг", E,
     "self.table.append([c, -1])\n            self.passed = 0\n            if log is not None:\n                log.append((\"attack\"",
     "self.table.append([c, -1])\n            if log is not None:\n                log.append((\"attack\"", TD),
    ("rules: перевод без карт у следующего", E, "self.hands[nxt].bit_count() >= k", "True", TD),
    ("rules: перевод после побитой", E, "if d >= 0 or a % 9 != r:", "if a % 9 != r:", TD),
    ("rules: перевод выключен не мешает", E, "if not self.rules.transfer or self.taking:",
     "if self.taking:", TD),
    ("rules: ничья не ничья", E, "self.fool = alive[0] if alive else DRAW",
     "self.fool = alive[0] if alive else 0", TD),
    ("rules: никто не выходит", E, "if not self.hands[q] and q not in self.out:", "if False:", TD),
    ("rules: старший козырь первым", E, "if best is None or low < best[0]:",
     "if best is None or low > best[0]:", TD),
    ("rules: берёт только атаку", E, "self.hands[d] |= tm",
     "self.hands[d] |= C.mask(a for a, _ in self.table)", TD),
    ("rules: козырь не последним", E, "got_trump = k == len(self.deck)", "got_trump = False", TD),
]
O = "game/core/observation.py"
TH = "tests/test_honesty.py"
MUTANTS += [
    ("honesty: видны чужие руки", O, "hand_sizes=tuple(h.bit_count() for h in state.hands),",
     "hand_sizes=tuple(state.hands),", TH),
    ("honesty: видна колода", O, "deck_size=len(state.deck),", "deck_size=tuple(state.deck),", TH),
    ("honesty: чужие ходы видны", O,
     "legal=tuple(state.legal_moves()) if state.turn == player else (),",
     "legal=tuple(state.legal_moves()),", TH),
    ("honesty: взятые не известны", O, "known[e[1]] |= e[2]", "pass", TH),
    ("honesty: сыгранная остаётся известной", O, "known[e[1]] &= ~(1 << e[2])", "pass", TH),
]
G = "game/ai/agents.py"
TB = "tests/test_bots.py"
TT = "game/ai/tournament.py"
MUTANTS += [
    ("bots: атака старшей", G, "key = (strength(c, trump), not pair, c)",
     "key = (-strength(c, trump), not pair, c)", TB),
    ("bots: не бережёт козыри", G, "if c // 9 == trump and deck_size > 6 and c % 9 >= 5:",
     "if False:", TB),
    ("bots: подкидывает козыри", G, "            if c // 9 == trump:\n                continue\n",
     "", TB),
    ("bots: тратит карты, хотя не побить", G, "if {m[2] for m in defends} != undefended_slots:",
     "if not defends:", TB),
    ("tournament: места не меняются", TT, "seat = i % 2", "seat = 0", TB),
    ("tournament: зерно хода постоянное", TT, "seed=move_seed(deck_seed, k)", "seed=0", TB),
]
