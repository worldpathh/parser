"""
Фильтр каналов: 130–1000 участников. Закрытые помечаем.
"""
import asyncio
import logging
import random
from typing import Optional, Dict, Tuple

from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import Channel, Chat
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError

logger = logging.getLogger(__name__)

# Результат проверки канала
# (include: bool, closed: bool, count: Optional[int], label: str)
ChannelCheck = Tuple[bool, bool, Optional[int], str]


async def check_channel(
    client: TelegramClient,
    channel_ref: str,
    min_count: int = 130,
    max_count: int = 1000,
    delay: float = 0.5,
) -> ChannelCheck:
    """
    Проверяет канал/чат.
    Возвращает (include, closed, count, label):
    - include: включать в вывод (130 <= count <= 1000)
    - closed: закрытый/приватный
    - count: число участников или None
    - label: "закрытый" если закрыт, иначе ""
    """
    if delay > 0:
        await asyncio.sleep(random.uniform(delay * 0.5, delay * 1.5))

    try:
        entity = await client.get_entity(channel_ref)
    except ChannelPrivateError as e:
        logger.debug(f"Канал {channel_ref}: закрытый/приватный - {e}")
        return (False, True, None, "закрытый")
    except UsernameNotOccupiedError as e:
        # username не существует / не занят — это не "закрытый"
        logger.debug(f"Канал {channel_ref}: username не найден - {e}")
        return (False, False, None, "")
    except ValueError as e:
        # некорректная ссылка/username — не "закрытый"
        logger.debug(f"Канал {channel_ref}: некорректный ref - {e}")
        return (False, False, None, "")
    except Exception as e:
        # Любая другая ошибка (таймауты, флад, сетевые) — не помечаем как закрытый
        logger.debug(f"Канал {channel_ref}: временная ошибка - {e}")
        return (False, False, None, "")

    # Только каналы и супергруппы
    if isinstance(entity, Channel):
        try:
            full = await client(GetFullChannelRequest(entity))
            count = getattr(full.full_chat, "participants_count", None)
            if count is None and getattr(full.full_chat, "participants_hidden", False):
                return (False, False, None, "")  # скрыто — пропускаем
            count = count or 0
        except ChannelPrivateError as e:
            logger.debug(f"Канал {channel_ref}: закрытый/приватный - {e}")
            return (False, True, None, "закрытый")
        except Exception as e:
            logger.debug(f"Канал {channel_ref}: нельзя получить инфо - {e}")
            return (False, False, None, "")
    elif isinstance(entity, Chat):
        try:
            full = await client(GetFullChatRequest(entity.id))
            p = getattr(full.full_chat, "participants", None)
            count = len(p.participants) if p and hasattr(p, "participants") else 0
        except Exception as e:
            logger.debug(f"Чат {channel_ref}: ошибка - {e}")
            return (False, True, None, "закрытый")
    else:
        return (False, False, None, "")  # пользователь, не канал

    include = (min_count is None and max_count is None) or (
        min_count <= count <= max_count
    )
    closed = False  # если дошли сюда — не закрытый
    return (include, closed, count, "")


async def filter_channels(
    client: TelegramClient,
    channel_refs: set,
    min_count: Optional[int] = 130,
    max_count: Optional[int] = 1000,
) -> Dict[str, ChannelCheck]:
    """Проверяет каналы. Всегда определяет closed. При min/max=None — все проходят по count."""
    cache = {}
    for ref in channel_refs:
        ref = str(ref).strip().lstrip("@")
        if not ref or ref.startswith("id:") or ref.isdigit():
            continue
        if ref in cache:
            continue
        r = await check_channel(client, ref, min_count or 0, max_count or 999999999)
        if min_count is None and max_count is None:
            r = (True, r[1], r[2], r[3])  # всегда include
        cache[ref] = r
        if r[1]:
            logger.info(f"  {ref}: закрытый")
        elif r[2] is not None and not r[0]:
            logger.info(f"  {ref}: {r[2]} участников (вне диапазона)")
    return cache
