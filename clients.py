"""
Управление несколькими Telethon-клиентами (аккаунтами).
Поддержка MTProxy (ConnectionTcpMTProxyRandomizedIntermediate) с разными портами на один IP.
"""
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

logger = logging.getLogger(__name__)

try:
    import config as _cfg
except ImportError:  # fallback для примера
    import config.example as _cfg

MT_PROXY_IP: Optional[str] = getattr(_cfg, "MT_PROXY_IP", None)
MT_PROXY_SECRET: Optional[str] = getattr(_cfg, "MT_PROXY_SECRET", None)
MT_PROXY_PORTS: List[int] = getattr(_cfg, "MT_PROXY_PORTS", []) or []
DEVICE_MODELS: List[str] = getattr(_cfg, "DEVICE_MODELS", []) or []
SYSTEM_VERSIONS: List[str] = getattr(_cfg, "SYSTEM_VERSIONS", []) or []
APP_VERSIONS: List[str] = getattr(_cfg, "APP_VERSIONS", []) or []

if MT_PROXY_IP or MT_PROXY_SECRET or MT_PROXY_PORTS:
    # Быстрая проверка корректности настроек MTProxy при старте
    if not (MT_PROXY_IP and MT_PROXY_SECRET and MT_PROXY_PORTS):
        logger.warning(
            "MTProxy частично настроен (MT_PROXY_IP/MT_PROXY_SECRET/MT_PROXY_PORTS). "
            "Проверь config.py: нужны все три параметра."
        )
    else:
        logger.info(
            "MTProxy включён: IP=%s, порты=%s",
            MT_PROXY_IP,
            ", ".join(str(p) for p in MT_PROXY_PORTS),
        )


def _is_string_session(s: str) -> bool:
    """Определяет, похоже ли значение на Telethon string session."""
    if not s or len(s) < 80:
        return False
    # String session: base64-like, без путей, обычно начинается с "1"
    if "/" in s or "\\" in s or " " in s:
        return False
    return s[0].isdigit() or (s[0].isalnum() and len(s) > 150)


def get_session_path(session_name: str, sessions_dir: str = "sessions") -> str:
    """Путь к сессии (без .session — Telethon добавит сам)."""
    Path(sessions_dir).mkdir(parents=True, exist_ok=True)
    name = session_name.replace(".session", "")
    return os.path.join(sessions_dir, name)


def _get_mtproxy_kwargs(index: int) -> Dict:
    """
    Возвращает kwargs для TelegramClient с MTProxy для аккаунта по индексу.
    Если MT_PROXY_IP/SECRET/PORTS не заданы, возвращает пустой dict.
    """
    if not (MT_PROXY_IP and MT_PROXY_SECRET and MT_PROXY_PORTS):
        return {}

    # Порт по индексу; если аккаунтов больше, чем портов — берём последний порт
    port = MT_PROXY_PORTS[index] if index < len(MT_PROXY_PORTS) else MT_PROXY_PORTS[-1]

    def _pick(seq: List[str], idx: int, default: str) -> str:
        if not seq:
            return default
        if idx < len(seq):
            return seq[idx]
        return seq[-1]

    kwargs: Dict = {
        "connection": ConnectionTcpMTProxyRandomizedIntermediate,
        "proxy": (MT_PROXY_IP, port, MT_PROXY_SECRET),
        "device_model": _pick(DEVICE_MODELS, index, "Telethon"),
        "system_version": _pick(SYSTEM_VERSIONS, index, "Python"),
        "app_version": _pick(APP_VERSIONS, index, "1.0"),
    }
    return kwargs


async def create_client(
    session_name_or_string: str,
    api_id: int,
    api_hash: str,
    sessions_dir: str = "sessions",
    phone: Optional[str] = None,
    force_sms: bool = False,
    client_kwargs: Optional[Dict] = None,
) -> TelegramClient:
    """
    Создаёт и подключает клиент.
    session_name_or_string: имя файла сессии ("account1") ИЛИ готовая string session.
    Если передана string session — логин не нужен, подключается сразу.
    client_kwargs: дополнительные параметры для TelegramClient (MTProxy, device_model и т.п.).
    """
    extra = client_kwargs or {}
    if _is_string_session(session_name_or_string):
        session = StringSession(session_name_or_string.strip())
        client = TelegramClient(session, api_id, api_hash, **extra)
        await client.connect()
    else:
        session_path = get_session_path(session_name_or_string, sessions_dir)
        client = TelegramClient(session_path, api_id, api_hash, **extra)
        if phone:
            await client.start(phone=phone, force_sms=force_sms)
        else:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError(f"Сессия {session_name_or_string} не авторизована. Запусти login_accounts.py")
    me = await client.get_me()
    logger.info(f"Аккаунт подключён: {me.first_name} (@{me.username})")
    if extra.get("proxy"):
        ip, port, _ = extra["proxy"]
        logger.info("    Работает через MTProxy %s:%s", ip, port)
    return client


async def create_clients(
    accounts: List[str],
    api_id: int,
    api_hash: str,
    sessions_dir: str = "sessions",
) -> List[TelegramClient]:
    """
    Создаёт список подключённых клиентов.
    accounts: имена сессий ("account1") или string sessions (готовая строка).
    MTProxy (если задан в config.py) автоматически распределяется по аккаунтам по разным портам.
    """
    clients = []
    for idx, acc in enumerate(accounts):
        name = acc if isinstance(acc, str) else str(acc)
        try:
            mt_kwargs = _get_mtproxy_kwargs(idx)
            if mt_kwargs:
                logger.info(
                    "Инициализация %s через MTProxy %s:%s",
                    name,
                    mt_kwargs["proxy"][0],
                    mt_kwargs["proxy"][1],
                )
            client = await create_client(name, api_id, api_hash, sessions_dir, client_kwargs=mt_kwargs)
            clients.append(client)
        except Exception as e:
            logger.error(f"Не удалось подключить {name}: {e}")
    return clients


async def disconnect_all(clients: List[TelegramClient]) -> None:
    """Отключить все клиенты."""
    for c in clients:
        try:
            await c.disconnect()
        except Exception as e:
            logger.warning(f"Ошибка при отключении: {e}")
