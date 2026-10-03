"""DurakAi: карточная игра «Дурак» против ИИ, который научился играть сам.

Вход игры по контракту PythonAiGames: GAME_INFO и create_widget(ctx). Qt загружается
только в create_widget - правила, ИИ и обучение работают без него.
"""
from game.version import VERSION

GAME_INFO = {
    "id": "durak",
    "title": {"ru": "Дурак", "en": "Durak"},
    "summary": {"ru": "Подкидной и переводной дурак против ИИ, который не подглядывает в карты",
                "en": "Durak card game against a self-taught AI that never peeks at your cards"},
    "preview": "docs/preview.png",
    "version": VERSION,
}

APP_NAME = "DurakAi"


def create_widget(ctx):
    """ctx: aikit.Context. Виджет со столом, меню и панелями."""
    from game.ui.widget import GameWidget
    return GameWidget(ctx)
