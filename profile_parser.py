"""
Парсинг профилей пользователей: прикреплённый канал и ссылки из "О себе".
"""
import asyncio
import logging
import random
from typing import Optional, List, Set, Union

from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import User, InputUser
from telethon.errors import UserIdInvalidError

from utils.regex_patterns import extract_telegram_usernames, extract_private_invite_links

logger = logging.getLogger(__name__)


async def get_profile_channels_and_links(
    client: TelegramClient,
    user_info: dict,
) -> dict:
    """
    Парсит профиль пользователя двумя способами:
    1. Прикреплённый канал в профиле (personal_channel_id из UserFull)
    2. Ссылки из поля "О себе" (regex по t.me, telegram.me, @username)

    Возвращает:
        {
            "user_id": int,
            "username": str|None,
            "attached_channel": str|None,  # username канала если есть
            "links_from_bio": list[str],   # юзернеймы из био
            "bio": str|None,
            "error": str|None
        }
    """
    result = {
        "user_id": None,
        "username": None,
        "attached_channel": None,
        "links_from_bio": [],
        "bio": None,
        "error": None,
    }

    uid = user_info.get("user_id")
    uname = user_info.get("username")
    access_hash = user_info.get("access_hash")

    if not uid and not uname:
        result["error"] = "no id or username"
        return result

    # 1. Полный профиль (UserFull) — прикреплённый канал и био
    try:
        try:
            if uid and access_hash:
                inp = InputUser(uid, access_hash)
                full = await client(GetFullUserRequest(inp))
            else:
                raise UserIdInvalidError(request=None, message="no access_hash")  # перейти к fallback
        except UserIdInvalidError:
            # fallback: резолвим entity по username/id и пробуем ещё раз
            user_entity = await client.get_entity(uname or uid)
            full = await client(GetFullUserRequest(user_entity))

        user = next((u for u in full.users if isinstance(u, User) and (uid is None or u.id == uid)), None)
        if not user or getattr(user, "deleted", False):
            result["error"] = "deleted or not a user"
            return result

        result["user_id"] = user.id
        result["username"] = getattr(user, "username", None) or None

        full_user = full.full_user
        bio = getattr(full_user, "about", None) or ""

        result["bio"] = bio.strip() or None

        # Прикреплённый канал (personal_channel_id)
        channel_id = getattr(full_user, "personal_channel_id", None)
        if channel_id:
            try:
                channel = await client.get_entity(channel_id)
                result["attached_channel"] = getattr(channel, "username", None) or f"-100{channel_id}"
            except Exception as e:
                result["attached_channel"] = f"id:{channel_id}"
                logger.debug(f"Не удалось резолвнуть канал {channel_id}: {e}")

        # 2. Ссылки из био (regex)
        if bio:
            usernames = extract_telegram_usernames(bio)
            private_invites = extract_private_invite_links(bio)
            # usernames — как раньше (юзернеймы каналов/чатов)
            # private_invites — полные ссылки t.me/+... / t.me/joinchat/... (чаще всего закрытые)
            combined = list(sorted(usernames)) + list(sorted(private_invites))
            result["links_from_bio"] = combined

    except Exception as e:
        result["error"] = str(e)
        logger.debug(f"GetFullUser failed for user_info={user_info}: {e}")

    return result


async def parse_profiles_batch(
    client: TelegramClient,
    users: List[dict],
    delay: float = 1.0,
    account_name: Optional[str] = None,
    batch_cooldown: float = 12.0,
) -> List[dict]:
    """
    Парсит батч профилей с задержкой между запросами.
    users: список {"user_id", "username", ...}
    account_name: имя аккаунта для логов
    """
    label = f"[{account_name}] " if account_name else ""
    logger.info(f"{label}Старт парсинга {len(users)} профилей")
    # 4–5 длинных пауз (10–15 сек) в батче, остальные — короткие (1.5–4 сек)
    num_long = random.randint(4, 5)
    slots = max(0, len(users) - 1)  # после скольких профилей можно вставить паузу
    long_indices = set(random.sample(range(slots), min(num_long, slots))) if slots else set()
    results = []
    for i, u in enumerate(users):
        r = await get_profile_channels_and_links(client, u)
        r["source_username"] = u.get("username")
        results.append(r)
        if delay > 0 and i < len(users) - 1:
            if i in long_indices:
                pause = random.uniform(10, 15)
            else:
                pause = random.uniform(1.5, 4.0)
            await asyncio.sleep(pause)
    logger.info(f"{label}Готово: {len(results)} профилей")
    if batch_cooldown > 0:
        pause = random.uniform(30, 60)
        logger.info(f"{label}Пауза {pause:.1f} сек")
        await asyncio.sleep(pause)
    return results
