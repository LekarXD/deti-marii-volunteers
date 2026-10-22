# Telegram-бот @detimarie_bot на стенде — первый запуск

Что появилось: сервис `bot` в `compose.yml` (образ из `infra/preview/bot.Dockerfile`), переменные
`OPORA_TELEGRAM_*` у `api`, образ `bot` в `opora_deploy.py`. Бот ходит в API по внутренней сети
(`http://api:8001`) и в Telegram по `egress`. Как он устроен — `bot/README.md` и
`apps/api/app/modules/notifications/TELEGRAM.md`.

Первый релиз с ботом автоматическая выкладка **откажется ставить**: меняется конфигурация Compose
(новый сервис и переменные), это по правилам `README.md` делается вручную один раз. Дальше каждый пуш
в `main` пересобирает и бота автоматически, как остальные образы.

## 1. Секреты в `private/runtime.env` (root, 0600)

```sh
cd /opt/odschool/opora-preview/private
printf 'OPORA_TELEGRAM_LINK_ENABLED=true\nOPORA_TELEGRAM_BOT_USERNAME=detimarie_bot\n' >> runtime.env
printf 'OPORA_TELEGRAM_WEBHOOK_SECRET=%s\n' "$(openssl rand -hex 32)" >> runtime.env
printf 'OPORA_TELEGRAM_BOT_API_SECRET=%s\n' "$(openssl rand -hex 32)" >> runtime.env
# токен бота от @BotFather — Фёдор передаёт лично, не в чат и не в git:
printf 'OPORA_TELEGRAM_BOT_TOKEN=%s\n' '<токен>' >> runtime.env
```

Не печатать runtime.env и `docker compose config`. Токен попадает только в контейнер `bot`
(как `BOT_TOKEN`), в API его нет — поэтому заполнение демо-данными (`app.stage_demo`) по-прежнему работает.

## 2. Остановить другие копии бота

Одновременно у токена может работать только одна копия. Если бот запускали на ноутбуке или
другом сервере — остановить. Признак второй копии в логах: `TelegramConflictError` / `409 Conflict`.

## 3. Ручной релиз

Как в `../README.md` для изменений конфигурации: исходники релиза `releases/<SHA>`, образы
`api`, `web`, `board`, `media` для этого SHA (или те, что уже собрала автовыкладка перед отказом —
см. `evidence/<SHA>/`), плюс образ бота:

```sh
cd /opt/odschool/opora-preview/releases/<SHA>
docker build --label org.opencontainers.image.revision=<SHA> -f infra/preview/bot.Dockerfile -t opora-preview/bot:<SHA> .
```

Затем обычный `docker compose ... -f releases/<SHA>/infra/preview/compose.yml --profile media up -d`
с теми же файлами-переопределениями, что у работающего релиза. Миграция `b7e2c41d9a05` (колонка
`sessions.channel`) применяется сервисом `migrate` как обычно.

**Обязательно в том же релизе** обновить установленную копию скрипта выкладки — пуши её не обновляют
(`README.md`, «Install or update on the host»):

```sh
cp releases/<SHA>/infra/preview/deploy/opora_deploy.py /opt/odschool/opora-preview/bin/
```

Без этого следующий пуш в `main` не соберёт `opora-preview/bot:<новый SHA>` и не впишет бота в
`release-<SHA>-images.json`: автовыкладка откажется («runtime configuration would change») или упадёт
на `up -d`, и так будет с каждым следующим коммитом. Ставить новую копию раньше релиза с ботом тоже
нельзя: она попробует собрать `bot.Dockerfile`, которого в старых коммитах нет. Поэтому на время
ручного релиза таймер лучше остановить: `systemctl stop opora-preview-autodeploy.timer`, после —
`systemctl start …`.

## 4. Проверка

```sh
docker logs opora-preview-bot-1 --tail 20      # ждём «Start polling», без ошибок
docker logs opora-preview-api-1 --tail 50 | grep -i telegram
```

В браузере: войти демо-волонтёром → Профиль → «Обо мне» → **«Подключить Telegram»** → «Открыть бота» →
в Telegram «Начать» → бот пишет «Telegram подключён к вашему профилю на сайте». Дальше «Мои занятия»
показывает занятия с сайта. Координатор: подключить Telegram так же, затем в боте `/coordinator`
и код из приложения (на стенде с `OPORA_DEMO_EMAIL_CODES=true` код не спрашивается).

## Откат

Убрать строку `OPORA_TELEGRAM_BOT_TOKEN` и `docker compose ... up -d bot` — бот остановится и будет ждать
настройки. `OPORA_TELEGRAM_LINK_ENABLED=false` и `up -d api` — кнопка в профиле покажет «Привязка пока
недоступна». Данные сайта бот не хранит: в его томе `bot-data` только отметки «что уже отправлено».
