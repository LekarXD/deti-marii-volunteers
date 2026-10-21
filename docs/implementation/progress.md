# Реализация

Reference: `7d07222`, 43 boards plus `Event.html`. Этот commit опубликован в `main`; реализация собирается отдельно в `codex/implementation`. Незакоммиченные изменения прототипа в основном checkout сохранены.

Один интегратор A0, восемь исполнителей в отдельных worktrees. 21 октября P16 передан от A4 к A5 после сдачи P09; A4 продолжает Studio. Контракты генерируются из фактического FastAPI, миграции пишет только A1. Общая геометрия live/solo/renderer находится в `packages/studio-core`.

| Пакет | Текущее состояние | Проверка / граница доказательства |
|---|---|---|
| P00 | Контракты, workspace и reference зафиксированы | active-reference.json, work graph; ongoing integration |
| P01 | API, session/MFA, права, assets, jobs/outbox подключены | PostgreSQL, concurrency/revoke/receipt tests; production не развёрнут |
| P02 | Токены/SVG/локальный Inter, controls, верхняя навигация подключены | компонентные проверки, Storybook build; полный responsive matrix ещё не принят |
| P03–P05 | Анкета, три варианта знакомства, кабинет и очередь кандидатов подключены | серверные тесты; обычные 3 шага формы, draft reload и network retry проверены в браузере; финальная отметка согласия заблокирована auto-review |
| P06 | Слоты, запись/перенос/отмена, исход и следующий контакт подключены | 6 PostgreSQL тестов; следующий шаг использует единый CRM task store |
| P07–P09 | Роли, возможности, повторы, календарь, участие и attendance подключены | 16 PostgreSQL тестов; CUA: подтверждение/reload, счётчики координатора, отмена, attendance и корректировка; ledger P13 ещё не подключён |
| P10A/B | Участники/группы/фото и памятка подтверждённого назначения подключены | PostgreSQL scope/revoke/compound FK; JSON и фото закрываются при отмене/отзыве; private note не входит в памятку |
| P11 | CRM, резерв, импорт и единые follow-up подключены | 8 PostgreSQL тестов; frontend проверен типами/компонентным тестом, общий браузерный проход ещё не принят |
| P12 | Текстовый контур подключён | 11 PostgreSQL + 3 UI проверки; подготовка/рефлексия/restricted Signals, ASR явно недоступен; общий браузерный проход ещё нужен |
| P13 | В работе A3 | Профиль, ledger/коррекции, справки и workflows собственных данных |
| P14 | Ручной Builder и Academy подключены | версии/review/publish, private attachments, progress и задания проверены PostgreSQL; 2 компонентных проверки |
| P15 | Knowledge/Mentor/Builder AI подключены | published-only FTS/citations, durable provider outcomes, 5 PostgreSQL + 2 UI проверки; реальный внешний AI не вызван |
| P16 | В работе A5 | Редактор/версии сценариев; AI команды ждут проверенный P15 seam |
| P17A | Внутренние сообщения и outbox подключены | серверные ACL/receipt tests и 3 компонентных теста; двухсессионная браузерная приёмка ещё нужна |
| P17B | В работе A1 | Настройки, templates, audience preview и SMTP outcome journal; внешние сообщения не отправлялись |
| P18A | Shared stage подключён | 26 тестов geometry/readiness; CUA desktop и 390px, переключение live/solo и custom layout; это не запись видео |
| P18B | В работе A4 | LiveKit adapter/session/scene/slides/board; source reuse, локальная media приёмка ещё нужна |
| P18C/D/E | Последующие задачи A1/A2/A7 | Private renderer, реальный MP4, solo takes и явная публикация ещё не готовы |
| P19 | В очереди A3 | Отчёты и администрация после P13/P15/P17B |
| P20 | Независимая QA идёт с начала; общий гейт открыт | Полная карта экранов, обе роли, внешние providers/media/staging и точный release SHA ещё не приняты |

## Проверено на объединённом коде

- Последняя завершённая frontend серия: 93 tests, typecheck и production build. После следующих модулей проверка повторяется по изменённому составу.
- Расширенная серверная серия: 73 passed, zero skips после CRM/assignments/Studio. Независимая QA нашла два attendance edge case; владелец исправил их с 7 focused PostgreSQL проверками. Это не доказательство полного P20.
- G1: 14 HTTP сценариев на реальном API/PostgreSQL; дополнительные 12 ACL/revoke/receipt сценариев приняты отдельно.
- Native PostgreSQL16 используется в отдельных dev/test кластерах, существующие сервисы и SSH tunnel не изменяются. Миграции dev БД по head12 и `alembic check` прошли.
- Восстановление БД и приватного PNG проверено в отдельном QA кластере; детали и ограничения в `infra/evidence/`. Docker compose config проверен, сами образы/контейнеры не запускались из-за недоступного Docker daemon.
- CUA screenshots общей сцены сохранены в `infra/evidence/screenshots/`. Камера выключена, все имена/материалы вымышлены.

## До запуска

Реальный AI, email и RTC/recording providers должны быть настроены и отдельно приняты. Отсутствие интеграции возвращает unavailable/unknown, без ложной доставки/оценки/готового видео. Внешние сообщения, импорт реальной базы и production deployment не выполнялись.

Нет минимального возраста; справка рекомендована, пока роль явно не задаёт иное; знакомство и запись на собеседование независимы; исторический контакт не означает готового волонтёра. Новые разрешения не включают в себя автоматическое согласие на запись аудитории.
