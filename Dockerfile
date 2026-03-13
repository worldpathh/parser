FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC

WORKDIR /app

# Ставим зависимости
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Кладём весь проект внутрь образа
COPY . ./

# Папки для сессий и вывода (на сервере можно примонтировать volume)
RUN mkdir -p /app/sessions /app/output

# По умолчанию запускаем бота, который управляет парсером
CMD ["python", "bot.py"]

