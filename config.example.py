# Скопируйте в config.py и заполните своими данными

# API credentials от https://my.telegram.org
API_ID = 12345678
API_HASH = "your_api_hash_here"

# Аккаунты: добавляй имена или string sessions.
# 1) Имя сессии: сначала запусти python login_accounts.py, залогинь аккаунт
# 2) String session: вставь готовую строку "1BVtsOGcB..." (без логина)
ACCOUNTS = [
    "account1",
    # "account2",      # добавить: добавить в список, запустить login_accounts.py
    # "1BVtsOGcB...",  # или string session
]

# Размер батча пользователей на один аккаунт
BATCH_SIZE = 75

# Фильтр каналов: 130–1000 участников. Закрытые помечаются
CHANNEL_MIN = 130
CHANNEL_MAX = 1000

# Пауза (сек) после каждого батча (10–15 рекомендуется)
BATCH_COOLDOWN = 12

# Задержка (сек) перед стартом парсинга у каждого следующего аккаунта (0 = все стартуют сразу)
PARSE_START_DELAY = 5

# Пауза (сек) между чтением чатов разными аккаунтами при разогреве (Фаза 1).
# Если MIN == MAX — пауза фиксированная, иначе выбирается случайное значение между MIN и MAX.
WARMUP_DELAY_MIN = 40
WARMUP_DELAY_MAX = 60

# Папка для сохранения сессий
SESSIONS_DIR = "sessions"

# Результаты
OUTPUT_DIR = "output"

# Токен бота (для bot.py) — создать через @BotFather
BOT_TOKEN = None

# Чат для прогрева сессий (должны быть добавлены все аккаунты)
# Можно указать username ("my_warmup_chat") или ID (-1001234567890)
WARMUP_CHAT = None

# Задержка (сек) после старта перед началом прогрева
WARMUP_INITIAL_DELAY = 3600

# Интервал (сек) между раундами warmup-сообщений
WARMUP_INTERVAL = 300
