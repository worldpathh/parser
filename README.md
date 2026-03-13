# Парсер чатов Telethon

Собирает чаты и каналы из профилей пользователей Telegram.

## Логика работы

1. **Сбор пользователей** из чата/канала:
   - если участники открыты → берём из `iter_participants`;
   - если скрыты → читаем сообщения и извлекаем `user_id` из отправителей, реплаев, пересланных.

2. **Разбивка на батчи** по 50–100 пользователей (настраивается).

3. **Парсинг профилей** — каждый батч обрабатывает отдельный аккаунт.

4. **Для каждого профиля**:
   - прикреплённый канал в профиле (`personal_channel_id`);
   - ссылки из поля «О себе» (regex: `t.me`, `telegram.me`, `@username`).

## Установка

```bash
pip install -r requirements.txt
```

## Настройка

1. Скопируйте `config.example.py` в `config.py`.

2. Укажите API credentials с [my.telegram.org](https://my.telegram.org):
   - `API_ID`
   - `API_HASH`

3. Добавьте имена сессий для аккаунтов в `ACCOUNTS`.

4. При первом запуске авторизуйте аккаунты:
   ```bash
   python login_accounts.py
   ```
   Или один аккаунт: `python login_accounts.py session_account1`

## Запуск

```bash
python main.py <chat_username_or_id> [chat2] [chat3] ...
```

Примеры:

```bash
python main.py my_channel
python main.py -1001234567890 another_chat
python main.py channel1 channel2 channel3
```

Результаты сохраняются в папку `output/` (CSV и JSON).

## Структура проекта

```
bot+pars/
├── main.py           # Точка входа
├── clients.py        # Управление несколькими аккаунтами
├── collectors.py     # Сбор пользователей (participants или сообщения)
├── profile_parser.py # Парсинг профиля (канал + regex по био)
├── utils/
│   └── regex_patterns.py  # Регулярки для ссылок
├── config.example.py
├── login_accounts.py # Первичная авторизация
└── requirements.txt
```
