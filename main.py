"""
Парсер чатов на Telethon.

Стратегия:
1. Все аккаунты параллельно считывают участников из чата(ов).
2. Из этого формируется общий список участников; каждый пользователь парсится только тем аккаунтом, который его собрал (чтобы не было ошибки «аккаунт не видел профиль»).
3. Список по аккаунтам делится на батчи, каждый аккаунт парсит свой батч; парсинг аккаунтов идёт параллельно.
"""
import asyncio
import csv
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from telethon import TelegramClient
from telethon.tl.types import Channel as TlChannel
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError, FloodWaitError, ChannelPrivateError

from clients import create_clients, disconnect_all
from collectors import collect_users_from_chat
from profile_parser import parse_profiles_batch
from channel_filter import filter_channels

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Импорт конфига
try:
    import config as _cfg
except ImportError:
    import config.example as _cfg
API_ID = _cfg.API_ID
API_HASH = _cfg.API_HASH
ACCOUNTS = _cfg.ACCOUNTS
BATCH_SIZE = _cfg.BATCH_SIZE
SESSIONS_DIR = _cfg.SESSIONS_DIR
OUTPUT_DIR = _cfg.OUTPUT_DIR
BATCH_COOLDOWN = getattr(_cfg, "BATCH_COOLDOWN", 12)
PARSE_START_DELAY = getattr(_cfg, "PARSE_START_DELAY", 5)
CHANNEL_MIN = getattr(_cfg, "CHANNEL_MIN", 130)
CHANNEL_MAX = getattr(_cfg, "CHANNEL_MAX", 1000)
CHANNEL_FILTER_BATCH_SIZE = 50  # сколько каналов проверяем за один заход на аккаунт


def split_into_batches(items: list, size: int) -> List[list]:
    """Делит список на батчи."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def _dedupe_results_by_user(results: List[dict]) -> List[dict]:
    """Оставляет первое вхождение по user_id (если один юзер собран несколькими аккаунтами)."""
    seen = set()
    out = []
    for r in results:
        uid = r.get("user_id")
        if uid is not None and uid in seen:
            continue
        if uid is not None:
            seen.add(uid)
        out.append(r)
    return out


async def _one_account_collect(
    client: TelegramClient,
    chat_ids: List[Union[str, int]],
    participant_limit: Optional[int],
    message_limit: int,
) -> List[dict]:
    """Один аккаунт собирает участников по всем чатам (без дублей по user_id)."""
    seen_ids = set()
    out = []
    for chat_id in chat_ids:
        users = await collect_users_from_chat(
            client,
            chat_id,
            participant_limit=participant_limit,
            message_limit=message_limit,
        )
        for u in users:
            uid = u.get("user_id")
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                out.append(u)
    return out


async def _join_chats_for_account(
    client: TelegramClient,
    chat_ids: List[Union[str, int]],
    acc_name: str,
) -> None:
    """Аккаунт пытается вступить во все указанные чаты/каналы."""
    for chat_id in chat_ids:
        try:
            ent = await client.get_entity(chat_id)
        except Exception as e:
            logger.warning("[%s] Не удалось получить чат %s при вступлении: %s", acc_name, chat_id, e)
            continue

        if not isinstance(ent, TlChannel):
            logger.info(
                "[%s] %s не является каналом/чатом (type=%s) — пропускаем join",
                acc_name,
                chat_id,
                type(ent),
            )
            continue

        try:
            logger.info("[%s] Пытаемся вступить в %s", acc_name, chat_id)
            await client(JoinChannelRequest(ent))
        except UserAlreadyParticipantError:
            logger.info("[%s] Уже в чате %s", acc_name, chat_id)
        except ChannelPrivateError as e:
            logger.warning("[%s] Канал приватный, нет доступа для join %s: %s", acc_name, chat_id, e)
        except FloodWaitError as e:
            wait_for = getattr(e, "seconds", None) or 60
            logger.warning(
                "[%s] FLOOD_WAIT %s сек при join %s, ждём и идём дальше", acc_name, wait_for, chat_id
            )
            await asyncio.sleep(wait_for + 5)
        except Exception as e:
            logger.warning("[%s] Ошибка при join %s: %s", acc_name, chat_id, e)


async def run_parser(
    chat_ids: List[Union[str, int]],
    participant_limit: Optional[int] = None,
    message_limit: int = 5000,
    profile_delay: float = 1.5,
) -> Optional[str]:
    """
    Запускает полный цикл парсинга.

    chat_ids: список чатов/каналов для сбора пользователей
    participant_limit: лимит участников (None = без лимита)
    message_limit: лимит сообщений при скрытых участниках
    profile_delay: задержка между запросами профиля (сек)
    """
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Подключаем аккаунты
    clients = await create_clients(ACCOUNTS, API_ID, API_HASH, SESSIONS_DIR)
    if not clients:
        logger.error("Нет подключённых аккаунтов")
        return None

    out_csv = None
    try:
        # 1. Вступление аккаунтов в чаты по очереди
        logger.info(
            "Фаза 1: аккаунты по очереди вступают в чаты %s (с паузой ~60 сек между аккаунтами)",
            chat_ids,
        )
        for idx, client in enumerate(clients):
            acc_name = ACCOUNTS[idx] if idx < len(ACCOUNTS) else f"acc{idx}"
            if idx > 0:
                pause = 60.0
                logger.info("Ожидание %.1f сек перед join для %s", pause, acc_name)
                await asyncio.sleep(pause)
            await _join_chats_for_account(client, chat_ids, acc_name)
        logger.info("Фаза 1 завершена.")

        # 2. Один аккаунт собирает полный список пользователей и делит на батчи.
        logger.info("Фаза 2: сбор общего списка пользователей первым аккаунтом")
        all_users = await _one_account_collect(
            clients[0],
            chat_ids,
            participant_limit,
            message_limit,
        )
        all_users = _dedupe_results_by_user(all_users)
        total_users = len(all_users)
        if total_users == 0:
            logger.info("Пользователей не найдено ни в одном чате")
            all_results: List[dict] = []
        else:
            logger.info("Всего уникальных пользователей: %s", total_users)

            batches = split_into_batches(all_users, BATCH_SIZE)
            logger.info("Всего батчей: %s (размер ~%s)", len(batches), BATCH_SIZE)

            # Распределяем батчи по аккаунтам: каждый аккаунт получает свой набор батчей.
            acc_names = [ACCOUNTS[i] if i < len(ACCOUNTS) else f"acc{i}" for i in range(len(clients))]
            batches_per_account: List[List[List[dict]]] = [[] for _ in range(len(clients))]
            for i, batch in enumerate(batches):
                idx = i % len(clients)
                batches_per_account[idx].append(batch)

            delay_sec = PARSE_START_DELAY
            if delay_sec > 0:
                logger.info(
                    "Фаза 3: парсинг батчей (старт аккаунтов с рандомной задержкой вокруг %s сек)", delay_sec
                )
            else:
                logger.info("Фаза 3: парсинг батчей по аккаунтам без стартовой задержки")

            async def _parse_account(idx: int) -> List[dict]:
                acc_name = acc_names[idx]
                my_batches = batches_per_account[idx]
                if not my_batches:
                    logger.info("[%s] батчей нет, аккаунт пропускаем", acc_name)
                    return []

                # Стартовая задержка для аккаунтов > 0 (рандомно вокруг PARSE_START_DELAY)
                if delay_sec > 0 and idx > 0:
                    total_delay = sum(
                        random.uniform(delay_sec * 0.5, delay_sec * 1.5) for _ in range(idx)
                    )
                    logger.info("[%s] старт парсинга через %.1f сек", acc_name, total_delay)
                    await asyncio.sleep(total_delay)

                all_res: List[dict] = []
                for i, batch in enumerate(my_batches, start=1):
                    logger.info(
                        "[%s] батч %s/%s (%s пользователей)",
                        acc_name,
                        i,
                        len(my_batches),
                        len(batch),
                    )
                    batch_results = await parse_profiles_batch(
                        clients[idx],
                        batch,
                        delay=profile_delay,
                        account_name=acc_name,
                        batch_cooldown=BATCH_COOLDOWN,
                    )
                    all_res.extend(batch_results)
                return all_res

            parsed_per_account: List[List[dict]] = await asyncio.gather(
                *[_parse_account(idx) for idx in range(len(clients))]
            )

            # Объединяем и убираем дубли по user_id (на всякий случай)
            raw_results = [r for results in parsed_per_account for r in results]
            all_results = _dedupe_results_by_user(raw_results)

        # 3. Сохраняем результаты
        out_csv = os.path.join(OUTPUT_DIR, f"profiles_{timestamp}.csv")
        out_json = os.path.join(OUTPUT_DIR, f"profiles_{timestamp}.json")

        def _link(u: str) -> str:
            """Нормализует ссылку на канал/чат.

            - если это уже полный URL (http/https) — возвращаем как есть
            - иначе считаем, что это username и добавляем https://t.me/
            """
            if not u:
                return ""
            s = str(u)
            if s.startswith("http://") or s.startswith("https://"):
                return s
            return f"https://t.me/{s}"

        def _format_channel(ref: str, cache: dict) -> str:
            """Форматирует канал: ссылка + метка. Пропускает если не 130–1000. Закрытые помечает."""
            ref_clean = str(ref).strip().lstrip("@").replace("id:", "")
            if not ref_clean or ref_clean.isdigit():
                return ""  # id без username — пропуск
            r = cache.get(ref_clean)
            if r is None:
                return _link(ref_clean)  # без фильтра — включаем
            include, closed, count, _ = r
            if closed:
                return _link(ref_clean) + " (закрытый)"
            if not include:
                return ""  # вне диапазона — пропускаем
            return _link(ref_clean)

        if all_results:
            # Собираем уникальные каналы (username'ы) для фильтрации по подписчикам.
            # Полные URL (t.me/+..., t.me/joinchat/..., http/https) НЕ отправляем в фильтр,
            # их считаем приватными/инвайтами и всегда включаем отдельно.
            channel_refs = set()
            for r in all_results:
                ch = r.get("attached_channel")
                if ch and not str(ch).startswith("id:"):
                    s = str(ch).strip()
                    if not (s.startswith("http://") or s.startswith("https://")):
                        channel_refs.add(s.lstrip("@"))
                for x in r.get("links_from_bio") or []:
                    if not isinstance(x, str):
                        continue
                    s = x.strip()
                    if not s or s.startswith("id:"):
                        continue
                    if s.startswith("http://") or s.startswith("https://"):
                        # полный URL — не отправляем в фильтр
                        continue
                    channel_refs.add(s.lstrip("@"))

            channel_cache: dict = {}
            if channel_refs:
                label = (
                    f"фильтр {CHANNEL_MIN}–{CHANNEL_MAX}"
                    if (CHANNEL_MIN is not None and CHANNEL_MAX is not None)
                    else "без фильтра по количеству"
                )
                logger.info(
                    "Проверка %s каналов (%s) всеми аккаунтами, батчами по %s с паузой 5 сек",
                    len(channel_refs),
                    label,
                    CHANNEL_FILTER_BATCH_SIZE,
                )

                # Распределяем каналы равномерно по аккаунтам
                refs_list = list(sorted(channel_refs))
                per_account: List[list] = [[] for _ in range(len(clients))]
                for i, ref in enumerate(refs_list):
                    per_account[i % len(clients)].append(ref)

                async def _filter_for_account(idx: int) -> dict:
                    client = clients[idx]
                    acc_name = acc_names[idx] if idx < len(acc_names) else f"acc{idx}"
                    my_refs = per_account[idx]
                    if not my_refs:
                        return {}
                    logger.info("[%s] проверяет %s каналов", acc_name, len(my_refs))
                    cache_local: dict = {}
                    # делим на батчи и даём паузу 5 сек между батчами
                    for start in range(0, len(my_refs), CHANNEL_FILTER_BATCH_SIZE):
                        batch = set(my_refs[start : start + CHANNEL_FILTER_BATCH_SIZE])
                        logger.info(
                            "[%s] батч каналов %s–%s из %s",
                            acc_name,
                            start + 1,
                            min(start + len(batch), len(my_refs)),
                            len(my_refs),
                        )
                        part = await filter_channels(client, batch, CHANNEL_MIN, CHANNEL_MAX)
                        cache_local.update(part)
                        if start + CHANNEL_FILTER_BATCH_SIZE < len(my_refs):
                            await asyncio.sleep(5)
                    return cache_local

                results_per_acc: List[dict] = await asyncio.gather(
                    *[_filter_for_account(i) for i in range(len(clients))]
                )
                for part in results_per_acc:
                    channel_cache.update(part)

            # Только username и каналы (с учётом фильтра). Полные URL считаем приватными.
            useful = []
            all_channels = set()
            for r in all_results:
                ch = r.get("attached_channel")
                links = r.get("links_from_bio") or []
                if not isinstance(links, list):
                    links = [x.strip() for x in str(links).split(";") if x.strip()]
                # Прикреплённый канал: username через фильтр, полный URL — как приватный
                ch_str = ""
                if ch:
                    s = str(ch).strip()
                    if s.startswith("http://") or s.startswith("https://"):
                        ch_str = f"{s} (закрытый)"
                    else:
                        ch_str = _format_channel(s, channel_cache)
                # Ссылки из био: username через фильтр, полный URL — как приватный
                link_parts = []
                for x in links:
                    s = str(x).strip()
                    if not s:
                        continue
                    if s.startswith("http://") or s.startswith("https://"):
                        link_parts.append(f"{s} (закрытый)")
                    else:
                        link_parts.append(_format_channel(s, channel_cache))
                # оба источника: attached_channel + links_from_bio, без дублей
                seen = set()
                unique = []
                for p in [ch_str] + link_parts:
                    if p and p not in seen:
                        seen.add(p)
                        unique.append(p)
                all_parts = unique
                if all_parts:
                    un = r.get("username") or r.get("source_username")
                    user = f"@{un}" if un else str(r.get("user_id", ""))
                    channels_str = ", ".join(all_parts)
                    for p in all_parts:
                        all_channels.add(p)
                    useful.append({"user": user, "channels": channels_str})

            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["user", "channels"], extrasaction="ignore")
                w.writeheader()
                w.writerows(useful)

            logger.info(f"Найдено каналов/чатов: {len(all_channels)}")
            logger.info(f"Пользователей с каналами: {len(useful)}")

        with open(out_json, "w", encoding="utf-8") as f:
            for r in all_results:
                r["links_from_bio"] = r.get("links_from_bio") or []
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        logger.info(f"Результаты: {out_csv}, {out_json}")
        return out_csv if all_results else None

    finally:
        await disconnect_all(clients)


def _parse_chat_id(s: str) -> Union[str, int]:
    """Преобразует строку в username или числовой ID."""
    s = s.strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return s


def main():
    import sys

    # Чат(ы) для парсинга — передать как аргументы или указать здесь
    raw = sys.argv[1:] if len(sys.argv) > 1 else [
        # "username_chata",
        # "-1001234567890",
    ]
    chat_ids = [_parse_chat_id(x) for x in raw]

    if not chat_ids:
        print("Использование: python main.py <chat_id_or_username> [chat2] [chat3] ...")
        print("Пример: python main.py my_channel -1001234567890")
        return

    asyncio.run(run_parser(chat_ids))


if __name__ == "__main__":
    main()
