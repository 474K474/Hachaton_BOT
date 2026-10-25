# Hachaton_BOT

Telegram-бот, который сам собирает IT-конференции, митапы и хакатоны в Санкт-Петербурге
и Москве — в первую очередь от Яндекса — и присылает их по твоим фильтрам.

## Что умеет

- `/upcoming` — ближайшие события по фильтрам, `/yandex` — все события Яндекса, `/hackathons` — хакатоны
- `/settings` — города (СПб / Москва / онлайн), типы, аудитория (разработка / PM и продукт / Data и ML),
  «только Яндекс», частота: сразу, раз в день или раз в неделю
- у каждого события кнопки **📅 В календарь** (.ics) и **🔔 Напомнить** (за сутки до начала)
- новые события присылаются автоматически; по понедельникам — сводка на неделю
- для админов: `/collect` — запустить сбор сейчас, `/stats` — статистика

## Откуда берутся события

| Источник | Как | Статус |
|---|---|---|
| [@Yandex4Developers](https://t.me/s/Yandex4Developers) | веб-превью публичного канала `t.me/s/…`, без авторизации; дайджесты режутся на отдельные события | основной источник Яндекса |
| events.yandex.ru | главная → страницы `/events/<slug>`, JSON-LD или og-теги | сейчас на сайте заглушка, коллектор возвращает пусто и заработает сам, когда сайт оживёт |
| Timepad | официальное API, города СПб и Москва, категория «ИТ» + фильтр по ключевым словам | нужен токен с dev.timepad.ru |

Любой публичный канал добавляется строкой в `.env`: `TG_CHANNELS=Yandex4Developers:Яндекс,другой_канал:Организатор`.

## Запуск

1. Создай бота у [@BotFather](https://t.me/BotFather) и получи токен.
2. Узнай свой user_id (например, у @userinfobot) — он нужен для админских команд.
3. Настрой окружение:

```bash
cp .env.example .env
# впиши BOT_TOKEN, ADMIN_IDS, при желании TIMEPAD_TOKEN
```

### Через Docker

```bash
docker compose up -d --build
docker compose logs -f
```

### Локально

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m eventbot
```

### Проверить парсеры без бота

```bash
python -m eventbot collect          # вывести, что нашлось, ничего не сохраняя
python -m eventbot collect --save   # то же, но записать в БД
```

## Как устроено

```
[APScheduler] → [collectors/*]  → RawEvent
                      ↓
               pipeline/normalize  → чистка названия, id = хэш(название + дата + город)
               pipeline/classify   → тип, аудитория, города (правила по ключевым словам)
               pipeline/dedup      → одно событие из разных источников = одна запись (rapidfuzz)
                      ↓
                 db (SQLite)  →  bot/notifier → подписчики
```

```
eventbot/
├── collectors/   # telegram_channel.py, yandex_events.py, timepad.py — по файлу на источник
├── pipeline/     # dates.py (русские даты), classify.py, normalize.py, dedup.py, runner.py
├── db/           # models.py, repo.py, session.py
├── bot/          # handlers.py, keyboards.py, notifier.py, formatting.py, ics.py
├── app.py        # сборка: бот + планировщик
└── __main__.py
tests/            # pytest, фикстуры страниц в tests/fixtures
web/              # будущая веб-часть на JS
```

Новый источник — это новый класс в `collectors/` с методом `fetch() -> list[RawEvent]`
и одна строка в `collectors/__init__.py`.

## Тесты

```bash
python -m pytest -q
```

Фикстура `tests/fixtures/tg_channel.html` собрана вручную по образцу разметки `t.me/s/…`.
Лучше заменить её реальной страницей: открыть https://t.me/s/Yandex4Developers,
«Сохранить как → только HTML» — и прогнать тесты.

## Что дальше

- [ ] прогнать на живых источниках и поправить разбор под реальные посты
- [ ] хакатон-источники (хакатоны.рус, Codenrock), PM-источники
- [ ] LLM-разметка для постов, которые правила не разобрали
- [ ] Postgres + alembic вместо SQLite
- [ ] веб-часть на React (`web/`)
