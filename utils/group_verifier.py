import re
from dataclasses import dataclass
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError


PUBLIC_LINK_RE = re.compile(r"^(?:https?://)?t\.me/([A-Za-z0-9_]{5,})/?$")
USERNAME_RE = re.compile(r"^@([A-Za-z0-9_]{5,})$")


@dataclass
class GroupVerificationResult:
    ok: bool
    message: str
    reason: Optional[str] = None
    normalized_link: Optional[str] = None
    chat_id: Optional[int] = None
    chat_title: Optional[str] = None


@dataclass
class GroupMembershipResult:
    ok: bool
    message: str
    chat_id: Optional[int] = None
    chat_title: Optional[str] = None


def _extract_public_chat_username(raw_value: str) -> Optional[str]:
    value = raw_value.strip()
    public_link_match = PUBLIC_LINK_RE.match(value)
    if public_link_match:
        return public_link_match.group(1)

    username_match = USERNAME_RE.match(value)
    if username_match:
        return username_match.group(1)

    return None


async def verify_group_link(bot: Bot, raw_link: str) -> GroupVerificationResult:
    if "+" in raw_link or "joinchat" in raw_link:
        return GroupVerificationResult(
            ok=False,
            message=(
                "Сейчас автоматическая проверка работает только для публичных групповых ссылок "
                "вида t.me/group_name."
            ),
            reason="private_invite_link",
        )

    chat_username = _extract_public_chat_username(raw_link)
    if not chat_username:
        return GroupVerificationResult(
            ok=False,
            message="Отправь публичную ссылку вида t.me/group_name или @group_name.",
            reason="invalid_link",
        )

    normalized_link = "https://t.me/{}".format(chat_username)

    try:
        bot_info = await bot.get_me()
        chat = await bot.get_chat("@{}".format(chat_username))
        if chat.type not in ("group", "supergroup"):
            return GroupVerificationResult(
                ok=False,
                message="Ссылка должна вести именно на группу или супергруппу Telegram.",
                reason="not_a_group",
            )

        chat_member = await bot.get_chat_member(chat.id, bot_info.id)
    except TelegramForbiddenError:
        return GroupVerificationResult(
            ok=False,
            message=(
                "Бот не может получить доступ к этой группе. Проверь, что ты уже добавил бота "
                "в группу и выдал ему права администратора."
            ),
            reason="bot_cannot_access_chat",
        )
    except TelegramBadRequest:
        return GroupVerificationResult(
            ok=False,
            message=(
                "Не удалось проверить группу по этой ссылке. Проверь, что ссылка публичная, "
                "бот уже добавлен в группу и группа существует."
            ),
            reason="telegram_bad_request",
        )

    if chat_member.status not in ("administrator", "creator"):
        return GroupVerificationResult(
            ok=False,
            message="Бот найден в группе, но у него нет прав администратора.",
            reason="bot_not_admin",
            normalized_link=normalized_link,
            chat_id=chat.id,
            chat_title=chat.title,
        )

    return GroupVerificationResult(
        ok=True,
        message="Проверка пройдена: бот найден в группе и имеет права администратора.",
        reason="ok",
        normalized_link=normalized_link,
        chat_id=chat.id,
        chat_title=chat.title,
    )


async def verify_user_in_group(bot: Bot, raw_link: str, tg_user_id: int) -> GroupMembershipResult:
    chat_username = _extract_public_chat_username(raw_link)
    if not chat_username:
        return GroupMembershipResult(
            ok=False,
            message="Не удалось определить группу по сохраненной ссылке комнаты.",
        )

    try:
        chat = await bot.get_chat("@{}".format(chat_username))
        member = await bot.get_chat_member(chat.id, tg_user_id)
    except TelegramForbiddenError:
        return GroupMembershipResult(
            ok=False,
            message=(
                "Бот больше не может проверить участников группы. Проверь, что он все еще состоит "
                "в группе и имеет права администратора."
            ),
        )
    except TelegramBadRequest:
        return GroupMembershipResult(
            ok=False,
            message="Не удалось проверить наличие игрока в групповом чате.",
        )

    if member.status in ("left", "kicked"):
        return GroupMembershipResult(
            ok=False,
            message="Ты не состоишь в групповом чате комнаты. Зайди в чат и попробуй снова.",
            chat_id=chat.id,
            chat_title=chat.title,
        )

    return GroupMembershipResult(
        ok=True,
        message="Игрок найден в групповом чате.",
        chat_id=chat.id,
        chat_title=chat.title,
    )


async def resolve_group_chat(bot: Bot, raw_link: str) -> GroupMembershipResult:
    chat_username = _extract_public_chat_username(raw_link)
    if not chat_username:
        return GroupMembershipResult(
            ok=False,
            message="Не удалось определить группу по сохраненной ссылке комнаты.",
        )

    try:
        chat = await bot.get_chat("@{}".format(chat_username))
    except TelegramForbiddenError:
        return GroupMembershipResult(
            ok=False,
            message="Бот больше не может получить доступ к групповому чату комнаты.",
        )
    except TelegramBadRequest:
        return GroupMembershipResult(
            ok=False,
            message="Не удалось открыть групповой чат комнаты.",
        )

    return GroupMembershipResult(
        ok=True,
        message="Групповой чат найден.",
        chat_id=chat.id,
        chat_title=chat.title,
    )
