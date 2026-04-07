from enum import Enum


class GameMode(str, Enum):
    CLASSIC = "classic"
    CUSTOM = "custom"


def game_mode_label(game_mode: str) -> str:
    if game_mode == GameMode.CUSTOM.value:
        return "Кастом"
    return "Классика"
