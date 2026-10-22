# Данные фонда для стенда «Опоры»

`fund-content.json` — публичные данные «Детей Марии»: площадки (10), направления (5) и программы (6), роли (20), группы без участников (2), возможности (11), события 23.10–15.12.2026 (11, это 17 записей EventSeries), окна собеседований (2), примеры призов (4), материалы библиотеки (7), список «не загружать» (7). У каждого элемента есть `source`. Всё, что выведено, помечено `"inferred": true` с причиной в `inferred_why`. Имён, почт и телефонов людей нет. Пути в `file:строка` ниже даны от `apps/api/app/`.

## Куда ложится каждый раздел

| Раздел JSON | Модель / helper |
|---|---|
| `places` | Отдельной модели нет. Строка `location` → `EventSeries.location`, `Opportunity.location`, `ParticipantGroup.location`, `AvailabilitySeries.venue` |
| `directions`, `programs` | Таблицы нет. Название программы → `Opportunity.program` / `EventSeries.program`. `VolunteerRole.direction` принимает только направления анкеты (`modules/activities/directions.py:25-30`) |
| `roles` | `VolunteerRole` (`modules/activities/models.py:16-27`) через `activities.create_role(db, actor, RoleCreate(...))` (`schemas.py:30`, как в `stage_demo/dataset.py:121-122`). `preparation_defaults` — это ссылки на `preparation_presets`, развернуть в `PreparationRequirement` (`schemas.py:15`) |
| `opportunities` | `Opportunity` (`models.py:53`): `create_opportunity` + `change_opportunity_state(..., 'published')` (`dataset.py:125-126`). `state: draft` не публиковать |
| `events` | `calendar_service.create_series(db, actor, EventSeriesCreate(...))` (`calendar_schemas.py:35-49`, вызов в `dataset.py:131`). `recurrence` → `RecurrenceRule` (`:9`, пн=0), нужды → `StaffingNeedInput` (`:26`), роль искать по `role_title`. Каждый элемент `parts` — отдельная серия `once`. Серия разворачивается на 183 дня вперёд (`calendar_service.py:193`) |
| `groups` | `ParticipantGroup` (`modules/participants/models.py:60`), без `Participant` |
| `interview_windows` | `AvailabilitySeries` (`modules/interviews/models.py:9`, поля как у `WindowInput` в `schemas.py:7`). Пропуск 4.11 → `AvailabilityException(kind='skip')` (`models.py:32`). Слоты создаются сами при чтении (`interviews/service.py:103-113`) |
| `prizes` | `Prize` (`modules/profile/models.py:178`) через `profile.prizes.create_prize` (`prizes.py:34`, `PrizeCommand` в `schemas.py:236`) |
| `knowledge` | `KnowledgeSource` (`modules/knowledge/models.py:9`): `create_source` → `review_source` → `publish_source` (`knowledge/service.py:56/106/115`). Публикация ставит в очередь задачу индексации. Текст брать из `body_from` |

Справочно: `dataset.py` не создаёт ни призов, ни шаблонов уведомлений (`NotificationTemplate`, `notifications/models.py:28`). Шаблоны мы тоже не готовили: в материалах для них ничего нет.

## Ограничения текущего seed

- Повторный запуск `seed` не загружает ничего нового. Если marker есть — `already_seeded`, если нет — команда требует пустую базу (`stage_demo/operator.py:72-73`):
  `if await db.scalar(select(func.count()).select_from(User)):` / `raise RuntimeError('First seed requires an empty newly created staging account database')`
- Guard по имени фонда (`operator.py:57-58`). Его проходят все команды `stage_demo`, включая `passwords`:
  `other = await db.scalar(select(Foundation.id).where((Foundation.id != foundation_id) | (Foundation.name != FOUNDATION_NAME)).limit(1))`
  `if other: raise RuntimeError('Refusing a database with another foundation or non-demo name')`
  `FOUNDATION_NAME = 'Опора — демонстрационный контур (вымышленные данные)'` (`operator.py:13`). **`Foundation.name` не переименовывать.**
- `dataset.py:1-2` и `docs/implementation/stage-demo-fixtures.md` называют стенд контуром с вымышленными данными. Реальный контент фонда на стенде должен одобрить владелец проекта. Вымышленные `[ДЕМО]`-роли и события из базового seed останутся: названия не совпадают, поэтому уникальный индекс `uq_active_role_title` не мешает.

## Как загрузить (рекомендация)

1. Новый модуль `app/stage_demo/fund_content.py` по образцу `stage_demo/passwords.py`. Порядок: `validate_runtime` → `database_guard` → проверить marker базового seed `('stage-seed:<fid>', 'stage.demo.seed', SEED_KEY)` → `pg_advisory_xact_lock` → проверить свой marker `MutationReceipt(actor_id='stage-fund-content:<fid>', operation='stage.fund.content', key='opora-stage-fund-content-v1')`. Если свой marker уже есть, вернуть `already_loaded`.
2. Действовать от имени демо-координатора: `BootstrapActor(coordinator_id, fid, frozenset(grants))` (`dataset.py:18-28, 77, 85`). Писать через service-helpers, как в `dataset.py`, а не через `db.add`: так появятся версии ролей и серий. Плейсхолдер `{introduction_release_id}` заменить на `LearningTrack(key='introduction').current_release_id`. Перед созданием проверять, есть ли уже такая запись: роль по `normalized_title`, серия по `title` + `start_date`, приз по `title`. Всё делать одной транзакцией вместе с marker.
3. JSON положить в релиз рядом с модулем (`app/stage_demo/fund_content.json`), монтировать ничего не нужно. Запуск по образцу `docs/implementation/stage-demo-fixtures.md:47-55`:
   `docker compose --project-name opora-preview --env-file /opt/odschool/opora-preview/private/runtime.env -f /opt/odschool/opora-preview/releases/<ПОЛНЫЙ_SHA>/infra/preview/compose.yml exec -T -e OPORA_STAGE_FIXTURE_SEED_ALLOW=true api python -m app.stage_demo.fund_content --confirm ONLY_SYNTHETIC_OPORA_STAGE`
4. Не загружать то, что перечислено в `not_to_load`: имена людей, историю участника, фото, книги, внутренние пометки, имя фонда. Возможности с `state: draft` создавать черновиками. События с `confidence: низкая` (декабрьские ярмарки) — по решению владельца.

## Как открыть ленту для volunteer1..3@example.test

Ленту закрывает `sign_up_gate` (`modules/activities/assignment_service.py:106-115`). Она открыта, если: профиль не на паузе (`VolunteerProfile.lifecycle != 'paused'`) **и** есть либо `Assignment.confirmed_at`, либо `InterviewBooking.status == 'completed'`. Подбор у координатора проверяет то же (`ranking.py:104-113`, `exclusion`) и дополнительно убирает тех, у кого `area == 'Другой город'`, с очных событий.

У volunteer1..3 анкет нет (`stage-demo-fixtures.md:137-140`), а `InterviewBooking.application_id` обязателен. В том же модуле для каждого из них:
1. `Application(user_id, submission_state='submitted', review_state='discussed')` + `ApplicationRevision(answers=validate_answers(..., complete=True, form=form.content))` + `submitted_revision_id`, как в `dataset.py:91-100`. `area` — не «Другой город».
2. Прошедшее окно `AvailabilitySeries(recurrence='once')` → `InterviewSlot` в прошлом → `InterviewBooking(status='completed', candidate_key=f'user:{id}', ...)` → `InterviewResult(outcome, public_agreement, author_id=координатор)` → `BookingEvent(kind='completed')`. Модели: `interviews/models.py:42, 57, 98, 88`. `reserve()` не вызывать: завершённая встреча время не держит (`interviews/router.py:217`).

Другой путь — через интерфейс: волонтёр отправляет анкету и записывается на ближайший слот, а координатор после начала встречи нажимает «Завершить». Раньше начала встречи `finish` её не закроет (`interviews/router.py:197`).
