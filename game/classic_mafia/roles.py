from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple


class RoleKey(str, Enum):
    MAFIA = "mafia"
    COMMISSAR = "commissar"
    DOCTOR = "doctor"
    LOVER = "lover"
    MANIAC = "maniac"
    ANGEL = "angel"
    GHOST = "ghost"
    CIVILIAN = "civilian"


class RoleTeam(str, Enum):
    MAFIA = "mafia"
    CITY = "city"
    SOLO = "solo"
    INHERITED = "inherited"


class NightActionType(str, Enum):
    KILL = "kill"
    CHECK = "check"
    HEAL = "heal"
    BLOCK = "block"
    PROTECT = "protect"
    FEAR = "fear"


@dataclass(frozen=True)
class AbilitySpec:
    action_type: NightActionType
    title: str
    description: str
    target_count: int = 1
    shared_with_team: bool = False
    can_target_self: bool = False
    max_uses: Optional[int] = None
    resolution_priority: int = 0
    result_message: Optional[str] = None


@dataclass(frozen=True)
class InteractionRule:
    trigger: str
    outcome: str


@dataclass(frozen=True)
class ClassicRoleSpec:
    id: int
    key: RoleKey
    name: str
    team: RoleTeam
    description: str
    goal: str
    abilities: Tuple[AbilitySpec, ...] = ()
    interaction_rules: Tuple[InteractionRule, ...] = ()
    learns_teammates: bool = False
    votes_with_team: bool = False
    one_time_ability: bool = False
    available_only_after_death: bool = False
    can_target_self: bool = False
    can_target_others: bool = True
    appears_as_mafia: bool = False

    @property
    def primary_action(self) -> Optional[AbilitySpec]:
        if not self.abilities:
            return None
        return self.abilities[0]

    @property
    def sort_order(self) -> int:
        return self.id

    @property
    def night_action_priority(self) -> int:
        action = self.primary_action
        if action is None:
            return 0
        return action.resolution_priority

    def has_action(self, action_type: NightActionType) -> bool:
        return any(ability.action_type == action_type for ability in self.abilities)


CLASSIC_ROLE_SPECS: Tuple[ClassicRoleSpec, ...] = (
    ClassicRoleSpec(
        id=1,
        key=RoleKey.MAFIA,
        name="Мафия",
        team=RoleTeam.MAFIA,
        description="Ночью мафия выбирает жертву. Если мафиози один, он стреляет без командного голосования.",
        goal="Устранить город и получить численное преимущество.",
        abilities=(
            AbilitySpec(
                action_type=NightActionType.KILL,
                title="Общее убийство",
                description="Мафия голосует за одну жертву и наносит ночной удар.",
                shared_with_team=True,
                can_target_self=False,
                resolution_priority=5,
            ),
        ),
        interaction_rules=(
            InteractionRule(
                trigger="Доктор лечит цель мафии.",
                outcome="Убийство мафии не проходит.",
            ),
            InteractionRule(
                trigger="Любовница блокирует мафию.",
                outcome="Мафия не стреляет этой ночью.",
            ),
            InteractionRule(
                trigger="Маньяк атакует мафию.",
                outcome="Мафия может быть убита маньяком как обычная цель.",
            ),
        ),
        learns_teammates=True,
        votes_with_team=True,
        appears_as_mafia=True,
    ),
    ClassicRoleSpec(
        id=2,
        key=RoleKey.COMMISSAR,
        name="Комиссар",
        team=RoleTeam.CITY,
        description="Ночью проверяет одного игрока и узнает, мафия это или нет.",
        goal="Найти мафию и помочь городу на дневном голосовании.",
        abilities=(
            AbilitySpec(
                action_type=NightActionType.CHECK,
                title="Проверка игрока",
                description="Показывает результат: Мафия или Не мафия.",
                can_target_self=False,
                resolution_priority=2,
                result_message="Результат проверки: Мафия / Не мафия.",
            ),
        ),
        interaction_rules=(
            InteractionRule(
                trigger="Любовница блокирует комиссара.",
                outcome="Проверка не происходит.",
            ),
            InteractionRule(
                trigger="Комиссар умирает ночью до выдачи результата.",
                outcome="Результат проверки не отправляется.",
            ),
        ),
    ),
    ClassicRoleSpec(
        id=3,
        key=RoleKey.DOCTOR,
        name="Доктор",
        team=RoleTeam.CITY,
        description="Ночью лечит одного игрока и отменяет смертельные атаки по цели.",
        goal="Сохранить город и ключевые роли в живых.",
        abilities=(
            AbilitySpec(
                action_type=NightActionType.HEAL,
                title="Лечение",
                description="Спасает выбранного игрока от ночной смерти.",
                can_target_self=True,
                resolution_priority=3,
            ),
        ),
        interaction_rules=(
            InteractionRule(
                trigger="Любовница блокирует доктора.",
                outcome="Лечение не срабатывает.",
            ),
            InteractionRule(
                trigger="Доктор лечит цель мафии.",
                outcome="Убийство мафии отменяется.",
            ),
            InteractionRule(
                trigger="Мафия и маньяк атакуют одну и ту же цель.",
                outcome="Доктор спасает цель сразу от обеих атак.",
            ),
        ),
        can_target_self=True,
    ),
    ClassicRoleSpec(
        id=4,
        key=RoleKey.LOVER,
        name="Любовница",
        team=RoleTeam.CITY,
        description="Ночью выбирает игрока и блокирует его способность на эту ночь.",
        goal="Контролировать ключевые роли и срывать опасные действия ночью.",
        abilities=(
            AbilitySpec(
                action_type=NightActionType.BLOCK,
                title="Блокировка",
                description="Лишает выбранного игрока его ночной способности.",
                can_target_self=False,
                resolution_priority=1,
            ),
        ),
        interaction_rules=(
            InteractionRule(
                trigger="Любовница выбирает мафию.",
                outcome="Мафия не убивает этой ночью.",
            ),
            InteractionRule(
                trigger="Любовница выбирает комиссара.",
                outcome="Проверка комиссара не происходит.",
            ),
            InteractionRule(
                trigger="Любовница выбирает доктора.",
                outcome="Лечение доктора не срабатывает.",
            ),
            InteractionRule(
                trigger="Любовница выбирает маньяка.",
                outcome="Маньяк не совершает убийство этой ночью.",
            ),
        ),
    ),
    ClassicRoleSpec(
        id=5,
        key=RoleKey.MANIAC,
        name="Маньяк",
        team=RoleTeam.SOLO,
        description="Ночью может убить любого игрока и играет сам за себя.",
        goal="Остаться единственным живым игроком в партии.",
        abilities=(
            AbilitySpec(
                action_type=NightActionType.KILL,
                title="Одиночное убийство",
                description="Маньяк выбирает одну цель и пытается убить ее ночью.",
                can_target_self=False,
                resolution_priority=6,
            ),
        ),
        interaction_rules=(
            InteractionRule(
                trigger="Доктор лечит цель маньяка.",
                outcome="Жертва маньяка выживает.",
            ),
            InteractionRule(
                trigger="Любовница блокирует маньяка.",
                outcome="Маньяк не убивает этой ночью.",
            ),
            InteractionRule(
                trigger="Маньяк атакует мафию.",
                outcome="Мафия может быть убита маньяком.",
            ),
        ),
    ),
    ClassicRoleSpec(
        id=6,
        key=RoleKey.ANGEL,
        name="Ангел",
        team=RoleTeam.CITY,
        description="Ночью защищает одного другого игрока. Эта защита сильнее лечения доктора.",
        goal="Сохранить ключевых игроков от любых ночных убийств.",
        abilities=(
            AbilitySpec(
                action_type=NightActionType.PROTECT,
                title="Защита",
                description="Защищенный игрок не может умереть ночью.",
                can_target_self=False,
                resolution_priority=4,
            ),
        ),
        interaction_rules=(
            InteractionRule(
                trigger="Ангел защищает игрока от мафии.",
                outcome="Игрок переживает атаку мафии.",
            ),
            InteractionRule(
                trigger="Ангел защищает игрока от маньяка.",
                outcome="Игрок переживает атаку маньяка.",
            ),
            InteractionRule(
                trigger="Ангел и доктор спасают одну цель.",
                outcome="Приоритет у ангела, но итог один: цель выживает.",
            ),
        ),
    ),
    ClassicRoleSpec(
        id=7,
        key=RoleKey.GHOST,
        name="Призрак",
        team=RoleTeam.INHERITED,
        description="Появляется после смерти игрока и наследует сторону своей прошлой роли.",
        goal="Помочь бывшей команде, используя единственный ночной испуг.",
        abilities=(
            AbilitySpec(
                action_type=NightActionType.FEAR,
                title="Испуг",
                description="Один раз ночью пугает игрока, лишая способности и дневного голоса.",
                can_target_self=False,
                max_uses=1,
                resolution_priority=7,
            ),
        ),
        interaction_rules=(
            InteractionRule(
                trigger="Призрак пугает игрока.",
                outcome="Игрок не применяет способность и не голосует днем.",
            ),
            InteractionRule(
                trigger="Призрак помогает бывшей команде.",
                outcome="Сторона призрака зависит от его роли при жизни.",
            ),
        ),
        one_time_ability=True,
        available_only_after_death=True,
    ),
    ClassicRoleSpec(
        id=8,
        key=RoleKey.CIVILIAN,
        name="Мирный",
        team=RoleTeam.CITY,
        description="Базовая городская роль без ночной способности.",
        goal="Найти и казнить мафию вместе с городом.",
        interaction_rules=(
            InteractionRule(
                trigger="Мирный участвует только в обсуждении и дневном голосовании.",
                outcome="Его сила строится на анализе и блефе, а не на ночном действии.",
            ),
        ),
    ),
)


CLASSIC_ROLE_SPECS_BY_KEY: Dict[str, ClassicRoleSpec] = {
    spec.key.value: spec for spec in CLASSIC_ROLE_SPECS
}


def get_classic_role_spec(role_key: str) -> Optional[ClassicRoleSpec]:
    return CLASSIC_ROLE_SPECS_BY_KEY.get(role_key)
