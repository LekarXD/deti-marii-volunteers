# База данных и доменные правила

Это проект схемы для PostgreSQL, а не уже созданные миграции. Названия согласовать в P00; последующие агенты используют эти сущности через доменные сервисы.

## Общие соглашения

- UUID — идентификатор сущности. Email, телефон, имя и Telegram меняются независимо от identity; нормализованный контакт не подменяет `user_id`.
- `created_at`, `updated_at`, автор изменения и `version bigint` у редактируемых агрегатов. Фактическое время — `timestamptz`, часы работы — целые минуты. Даты рождения/локальных повторений — `date`, не UTC timestamp.
- Один фонд в первой установке. `foundation_id` у ресурсов и staff membership; программа/группа — дополнительные scopes. Сквозные FK/проверки не позволяют связывать ресурсы разных scopes. Разработка полноценного SaaS multi-tenancy в этот объём не входит.
- JSONB — для версий анкет, блоков контента, raw import и входов/выходов jobs. Участия, роли, составы и права — нормализованные связи, не массивы UUID внутри JSON.
- История контактов/статусов/часов append-only. Архивирование не удаляет факты. Удаление/анонимизация по политике оформляется отдельной командой; `deleted_at` не заменяет её.
- У всех списков индексы под scope и сортировку: например `(foundation_id, status, created_at, id)`. Контакты, токены и заметки не попадают в универсальный полнотекстовый поиск.

## Границы хранения и реализации

Список ниже — карта доменных данных, а не требование создавать отдельный framework/repository/interface на каждую строку. Один конкретный SQLAlchemy service на агрегат и общая транзакция достаточны; дополнительные абстракции вводятся при втором реальном потребителе. Не создавать generic CRUD/UoW framework поверх SQLAlchemy Session. JSONB подходит для небольшого immutable snapshot, не требующего независимых прав, поиска или жизненного цикла.

Единственные источники истины: session/authz — P01, asset/upload/job — P01, приглашение/подтверждение — assignment P09, lesson draft/version/publication — P14, запись/render — P18C. Доменные adapters используют эти сервисы, не заводят вторые очереди, таблицы файлов или состояния публикации.

## Таблицы

### Identity, доступ и анкеты

| Таблица | Ключевые поля и связи |
|---|---|
| `users` | `id`, `foundation_id`, `display_name`, `account_state`, `version`, `authz_version` для событий изменения grants/сессий |
| `contact_channels` | `user_id`, `type`, `normalized_value`, `verified_at`, `is_primary`, preferences; уникальность подтверждённой login identity по выбранной политике |
| `auth_challenges` | hash одноразового кода/токена, назначение, контакт, expiry, attempts, consumed_at; открытый токен не хранить |
| `sessions` | hash opaque идентификатора, ровно один user или registration scope, expiry, revoked_at, auth assurance/MFA time; текущие grants читаются из БД |
| `registration_sessions` | anonymous draft/submission scope, expiry, contact verification state; без доступа к существующему user по одному email |
| `staff_memberships`, `permission_grants` | сотрудник, permission, foundation/program/group scope, revoked_at; техническое администрирование отдельно от чтения закрытых заметок |
| `volunteer_profiles` | `user_id UNIQUE`, interests, biography, preferences, lifecycle; справочники навыков/интересов связаны через join tables |
| `profile_change_suggestions`, `profile_revisions` | AI diff, source run, proposed/accepted/rejected/reverted, expected profile version, applied/reverted revision; история ручных изменений сохраняется |
| `form_versions` | schema версии формы, published_at, immutable content |
| `application_drafts` | owner user/registration, form_version, answers JSONB, version; один текущий draft на owner |
| `applications` | owner, submitted_revision_id, submitted_at, submission_state, review_state, assigned_coordinator_id |
| `application_revisions` | application, form_version, immutable answers snapshot, author, created_at; revision number UNIQUE внутри application |
| `consent_events` | subject, документ/версия, цель, grant/revoke, время, источник; согласие на новости отдельно от необходимых условий |
| `audit_events` | actor, command, entity type/id, changed field names, request_id, время; чувствительное содержимое не дублировать в обычных логах |

Поисковая проекция анкеты отдельно извлекает согласованные поля из submitted revision. Обновление контакта/ответов не создаёт нового волонтёра и не сбрасывает подготовку. Если новая редакция меняет значимые для роли условия, координатор видит отдельную задачу перепроверки, а не скрытый автоматический отказ.

### Подготовка и обучение

| Таблица | Ключевые поля и связи |
|---|---|
| `learning_tracks`, `learning_releases` | назначение трека, immutable опубликованная версия, applicability policy |
| `lessons`, `lesson_versions`, `lesson_blocks` | stable lesson ID и mutable draft с revision; immutable published snapshots/blocks с media references; current publication pointer и отдельный publication revision |
| `learning_assignments` | user, release, роль/программа, assigned_at, status |
| `lesson_progress` | assignment, lesson_version, completion/acknowledged_at; UNIQUE пары |
| `assessment_versions`, `assessment_questions` | версия теста, questions; answer key в закрытых server schemas/хранилище |
| `assessment_attempts`, `assessment_answers` | user, version, started/submitted/scored, answers, server score, feedback; UNIQUE attempt/question |
| `policy_acknowledgements` | user, policy_version, acknowledged_at |
| `preparation_requirements` | owner role/opportunity, вид, mandatory/recommended, order-independent policy, version |
| `preparation_reviews` | user, requirement_version, pending/fulfilled/waived, evidence_asset_id, author/reason |

История прохождения привязана к версии, а не текущему тексту страницы. Новый release задаёт `reacknowledgement_required` и набор изменённых обязательных пунктов; уже полученные часы и attendance не пересчитываются. Тест знакомства фиксирует завершение и результат без проходного процента. Прогресс обучения не является условием бронирования собеседования; состояния анкеты, знакомства и встречи независимы. Для иных курсов могут быть отдельные явно заданные правила.

### Собеседования

| Таблица | Ключевые поля и связи |
|---|---|
| `interview_availability_series` | coordinator, local start date/time, end time, timezone, recurrence, duration_minutes, buffer_after_minutes, active, last_date, version |
| `interview_availability_exceptions` | series + origin_local_date/time, skip/override, replacement interval; UNIQUE origin |
| `interview_slots` | series, origin key, effective start/end, coordinator, location/join reference, status, version; уникальный экземпляр |
| `interview_bookings` | candidate, slot, status, scheduled start/end snapshot, coordinator, public venue, version |
| `interview_booking_events` | booking, тип действия, before/after время и автор, reason, created_at |
| `interview_results` | booking UNIQUE, outcome, public_agreement, next_task_id, author |
| `interview_private_notes` | booking, author, private text; только закрытые staff DTO |
| `candidate_requests` | candidate, kind `alternate_time/question`, text, owner, state, response, responded_at |

В первой версии перерыв — после встречи. Следующая встреча начинается не раньше `end + buffer_after`. Если нужны перерывы до встречи, добавить отдельную policy, не менять скрытно смысл диапазона.

Окна могут пересекаться как черновики, но опубликованная доступность одного координатора проверяется на конфликт. Закрытие свободного окна не отменяет уже назначенные встречи. Если меняются время/длительность/место занятого интервала, API возвращает affected bookings и требует сначала перенести их либо выполнить явно подтверждённую команду пересогласования.

### Роли, возможности и календарь

| Таблица | Ключевые поля и связи |
|---|---|
| `programs`, `locations` | программа, площадка/online, timezone, адрес и публичная инструкция |
| `volunteer_roles`, `volunteer_role_versions` | название, tasks, preparation defaults, active/archive; normalized title unique среди активных в фонде |
| `opportunities` | role/program, аудитория, задачи, условия, регулярность, policy согласования, draft/published/paused/closed |
| `opportunity_role_links` | возможность ↔ одна или несколько ролей; условия конкретной возможности имеют snapshot/version |
| `event_series` | local datetime, timezone, duration, recurrence rule, last_date, template, version |
| `event_occurrences` | series или standalone, origin key, effective start/end, статус, место, version |
| `occurrence_overrides` | origin occurrence, изменённые поля/отмена; не теряет происхождение при переносе |
| `staffing_needs` | occurrence, role_version, capacity_required, условия подготовки, approval policy, version |
| `opportunity_responses` | volunteer, opportunity, state, coordinator decision/reason, timestamps |
| `assignment_events` | история invite/reinvite/approve/confirm/decline/expire/cancel с автором и причиной; доставка приглашения в P17, отдельная stateful таблица invitations не нужна |
| `assignments` | volunteer, occurrence, staffing_need, approved_at, confirmed_at, status, conditions_version |
| `resource_reservations` | user, source type/id, busy range, active; общая защита от пересечений встреч и подтверждённых занятий |

Роль ≠ staff permission. `photographer` означает задачу на мероприятии, не административный доступ. Координатор может иметь несколько ролей аккаунта и одновременно быть волонтёром; разные оси состояния это допускают.

Повторения: once, weekly с несколькими днями, каждые 2 недели, monthly. Хранить структурированное правило или валидированный RRULE subset, не произвольный исполняемый текст. Выбранная политика для 29–31 числа: пропуск отсутствующей даты, без неявного переноса на последний день; изменить можно явным правилом фонда. Проверить високосный год и DST для поддерживаемых timezone, даже если исходная площадка в Москве.

Материализовать на скользящий технический горизонт, например 6 месяцев, и достраивать запрошенные диапазоны. UI не ограничивается этим горизонтом. Для очень большого диапазона — асинхронное расширение, cursor/page и ясное pending состояние, не бесконечный синхронный расчёт.

`origin_local_date/time` остаётся неизменным при переносе. Изменение «только эта дата» создаёт override; «вся серия» пересчитывает затронутые будущие экземпляры с сохранением существующих override/отмен и истории. «Эта и последующие» — отдельная команда split series, если включена в согласованный UI; не трактовать её как «вся серия».

### Участники, сопровождение и учёт

| Таблица | Ключевые поля и связи |
|---|---|
| `participants` | имя для показа, birthday/year policy, lifecycle, публичная карточка |
| `participant_briefings` | communication/support/interests, версия, область видимости |
| `participant_private_notes` | закрытая заметка, автор; отдельная проекция и permission |
| `media_assets`, `participant_media_permissions` | storage key, type/size/checksum, scan/processing state, область разрешённого использования |
| `groups`, `group_memberships` | группа и участник, valid_from/until; запрет дублирующих активных периодов одной пары |
| `occurrence_group_links`, `occurrence_participants` | группа/уточнённый состав конкретного занятия; история состава не перезаписывается текущим списком |
| `availability_rules`, `availability_verifications` | доступность волонтёра, timezone, valid_until/verified_at, источник и автор проверки |
| `contact_events`, `agreements`, `follow_up_tasks` | история связи/договорённостей, ответственный, due_at, open/done/cancelled |
| `reserve_reviews` | контакт, результат проверки, актуальность доступности, next_task, no-contact preference. С 2026-10-22 не используется (проверка контактов удалена); таблица остаётся до решения фонда о персональных данных |
| `attendance_records` | assignment UNIQUE, attended/absent, actual minutes, approver, version |
| `service_time_entries` | user, source attendance/manual review, signed delta_minutes, reason, unique command source; append-only ledger |
| `manual_time_requests`, `certificates` | запрос часов и решение; документ с периодом, числом подтверждённых минут, asset/job и проверочным идентификатором |
| `first_visit_checklists` | assignment, checklist version, completion; памятка собирается по occurrence и briefing |
| `reflections`, `reflection_reviews` | assignment, добровольные ответы/настроение/помощь/продолжение, review и next_task |

Публикуемые памятки и частные заметки физически разделены. Нельзя считать приватным поле, которое сервер отправил и frontend просто не нарисовал. Фото хранится как asset, не base64; менять ссылку только после успешной обработки нового файла.

### Добро.рф: ручная копия подтверждённых часов

Дополнение от 22 октября описывает фактические модели `apps/api/app/modules/dobro/models.py` (интеграционный срез `88fc82e`), а не generic `external_*` из исходного продуктового дополнения. Identity, attendance, ledger, jobs и receipts остаются общими. Добро не пишет в `service_time_entries`, не начисляет минуты и не даёт допуск к занятиям.

| Модель / таблица | Поля и ограничения |
|---|---|
| `DobroActivityLink` / `dobro_activity_links` | `id`, `foundation_id`, `opportunity_id`, `url`, `kind=long_term/one_off`, `title`, `valid_from/until`, `version`, `actor_id`, `created_at`; scope FK к возможности, непересекающиеся включительные периоды одной возможности через GiST exclusion. Ссылка принадлежит возможности, не роли |
| `DobroSeriesOpportunity` / `dobro_series_opportunities` | `series_id` PK, `foundation_id`, `opportunity_id`, `version`, `actor_id`; scoped FK к серии и возможности. Явная атрибуция ledger-фактов; смена возможности после появления фактов запрещена |
| `DobroProfile` / `dobro_profiles` | `user_id` PK, `foundation_id`, `profile_url`, `version`, `updated_by/at`; scoped FK к User. Свой профиль меняет волонтёр, профиль связанного CRM-пользователя — уполномоченный координатор |
| `DobroEnrollment` / `dobro_enrollments` | `id`, `foundation_id`, `user_id`, `activity_id`, `state=none/applied/approved/not_needed`, `version`, `updated_at`; UNIQUE `(activity_id,user_id)`, scoped FK к User и activity |
| `DobroEnrollmentEvent` / `dobro_enrollment_events` | `id`, `enrollment_id`, `version`, `state`, `actor_id`, `reason`, `created_at`; UNIQUE `(enrollment_id,version)`, append-only история переходов |
| `DobroTransfer` / `dobro_transfers` | `id`, `foundation_id`, `user_id`, `activity_id`, `period` (первое число месяца), `minutes_due_snapshot`, ненулевой signed `hours_delta`, `snapshot_hash`, `snapshot` JSONB, `actor_id`, `note`, `entered_at`; scoped FK, append-only запись ручного подтверждения. Несколько частичных внесений/коррекций за период допустимы; идемпотентность через общие mutation receipts, а не UNIQUE на период |
| `DobroSettings` / `dobro_settings` | `foundation_id` PK, `organization_url`, `registration_url`, `verified`, `monthly_day` (1–28, default5), `hard_deadline_days` (1–365, default60), `risk_days` (1–60, default7), `whole_hours` (хранимая policy, расчёт сейчас целочасовой), `rules_confirmed`, `reminders_enabled`, `reminder_owner_user_id`, `reminder_template`, `version`, `updated_by`; включённые напоминания требуют владельца того же фонда |

Расчёт читает завершённые attendance-источники общего ledger и их signed corrections, привязывает их к возможности через серию и периоду ссылки. В `Europe/Moscow` минуты ограничиваются длительностью занятия, пересечения исключаются детерминированно (start, затем assignment UUID), бюджет по связанным добрым делам — 480 минут на человека в сутки. По activity/user накапливаются допустимые минуты до конца выбранного месяца: целевой итог `floor(minutes/60)`, остаток `%60`, к переносу — целевой итог минус сумма всех `hours_delta`. Уменьшение ledger даёт отрицательную коррекцию; история более позднего переноса делает старый период только читаемым. Непривязанные и ручные ledger-факты автоматически в Добро не включаются.

`mark-entered` после fresh authz берёт foundation lock и общие ledger subject locks, заново вычисляет snapshot и проверяет его hash. При изменении источников —409 с повторной сверкой. Команда подтверждает только выполненную вручную работу, сохраняет signed delta и при `applied` атомарно записывает `approved` + событие. Исправление требует новой записи, отрицательное — причины; update/delete истории запрещены DB-trigger. Неиспользованную ссылку можно менять с CAS; после ledger/enrollment/transfer её атрибуция защищена. Подробные команды и граница внешних правил — в [API](api-and-frontend.md#доброрф-ручной-перенос-часов).

### Коммуникации, знания, AI и эксплуатация

| Группа таблиц | Назначение |
|---|---|
| `conversations`, `conversation_members`, `messages`, `message_assets`, `read_cursors` | внутренние диалоги, история и непрочитанное |
| `notification_preferences`, `notification_templates`, `notification_deliveries`, `delivery_attempts` | отдельные события и попытки внешней доставки, verified channel identity |
| `knowledge_sources`, `source_versions`, `knowledge_chunks`, `knowledge_questions`, `approved_answers` | опубликованная библиотека, ссылки на фрагменты, очередь неизвестных вопросов |
| `simulator_scenarios`, `rubric_versions`, `simulation_sessions`, `simulation_turns`, `simulation_evaluations`, `evaluation_appeals` | тренировка и пересмотр оценки |
| `ai_runs`, `match_runs`, `match_suggestions` | model/prompt/rubric/source versions, разрешённый input, output, usage/cost, coordinator decision |
| `signals`, `signal_events` | предмет сигнала, scope, ответственный, state, reason и следующее действие |
| `webinars`, `webinar_enrollments`, `rtc_rooms`, `board_sessions`, `webinar_summaries` | доступ к комнате/общей доске, provider IDs и версионированные итоги; запись live использует те же projects/takes/renders P18, без второй таблицы recordings |
| `import_batches`, `import_rows`, `merge_reviews`, `import_effects` | исходные строки, mapping, dry-run/errors, provenance, ручные дубли, обратимость. С 2026-10-22 импорт удалён; `merge_reviews` по-прежнему пишет слияние дублей, таблицы импорта (и `import_external_references`) остаются без записи до решения фонда о персональных данных |
| `report_exports`, `integration_connections`, `settings_versions` | экспорт и настройки; secrets только refs во внешнее хранилище/окружение |
| `idempotency_records`, `outbox_events`, `jobs` | повторяемые команды, durable события, lease/retry/dead-letter |

Полнотекстовый поиск начать со средств PostgreSQL. Векторный поиск — отдельный adapter/index только при измеренной необходимости для Knowledge; pgvector не нужен для обычной анкеты, CRM или matching.

## Независимые состояния

| Агрегат | Переходы |
|---|---|
| Анкета | `draft → submitted → withdrawn`; review отдельно `new → reviewing → discussed/closed`, с явным reopen |
| Подготовка | по каждому requirement: `pending → fulfilled/waived`; waiver требует permission, автора и причину |
| Тест | `started → submitted → scored`; результат не означает допуск к любой роли |
| Встреча | `booked → completed/cancelled/missed`; reschedule меняет время и версию той же записи |
| Результат встречи | `first_visit / further_discussion / another_role / pause / finish`; отдельный next task |
| Возможность | `draft → published ↔ paused → closed`, reopen отдельной командой |
| Роль | `active ↔ archived`, история назначений сохраняется |
| Занятие | `scheduled → completed/cancelled`, restore только с повторной проверкой конфликтов |
| Отклик | `submitted → under_review → approved/declined/withdrawn` |
| Назначение | `invited → confirmed/declined/expired/cancelled`; факт отдельно `attended/absent` в attendance |
| Рефлексия | `draft → submitted → reviewed`; отказ отвечать не отменяет факт участия |
| Резерв | `unverified → contacted → awaiting_reply → ready/paused/unavailable/unreachable` |
| Доставка | `queued → provider_accepted → delivered/failed/unknown`; внутренний inbox отдельно от внешнего канала |

`candidate_stage` для списка — производная проекция этих фактов. Это не master enum, из которого автоматически переписываются обучения, встречи и участия.

## Критические ограничения PostgreSQL

Иллюстрация обязательных ограничений, не готовая миграция:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE UNIQUE INDEX interview_one_active_per_candidate
  ON interview_bookings (candidate_id) WHERE status = 'booked';

CREATE UNIQUE INDEX occurrence_origin_unique
  ON event_occurrences (series_id, origin_local_date, origin_local_time)
  WHERE series_id IS NOT NULL;

ALTER TABLE resource_reservations ADD CONSTRAINT user_time_no_overlap
  EXCLUDE USING gist (user_id WITH =, busy_range WITH &&) WHERE (active)
  DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE assignments ADD CONSTRAINT one_place_per_person_per_event
  UNIQUE (occurrence_id, volunteer_id);
```

В `resource_reservations` также обязательны `CHECK(NOT isempty(busy_range))`, запрет бесконечных границ, диапазон `[start,end)`, уникальная source/user связь. На встречу создаются две reservations: координатор с buffer и кандидат на фактическое время. На confirmed занятие — reservation волонтёра. Это защищает и пересечения между интервью и занятиями; два независимых индекса по разным доменным таблицам этого не обеспечивают.

Дополнительно: `end > start`, capacity > 0, duration > 0, minutes >= 0 для факта; signed minutes допустимы только в корректировочном ledger. FK не дают удалять историю. Capacity нельзя защитить обычным row CHECK с подсчётом дочерних записей: нужна транзакционная блокировка staffing need и повторная проверка в сервисе.

## Алгоритмы транзакций

Для команд, пересекающихся с отзывом доступа, сначала authz guard из [API-контракта](api-and-frontend.md), затем доменные locks. Общий порядок блокировок для всех конфликтующих команд: parent series/availability window (тип+UUID по возрастанию) → occurrence/slot → staffing need → booking/assignment → user rows для reservations (UUID по возрастанию). Редактирование и подтверждение используют одинаковые границы блокировки; при переносе блокируются и старые, и новые parents/slots. Исходные ссылки можно прочитать без lock для определения набора, затем после захвата parent locks повторно проверить ссылки/версию; изменение набора означает rollback/retry, а не продолжение с устаревшим набором. Deadlock/serialization errors обрабатывать ограниченным retry идемпотентной команды, не бесконечным циклом.

Материализация слотов/занятий тоже берёт lock соответствующей series, читает её текущую version и делает idempotent insert по origin key. Иначе worker может вернуть отменённые/устаревшие экземпляры после series edit. Для standalone occurrence родителем является сама occurrence; внутри каждой категории все UUID сортируются, включая старую и новую стороны переноса. При изменении времени серии сначала захватывается полный набор затронутых reservations/users, затем выполняются обновления. Для массового сдвига, при котором промежуточные диапазоны пересекаются, exclusion constraint объявляется DEFERRABLE и проверяется перед commit; одинарные бронирования оставляют immediate проверку. Большой пересчёт выполняется job с тем же протоколом и версионным preview, а не удерживает HTTP-транзакцию во время ожидания человека.

`assignments.staffing_need_id` должен ссылаться на need именно этой occurrence (composite FK по need ID + occurrence ID). Активное назначение одного человека на занятие одно; повторное приглашение изменяет тот же aggregate с event history. `resource_reservations` хранит ровно одну ссылку на booking либо assignment с FK и CHECK XOR вместо непроверяемой polymorphic source string. Source/user unique и exclusion работают вместе.

Обязательные парные race tests: materializer vs series edit; attendance vs cancel/time edit; availability edit vs booking; capacity/time edit vs confirmation; series edit vs перенос отдельной даты; два переноса с пересекающимися ресурсами.

### Бронирование и перенос

1. Проверить сессию, ownership и scope; получить/заблокировать idempotency record по `(actor, operation, key)`, сравнить hash payload.
2. Определить старый и новый parent/slot по предварительному чтению, захватить locks в общем порядке, затем заблокировать booking и проверить ссылки/`expected_version`.
3. Заново проверить future time, опубликованную доступность, право текущей регистрационной сессии/подтверждённого контакта и отсутствие другой активной записи кандидата. Завершение знакомства и теста здесь не проверяется.
4. Обновить booking и reservations в одной транзакции, сохраняя before/after event. При ошибке exclusion/unique — rollback всей транзакции: старая встреча остаётся.
5. Создать outbox `interview.booked/rescheduled`, записать result идемпотентной команды, commit. Только после commit worker готовит уведомления.

### Подтверждение участия

Lock parent series/occurrence → staffing need → assignment/user rows в общем порядке → проверка версии условий/готовности → подсчёт confirmed assignments → проверка capacity → insert/update assignment и user reservation → audit/outbox → commit. При приглашении место не резервируется бессрочно. Если нужен временный hold, это новая явная policy с expiry и отдельным state, не скрытый эффект approve.

### Факт и минуты

Lock parent series/occurrence → staffing need → assignment → attendance (в том же порядке, что изменение/отмена занятия) → проверить роль утверждающего и завершение занятия → upsert attendance с version → append уникального ledger delta → outbox → commit. Повтор команды не добавляет минуты снова. Исправление ранее подтверждённых 180 на 120 минут создаёт delta −60 с причиной, а не удаляет историю.

### Изменение серии

Lock series/version → затронутые occurrences/needs/assignments по общему порядку → вычислить затронутые будущие origin instances → подготовить preview конфликтов/подтверждений → по подтверждённому preview hash применить override/reconfirmation policy → не трогать завершённые факты → outbox на действительно изменившиеся назначения. При новом конфликте после preview вернуть 409; preview не является вечной блокировкой.

Повторная отправка использует тот же idempotency key и payload. Иной payload с тем же ключом возвращает конфликт. Авторизация выполняется до выдачи сохранённого результата, чтобы отозванное право не обходилось через idempotency cache.

## Миграции, seed и импорт

Один владелец Alembic: интегратор/агент A1. Доменные агенты согласуют model/schema delta, но не создают конкурирующие heads и не редактируют чужие applied migrations. Базовая схема строится этапами, минимальные общие IDs/FK фиксируются до параллельных доменов.

Демо-данные генерируются отдельно и не попадают в production. `roles.json` нужно разделить на справочник ролей и предложения по программам; не заливать файл одной таблицей. Фиксированную дату октября 2026 и legacy IDs не использовать в логике сервера. Исходные методические документы импортируются как источники/черновики с provenance и отдельной публикацией.

Миграция схемы и импорт фактической базы — разные процессы. Импорт CSV/XLSX сначала создаёт batch/rows, затем dry-run и preview дублей. Применение фиксирует `source + external_id`/checksum, row effects и очередь проверки. Объединение дублей меняет связи транзакционно, хранит alias/provenance и требует ручного решения при сомнении. Не откатывать импорт каскадным удалением записей с новым реальным участием. Импорт контактов удалён 2026-10-22 (волонтёры регистрируются сами); миграция удаления таблиц импорта и `reserve_reviews` ждёт решения фонда об уничтожении персональных данных.

Старый localStorage можно конвертировать только в dev fixtures или отдельный явно разрешённый разовый импорт. Клиентскому `done`, `best`, роли staff и начисленным часам не доверять как production-факту.

## Дополнение студии и записи уроков

К P18 добавляются `recording_projects`, `studio_capture_sessions`, `recording_takes`, `recording_source_files`, `recording_stage_events`, `recording_render_versions` с immutable manifest JSONB/hash, `recording_reviews`, `recording_publications`, `slide_decks` и их immutable versions/pages. Поля, независимые состояния и commands описаны в studio-recording.md.

Запись связывается с project/session/take/generation и manifest hash. Единственный активный take проекта защищён partial unique constraint и idempotency start/stop; CAS/fencing запрещают старому worker/webhook менять новую попытку. Approval относится к конкретному render hash; publish проверяет draft revision и publication revision stable lesson, создавая новую immutable lesson version; повтор команды не создаёт второй video block. Ready asset не означает опубликованный урок. Raw fallback при privacy failure блокируется.

Реализации receipts, paging, leases, source provenance и scoped cache из Общего Дела используются как reference инвариантов и тестов. RPC/PostgREST repository заменяется SQLAlchemy/UoW при сохранении атомарного SQL. Не превращать транзакционную исходную команду в SELECT-then-UPDATE в Python. История сотен чужих migrations не копируется в схему фонда.
