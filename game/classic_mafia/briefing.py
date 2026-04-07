from pathlib import Path

from .roles import CLASSIC_ROLE_SPECS_BY_KEY


PLAYER_CARDS_DIR = Path(__file__).resolve().parents[2] / "src" / "playerСards"

ROLE_CARD_FILENAMES = {
    "mafia": "mafia.jpeg",
    "commissar": "sheriff.jpeg",
    "doctor": "doctor.jpeg",
    "lover": "whore.jpeg",
    "maniac": "maniac.jpeg",
    "angel": "angel.jpeg",
    "ghost": "ghost.jpeg",
    "civilian": "civilian.jpeg",
}

ROLE_LIMITATIONS = {
    "mafia": "Нельзя лечить, проверять, защищать и блокировать игроков.",
    "commissar": "Нельзя лечить, убивать, защищать и блокировать игроков.",
    "doctor": "Нельзя убивать, проверять, защищать как ангел и блокировать игроков.",
    "lover": "Нельзя убивать, лечить, проверять и защищать игроков.",
    "maniac": "Нельзя лечить, проверять, защищать и играть в команде с городом или мафией.",
    "angel": "Нельзя защищать себя, убивать, лечить и проверять игроков.",
    "ghost": "Нельзя голосовать и пользоваться способностью больше одного раза.",
    "civilian": "Нельзя делать ночные действия: только обсуждать и голосовать днем.",
}

TEAM_LABELS = {
    "mafia": "Мафия",
    "city": "Город",
    "solo": "Одиночка",
    "inherited": "Наследуется от роли при жизни",
}


def get_role_card_path(role_key: str) -> Path:
    filename = ROLE_CARD_FILENAMES.get(role_key)
    if not filename:
        raise ValueError("Не найдена карточка для роли '{}'.".format(role_key))
    return PLAYER_CARDS_DIR / filename


def build_role_brief_text(role_key: str) -> str:
    spec = CLASSIC_ROLE_SPECS_BY_KEY.get(role_key)
    if spec is None:
        raise ValueError("Не найдена спецификация роли '{}'.".format(role_key))

    can_lines = []
    for ability in spec.abilities:
        can_lines.append("• {}".format(ability.description))
    if not can_lines:
        can_lines.append("• У тебя нет активной ночной способности.")

    limitations = ROLE_LIMITATIONS.get(role_key, "• Ограничения будут уточняться логикой игры.")
    return (
        "Твоя роль: {role_name}\n\n"
        "Команда: {team}\n"
        "Цель: {goal}\n\n"
        "Что ты можешь:\n"
        "{can_text}\n\n"
        "Что ты не можешь:\n"
        "• {limitations}\n\n"
        "Ознакомься с ролью и нажми кнопку ниже."
    ).format(
        role_name=spec.name,
        team=TEAM_LABELS.get(spec.team.value, spec.team.value),
        goal=spec.goal,
        can_text="\n".join(can_lines),
        limitations=limitations,
    )
