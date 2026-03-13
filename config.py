# Скопируйте в config.py и заполните своими данными

# API credentials от https://my.telegram.org
API_ID = 30172366
API_HASH = "0c72424ee890792a3e269d3711e6e12a"

# Аккаунты: имя сессии (затем login_accounts.py) или string session
ACCOUNTS =[
    "22",
    "account1",
    "hold"
]
## 33 - md dead

# Размер батча пользователей на один аккаунт
BATCH_SIZE = 75

# Фильтр каналов: мин и макс участников (None = без фильтра)
CHANNEL_MIN = 130
CHANNEL_MAX = 1000

# Пауза (сек) после каждого спаршенного батча
BATCH_COOLDOWN = 12

# Задержка (сек) перед стартом парсинга у каждого следующего аккаунта (0 = все стартуют сразу)
PARSE_START_DELAY = 5

# Пауза (сек) между чтением чатов разными аккаунтами при разогреве (Фаза 1).
# Если MIN == MAX — пауза фиксированная, иначе берётся случайное значение в диапазоне.
WARMUP_DELAY_MIN = 1
WARMUP_DELAY_MAX = 5

# Папка для сохранения сессий
SESSIONS_DIR = "sessions"

# Результаты
OUTPUT_DIR = "output"

# Токен бота (@BotFather) для bot.py
BOT_TOKEN = "8705223101:AAHdcVYrkkJwESpxtxU-7_L-RIyneIf9Ens"

# MTProxy настройки для аккаунтов
# Один IP, разные порты. Пример: 5 аккаунтов, порты 5001–5005.
MT_PROXY_IP = "193.46.218.194"          # сюда IP сервера, например "1.2.3.4"
MT_PROXY_SECRET = "dd9ce7b6195a35e522971251a1312d6e9c"      # сюда секрет вида "dd571d3f6f5b1a2c8e9a0b4c7d3e5f1a"
MT_PROXY_PORTS = [5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009]

# Модели устройств/версии для маскировки под разные клиенты (опционально)
DEVICE_MODELS = [
    "Samsung SM-S928B",
    "iPhone 15 Pro",
    "Xiaomi 14",
    "Pixel 8 Pro",
    "iPhone 14 Pro Max",
    "Samsung SM-S921B",
    "iPhone 13",
    "Xiaomi 13",
    "iPhone 12",
]

SYSTEM_VERSIONS = [
    "SDK 34",
    "iOS 18.1",
    "Android 14",
    "Android 14",
    "iOS 18.0",
    "SDK 34",
    "iOS 17.5",
    "Android 13",
    "iOS 17.0",
]

APP_VERSIONS = [
    "11.0.1",
    "10.14.2",
    "10.5.1",
    "10.5.1",
    "10.14.2",
    "11.0.1",
    "10.5.1",
    "10.5.1",
    "11.0.1",
]