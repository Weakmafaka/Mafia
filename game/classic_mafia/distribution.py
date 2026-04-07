from typing import Dict, List, Tuple

from .roles import RoleKey


CLASSIC_ROLE_DISTRIBUTION_BY_PLAYERS: Dict[int, Dict[str, int]] = {
    5: {
        RoleKey.MAFIA.value: 1,
        RoleKey.COMMISSAR.value: 1,
        RoleKey.DOCTOR.value: 1,
        RoleKey.CIVILIAN.value: 2,
    },
    6: {
        RoleKey.MAFIA.value: 1,
        RoleKey.COMMISSAR.value: 1,
        RoleKey.DOCTOR.value: 1,
        RoleKey.LOVER.value: 1,
        RoleKey.CIVILIAN.value: 2,
    },
    7: {
        RoleKey.MAFIA.value: 2,
        RoleKey.COMMISSAR.value: 1,
        RoleKey.DOCTOR.value: 1,
        RoleKey.LOVER.value: 1,
        RoleKey.CIVILIAN.value: 2,
    },
    8: {
        RoleKey.MAFIA.value: 2,
        RoleKey.COMMISSAR.value: 1,
        RoleKey.DOCTOR.value: 1,
        RoleKey.LOVER.value: 1,
        RoleKey.MANIAC.value: 1,
        RoleKey.CIVILIAN.value: 2,
    },
    9: {
        RoleKey.MAFIA.value: 2,
        RoleKey.COMMISSAR.value: 1,
        RoleKey.DOCTOR.value: 1,
        RoleKey.LOVER.value: 1,
        RoleKey.MANIAC.value: 1,
        RoleKey.ANGEL.value: 1,
        RoleKey.CIVILIAN.value: 2,
    },
    10: {
        RoleKey.MAFIA.value: 3,
        RoleKey.COMMISSAR.value: 1,
        RoleKey.DOCTOR.value: 1,
        RoleKey.LOVER.value: 1,
        RoleKey.MANIAC.value: 1,
        RoleKey.ANGEL.value: 1,
        RoleKey.CIVILIAN.value: 2,
    },
    11: {
        RoleKey.MAFIA.value: 3,
        RoleKey.COMMISSAR.value: 1,
        RoleKey.DOCTOR.value: 1,
        RoleKey.LOVER.value: 1,
        RoleKey.MANIAC.value: 1,
        RoleKey.ANGEL.value: 1,
        RoleKey.CIVILIAN.value: 3,
    },
}


CLASSIC_NIGHT_ACTION_ORDER: Tuple[str, ...] = (
    RoleKey.LOVER.value,
    RoleKey.COMMISSAR.value,
    RoleKey.DOCTOR.value,
    RoleKey.ANGEL.value,
    RoleKey.MAFIA.value,
    RoleKey.MANIAC.value,
    RoleKey.GHOST.value,
)


def get_classic_role_distribution(player_count: int) -> Dict[str, int]:
    distribution = CLASSIC_ROLE_DISTRIBUTION_BY_PLAYERS.get(player_count)
    if distribution is None:
        raise ValueError("Для классики нет распределения ролей на {} игроков.".format(player_count))
    return dict(distribution)


def build_classic_role_list(player_count: int) -> List[str]:
    distribution = get_classic_role_distribution(player_count)
    role_keys: List[str] = []
    for role_key, count in distribution.items():
        role_keys.extend([role_key] * count)
    return role_keys


def validate_classic_role_distribution() -> None:
    for player_count, distribution in CLASSIC_ROLE_DISTRIBUTION_BY_PLAYERS.items():
        assigned_roles = sum(distribution.values())
        if assigned_roles != player_count:
            raise ValueError(
                "Некорректное распределение классики для {} игроков: ролей {}.".format(
                    player_count,
                    assigned_roles,
                )
            )
