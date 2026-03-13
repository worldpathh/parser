"""
Регулярные выражения для извлечения ссылок из поля "О себе" в профиле.
Поддерживает: t.me, telegram.me, tg://, @username.
"""
import re
from typing import Set

# t.me/username или telegram.me/username
TELEGRAM_LINK = re.compile(
    r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})',
    re.IGNORECASE,
)

# t.me/+invite или t.me/joinchat/invite — приватные/инвайт-ссылки
PRIVATE_INVITE = re.compile(
    r'(?:https?://)?(?:www\.)?t\.me/(\+[A-Za-z0-9_\-]{5,64}|joinchat/[A-Za-z0-9_\-]{5,64})',
    re.IGNORECASE,
)

# tg://resolve?domain=username
TG_RESOLVE = re.compile(
    r'tg://resolve\?domain=([a-zA-Z0-9_]{5,32})',
    re.IGNORECASE
)

# @username в тексте (отдельное слово)
USERNAME_MENTION = re.compile(
    r'(?:^|[\s,;:!?.])(@[a-zA-Z0-9_]{5,32})(?:[\s,;:!?.]|$)'
)

# Любые URL (опционально, для дополнительных ссылок)
GENERIC_URL = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+',
    re.IGNORECASE
)


def extract_telegram_usernames(text: str) -> Set[str]:
    """
    Извлекает все Telegram-ссылки и юзернеймы из текста.
    Возвращает множество юзернеймов без @.
    """
    if not text or not isinstance(text, str):
        return set()

    usernames = set()

    # t.me/username, telegram.me/username
    for match in TELEGRAM_LINK.finditer(text):
        usernames.add(match.group(1).lower())

    # tg://resolve?domain=username
    for match in TG_RESOLVE.finditer(text):
        usernames.add(match.group(1).lower())

    # @username
    for match in USERNAME_MENTION.finditer(text):
        username = match.group(1).lstrip('@').lower()
        if len(username) >= 5:
            usernames.add(username)

    return usernames


def extract_all_urls(text: str) -> Set[str]:
    """Извлекает все URL из текста."""
    if not text or not isinstance(text, str):
        return set()
    return set(GENERIC_URL.findall(text))


def extract_private_invite_links(text: str) -> Set[str]:
    """
    Извлекает приватные инвайт-ссылки t.me/+... и t.me/joinchat/...
    Возвращает полный URL с https://.
    """
    if not text or not isinstance(text, str):
        return set()
    out: Set[str] = set()
    for match in PRIVATE_INVITE.finditer(text):
        path = match.group(1)
        out.add(f"https://t.me/{path}")
    return out
