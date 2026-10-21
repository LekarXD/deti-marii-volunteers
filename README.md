# deti-marii-volunteers

Веб-платформа волонтёров фонда «Дети Марии» (хакатон, кейс 3).

Единое цифровое пространство: профиль волонтёра, обучение, каталог возможностей, подбор, учёт участия, коммуникация, мотивация и рабочее пространство для команды фонда.

[Технический план реализации](docs/implementation/README.md): React + TypeScript, FastAPI, PostgreSQL; карта всех экранов, модель данных, API и пакеты мультиагентной разработки.

**Реализация приложения** — `apps/web` (React) и `apps/api` (FastAPI), общие контракты и Studio — `packages/`. [Запуск и проверки](infra/README.md), [фактический прогресс и ограничения](docs/implementation/progress.md). После установки зависимостей и запуска локальной БД/API: `pnpm dev`, интерфейс — `http://127.0.0.1:5174`. Демонстрационный контур: https://www.odschool.ru/deti-marii/ — отдельная staging-база с вымышленными данными. Серверная проверка записи продолжается; статус — в журнале прогресса.

Материалы и постановка задачи — в [`materials/`](materials/README.md).

**Путь кандидата** «анкета → кабинет → выбор времени встречи и знакомство с фондом параллельно → встреча с координатором» — в прототипе «Опора»: `prototype/Apply.dc.html`, `Onboarding.dc.html`, `ApplicationStatus.dc.html`. Тексты правятся в `prototype/content/`, после правки — `python3 scripts/build_prototype.py`. Координатор видит анкеты и прогресс в `Candidates.dc.html`, встречи и доступность — в `Interviews.dc.html`. Старые ссылки `prototype/index.html#/…` переводят в тот же интерфейс; сохранённые ответы переносятся. Подробнее — [prototype/README.md](prototype/README.md).

Прототип «Опора» и все сохранённые артефакты его подготовки — в [`materials/04-дизайн/прототип-до-фактуры/`](materials/04-дизайн/прототип-до-фактуры/README.md). [Интерактивный холст Claude Design](https://claude.ai/artifact/KeurJ9hsWHTx9g8ovz512u).

**Расширенный прототип «Опора»**: [расписание, роли, участники и группы](prototype/README-opora.md). Открывается через `prototype/Main.dc.html`; исходники в `prototype-src/`. Анкета и онбординг — экраны `Apply`, `Onboarding`, `ApplicationStatus`.
