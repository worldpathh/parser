"""
Сбор пользователей из чатов и каналов.
Стратегия: если участники открыты — берём из participants, иначе — из сообщений чата.
"""
import asyncio
import logging
from typing import Set, List, Optional, Union

from telethon import TelegramClient
from telethon.tl.types import Channel, User
from telethon.errors import ChannelPrivateError, ChatAdminRequiredError

logger = logging.getLogger(__name__)


async def _get_chat_entity(client: TelegramClient, chat_id: Union[str, int]):
    """Получить entity чата по username, ID или t.me-ссылке."""
    original = chat_id

    # Нормализация t.me-ссылок и @username
    if isinstance(chat_id, str):
        s = chat_id.strip()
        # Если прилетела полная ссылка вида https://t.me/xxx или http://t.me/xxx
        if "t.me/" in s:
            # отбрасываем протокол и всё до t.me/
            try:
                s = s.split("t.me/", 1)[1]
            except Exception:
                pass
        # Убираем ведущий @
        if s.startswith("@"):
            s = s[1:]
        chat_id = s or chat_id

    try:
        return await client.get_entity(chat_id)
    except Exception as e:
        logger.error(f"Не удалось получить чат {original}: {e}")
        return None


def _participants_hidden(entity) -> bool:
    """Проверяет, скрыты ли участники в канале/супергруппе."""
    if isinstance(entity, Channel):
        return getattr(entity, "participants_hidden", False) or False
    return False


async def collect_from_participants(
    client: TelegramClient,
    chat_id: Union[str, int],
    limit: Optional[int] = None,
) -> List[dict]:
    """
    Собирает пользователей из списка участников (если он открыт).
    Возвращает список словарей с user_id, username.
    """
    entity = await _get_chat_entity(client, chat_id)
    if not entity:
        return []

    users = []
    try:
        async for user in client.iter_participants(entity, limit=limit):
            if user.bot or user.deleted:
                continue
            users.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "phone": getattr(user, "phone", None),
                    "access_hash": getattr(user, "access_hash", None),
                }
            )
    except (ChannelPrivateError, ChatAdminRequiredError) as e:
        logger.warning(f"Участники недоступны для {chat_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Ошибка при сборе участников {chat_id}: {e}")
        return []

    return users


def _extract_users_from_message(msg) -> Set[int]:
    """Извлекает user_id из сообщения (from_id, reply, fwd)."""
    ids = set()
    if msg.from_id:
        # Берём только user_id. channel_id/chat_id не являются пользователями.
        uid = getattr(msg.from_id, "user_id", None)
        if uid:
            ids.add(uid)
    if msg.reply_to:
        rid = getattr(msg.reply_to, "reply_to_sender_id", None) or (
            getattr(msg.reply_to.reply_to_peer_id, "user_id", None) if hasattr(msg.reply_to, "reply_to_peer_id") else None
        )
        if rid:
            ids.add(rid)
    if msg.fwd_from:
        fid = getattr(msg.fwd_from.from_id, "user_id", None)
        if fid:
            ids.add(fid)
        # saved_from_peer может быть канал/чат — не добавляем
    # entities: MessageEntityMentionName
    if msg.entities:
        for ent in msg.entities:
            if hasattr(ent, "user_id"):
                ids.add(ent.user_id)
    return ids


async def collect_from_messages(
    client: TelegramClient,
    chat_id: Union[str, int],
    message_limit: int = 5000,
) -> List[dict]:
    """
    Собирает пользователей из сообщений чата (когда участники скрыты).
    Читает историю и извлекает user_id из отправителей, реплаев, пересланных.
    """
    entity = await _get_chat_entity(client, chat_id)
    if not entity:
        return []

    user_ids = set()
    try:
        async for msg in client.iter_messages(entity, limit=message_limit):
            user_ids.update(_extract_users_from_message(msg))
    except Exception as e:
        logger.error(f"Ошибка при чтении сообщений {chat_id}: {e}")
        return []

    users = []
    for uid in user_ids:
        try:
            ent = await client.get_entity(uid)
            # Нам нужны только реальные пользователи
            if not isinstance(ent, User):
                continue
            if ent.bot or getattr(ent, "deleted", False):
                continue
            users.append(
                {
                    "user_id": ent.id,
                    "username": getattr(ent, "username", None),
                    "phone": getattr(ent, "phone", None),
                    "access_hash": getattr(ent, "access_hash", None),
                }
            )
        except Exception:
            continue

    return users


async def collect_users_from_chat(
    client: TelegramClient,
    chat_id: Union[str, int],
    participant_limit: Optional[int] = None,
    message_limit: int = 5000,
) -> List[dict]:
    """
    Главная функция: собирает пользователей чата.
    - Если участники видны → iter_participants
    - Если скрыты → iter_messages и извлечение user_id
    """
    entity = await _get_chat_entity(client, chat_id)
    if not entity:
        return []

    # Если это личный аккаунт (User), а не чат/канал — у него нет «участников».
    # Такое бывает, когда передают ссылку на профиль вместо чата.
    if isinstance(entity, User):
        logger.warning(
            "Объект %s является личным аккаунтом (@%s), у него нет участников — пропускаем",
            chat_id,
            getattr(entity, "username", None),
        )
        return []

    if _participants_hidden(entity):
        logger.info(f"Участники скрыты для {chat_id}, парсим по сообщениям")
        return await collect_from_messages(client, chat_id, message_limit)
    else:
        logger.info(f"Участники открыты для {chat_id}, парсим participants")
        return await collect_from_participants(client, chat_id, participant_limit)
