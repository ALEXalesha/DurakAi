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
TR = "game/ai/tracker.py"
TTR = "tests/test_tracker.py"
MUTANTS += [
    ("tracker: «не отбился» не учитывается", TR, "w[q, c] = min(w[q, c], TAKE_W)", "pass", TTR),
    ("tracker: козыри не бьют", TR, "    if s != trump:\n        m |= C.SUIT_MASK[trump]\n", "", TTR),
    ("tracker: без нормировки столбцов", TR, "        M *= scale\n", "", TTR),
    ("tracker: козырь не в колоде", TR, "        P[obs.trump_card, n] = 1.0", "        pass", TTR),
    ("tracker: раскладка без весов", TR, "        p = P[pool[idx], q] + 1e-9", "        p = np.ones(len(idx))", TTR),
    ("tracker: известные не в раскладке", TR,
     "        hands[q] = obs.hand if q == obs.player else obs.known[q]",
     "        hands[q] = obs.hand if q == obs.player else 0", TTR),
]
S = "game/ai/search.py"
TS = "tests/test_search.py"
MUTANTS += [
    ("search: перебор за соперника максимизирует", S, "maximize = s.turn == self.me",
     "maximize = True", TS),
    ("search: отбой не доигрывается", S, "        if s.over or (s.bout != bout and not s.table):\n            return s",
     "        return s", TS),
    ("search: стоп не слушается", S,
     "if k >= 2 and ((stop is not None and stop.is_set()) or", "if k >= 2 and ((False) or", TS),
    ("search: формула наоборот", S, "return float(np.tanh(0.45 * weight * (others / n_alive - mine)))",
     "return float(np.tanh(0.45 * weight * (mine - others / n_alive)))", TS),
    ("search: без точного перебора", S, "        if self.exact is not None and exact_applicable(obs):",
     "        if False:", TS),
]
N = "game/ai/net.py"
SP = "game/train/selfplay.py"
TN = "tests/test_net_train.py"
MUTANTS += [
    ("net: без поворота мастей", N, "_ROT = [[(s - t - 1) % 4 for s in range(4)] for t in range(4)]",
     "_ROT = [[s for s in range(4)] for t in range(4)]", TN),
    ("net: колода не во входе", N, "    put_mask(v, 108, deckm, t)\n", "", TN),
    ("net: градиент со знаком минус", N, "self.backward((2.0 / len(y)) * diff)",
     "self.backward((-2.0 / len(y)) * diff)", TN),
    ("train: снимок без Adam", SP, "        self.opt.t = int(a[\"adam.t\"])\n", "", TN),
    ("train: цель без знака", SP, "(-1.0 if s.fool == q else 1.0)", "(1.0 if s.fool == q else 1.0)", TN),
]
TBL = "game/ui/table.py"
W = "game/ui/widget.py"
AT = "game/ui/ai_thread.py"
TU = "tests/test_ui.py"
MUTANTS += [
    ("ui: закрытые карты на своих местах", TBL, "face = self.reveal or (mine and self.viewer >= 0)",
     "face = True", TU),
    ("ui: мысли за ИИ", W,
     "elif self.settings[\"show_thoughts\"]:\n                self.ai.request_thoughts(self.token, s.obs(s.human),",
     "elif self.settings[\"show_thoughts\"]:\n                self.ai.request_thoughts(self.token, s.obs(1),", TU),
    ("ui: подглядывание не отмечается", W, "                self.session.peeked = True", "                pass", TU),
    ("ui: статистика не пишется", W, "            if not s.peeked:", "            if s.peeked:", TU),
    ("ui: потоки не ждут", AT, "            j.wait(left)", "            pass", TU),
    ("ui: перевод мышью не работает", TBL, "                if m[0] in (ATTACK, TRANSFER):", "                if m[0] == ATTACK:", TU),
]
MUTANTS += [
    ("passport: другой поиск у сильного", "game/ai/search.py", '"strong": dict(samples=24, use_net=True, exact=True)',
     '"strong": dict(samples=20, use_net=True, exact=True)', "tests/test_passport.py"),
]
MUTANTS += [
    ("ui: gc.freeze вернулся", W, "        self.ctx = ctx\n        self.t = translator(ctx.lang)",
     "        __import__('gc').freeze()\n        self.ctx = ctx\n        self.t = translator(ctx.lang)", TU),
    ("ui: pause не останавливает ИИ", W, "        self.hidden = True\n        self._invalidate()\n",
     "        self.hidden = True\n", TU),
    ("ui: resume не продолжает", W,
     "        if self.session is not None and self.current_page() == \"play\":\n            self.after_change()",
     "        pass", TU),
    ("ui: скрытая игра ходит", W, "        if self.hidden:                   # resume() запустит ход заново\n            return\n",
     "", TU),
    ("ui: поток ИИ не удаляется", AT, "        job.finished.connect(self._reap)", "        pass", TU),
    ("ui: несостоявшийся поток не в сиротах", AT, "            _ORPHANS.append(j)\n", "", TU),
]
MUTANTS += [
    ("search: перебор не слышит стоп", S,
     "        if self.nodes % 64 == 0 and ((self.stop is not None and self.stop.is_set()) or",
     "        if self.nodes % 64 == 0 and ((False) or", TS),
    ("search: перебор без срока", S,
     "                                     (self.deadline is not None and time.perf_counter() > self.deadline)):",
     "                                     (False)):", TS),
    ("ui: кнопка даёт зерно False", W, 'button("", "menuPrimary", lambda: gw.start_game())',
     'button("", "menuPrimary", gw.start_game)', TU),
    ("ui: клавиши ходят вне стола", W,
     "        return (s is not None and not self.hidden and self.current_page() == \"play\"",
     "        return (s is not None", TU),
]
MUTANTS += [
    ("ui: раздача без полёта", TBL, "        if self.deal_next:\n            self.deal_next = False\n",
     "        if False:\n            self.deal_next = False\n", TU),
    ("ui: ИИ не ждёт очередь карт", W, "        anim = round(max(0.0, self.play.table.anim_left()) * 1000)",
     "        anim = self.settings[\"anim_ms\"] if self.play.table.animating() else 0", TU),
]
MUTANTS += [
    ("ui: ход ИИ раньше мыслей", W,
     "            self.ai.request_thoughts(self.token, obs, self.rng.randrange(2 ** 31), level=s.level)\n            return\n",
     "            self.ai.request_thoughts(self.token, obs, self.rng.randrange(2 ** 31), level=s.level)\n", TU),
    ("ui: текст мыслей скрыт", W, "        pp.thoughts_text.setVisible(show)", "        pp.thoughts_text.setVisible(False)", TU),
    ("ui: на ходу ИИ учёт не обновляется", W,
     "        if s.mode == \"play\" and self.settings[\"show_thoughts\"]:\n", "        if False:\n", TU),
    ("ui: новичок без правил", AT, "            if level == \"novice\":", "            if False:", TU),
]
HI = "game/ui/history.py"
CH = "game/ui/charts.py"
TC = "tests/test_charts.py"
MUTANTS += [
    ("charts: окно скользящего среднего на 1 шире", HI, "if window is not None and k >= window:",
     "if window is not None and k > window:", TC),
    ("charts: доли по уровням не делятся", HI,
     "series = [(o, [count[lv][o] / sum(count[lv].values()) for lv in groups])",
     "series = [(o, [count[lv][o] / 1 for lv in groups])", TC),
    ("charts: пустой график без надписи", CH, "        if not self.has_data():\n            self.empty(p)\n            p.end()\n            return\n        series = ",
     "        if not self.has_data():\n            p.end()\n            return\n        series = ", TC),
    ("charts: журнал теряет номер партии", HI, "            self.next = max(last + 1, raw[\"next\"] if is_int(raw.get(\"next\")) else 1)",
     "            self.next = 1", TC),
    ("ui: партия не идёт в журнал", W, "                self.history.record({", "                ({", TU),
    ("ui: графики не меняют тему", W, "        for chart in self.stats.charts:\n            chart.set_theme(self.ctx.theme)\n",
     "", TU),
    ("charts: разница карт без знака", HI, "        return -left[human]", "        return left[human]", TC),
]
# 16.10, независимая проверка: подпись проверок паспорта и дурак из показа
MUTANTS += [
    ("ui: паспорт - новичок втроём «с новичками»", W,
     '    if ch.get("players", 2) > 2 and ch.get("villain") == "random":', '    if False:', TU),
    ("ui: дурак из показа решает первый ход", W, 'last = self.last_fool.get(s["mode"])',
     'last = next((v for v in self.last_fool.values() if v), None)', TU),
]
# 16.10, решение автора: брошенная партия после первого хода - в статистике
SE = "game/ui/session.py"
TA = "tests/test_abandon.py"
MUTANTS += [
    ("abandon: меню не бросает партию", W, "            self._abandon()                  # из меню",
     "            pass                  # из меню", TA),
    ("abandon: новая партия не бросает старую", W, "    def start_game(self, seed=None):\n        self._abandon()\n",
     "    def start_game(self, seed=None):\n", TA),
    ("abandon: закрытие окна не бросает партию", W,
     "        self._abandon()\n        self._invalidate()\n        return self.ai.shutdown(2000)",
     "        self._invalidate()\n        return self.ai.shutdown(2000)", TA),
    ("abandon: считается и до первого хода", SE, "if self.human < 0 or self.over or self.human_moves == 0:",
     "if self.human < 0 or self.over:", TA),
    ("abandon: автоматический пас - ваш ход", SE, "if not auto and self.human >= 0 and self.state.turn == self.human:",
     "if self.human >= 0 and self.state.turn == self.human:", TA),
    ("abandon: вышедший бросил - дурак", SE, 'return "win" if self.human in self.state.out else "loss"',
     'return "loss"', TA),
    ("abandon: вышедший раньше ничьей - ничья", SE, "        if self.out_early:\n            return \"win\"\n", "", TA),
    ("abandon: брошенная пишется дважды", W, "        if s is None or s.recorded:\n            return\n        outcome = s.abandon_outcome()",
     "        if s is None:\n            return\n        outcome = s.abandon_outcome()", TA),
    ("abandon: подсмотренная брошенная считается", W,
     "        s = self.session\n        if not s.peeked:\n            self.ctx.stats.record(",
     "        s = self.session\n        if True:\n            self.ctx.stats.record(", TA),
    ("abandon: разница карт - ваши", HI, "        return max((left[q] for q in range(len(left)) if q not in out and q != human), default=0)",
     "        return left[human]", TA),
]
