import logging

from sqlalchemy import select

from database.database import db
from database.models.role import Role
from game.classic_mafia.roles import CLASSIC_ROLE_SPECS
from game.classic_mafia.roles import NightActionType

log = logging.getLogger("database.roles")


def _build_role_values(spec) -> dict:
    primary_action = spec.primary_action

    return {
        "id": spec.id,
        "key": spec.key.value,
        "name": spec.name,
        "team": spec.team.value,
        "description": spec.description,
        "goal": spec.goal,
        "night_action_type": primary_action.action_type.value if primary_action else None,
        "night_action_priority": spec.night_action_priority,
        "sort_order": spec.sort_order,
        "can_kill": spec.has_action(NightActionType.KILL),
        "can_check": spec.has_action(NightActionType.CHECK),
        "can_heal": spec.has_action(NightActionType.HEAL),
        "can_block": spec.has_action(NightActionType.BLOCK),
        "can_protect": spec.has_action(NightActionType.PROTECT),
        "can_fear": spec.has_action(NightActionType.FEAR),
        "learns_teammates": spec.learns_teammates,
        "votes_with_team": spec.votes_with_team,
        "one_time_ability": spec.one_time_ability,
        "available_only_after_death": spec.available_only_after_death,
        "can_target_self": spec.can_target_self,
        "can_target_others": spec.can_target_others,
        "appears_as_mafia": spec.appears_as_mafia,
    }


async def sync_classic_roles() -> None:
    async with db.begin() as session:
        existing_roles = await session.scalars(select(Role))
        roles_by_key = {role.key: role for role in existing_roles.all() if role.key}

        for spec in CLASSIC_ROLE_SPECS:
            values = _build_role_values(spec)
            role = roles_by_key.get(spec.key.value)

            if role is None:
                role = await session.get(Role, spec.id)

            if role is None:
                session.add(Role(**values))
                continue

            for field_name, value in values.items():
                setattr(role, field_name, value)

    log.info("Classic mafia roles synced: %s", len(CLASSIC_ROLE_SPECS))
