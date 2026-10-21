# Мультиагентная реализация

## Правила команды

Один интегратор A0 и максимум 8 исполнителей A1–A8 одновременно. Агент получает пакет с конкретной областью файлов, входными контрактами и приёмкой. После сдачи пакета его слот можно использовать для следующего. Наличие свободного слота не означает, что можно начать зависимую задачу до фиксации её API/схемы.

| Агент | Основная область |
|---|---|
| A0 Интегратор | reference snapshot, архитектурные решения, контракты, router wiring, интеграция, финальная приёмка |
| A1 Платформа и БД | auth, permissions, DB/migrations, worker/outbox; затем доставка сообщений и интеграции |
| A2 UI foundation и Studio | tokens, primitives, layouts, верхняя навигация, Storybook; затем shared stage, recorder и solo UI |
| A3 Кандидаты и CRM | анкета, очередь кандидатов, профили/резерв/импорт; затем часы, отчёты и admin UI |
| A4 Интервью и интерактивные сервисы | доступность/бронирование, затем live Studio и тренажёр после освобождения слота |
| A5 Занятия и участие | роли, возможности, календарь, потребности, приглашения, подтверждения и attendance |
| A6 Участники и сопровождение | группы, карточки/фото, памятка первого выхода, рефлексия и follow-up |
| A7 Обучение и знания | версии онбординга/теста, академия/редактор, источники/наставник и общий AI gateway |
| A8 QA и эксплуатация | independent contract/ACL/race/E2E/visual tests, CI и staging/release checks |

21 основной пакет имеет 27 контрольных задач: P10 разделён на P10A/P10B, P17 — на P17A/P17B, P18 — на P18A–P18E. Это отделяет базу групп от assignments, shared scene от media pipeline и готовый draft от публикации.

Агент A8 участвует с первого контура, не появляется только в конце. Изменения чужого домена передаются владельцу с воспроизведением; QA не исправляет одновременно те же файлы. A2 после стабилизации UI помогает с адаптацией и visual mismatches через согласованные задачи, не меняет доменные решения.

## Владение файлами

- A0: `packages/contracts/**`, `apps/web/src/app/router.tsx`, root workspace/lockfiles, общий registry API, orchestration scripts, source mapping. Доменные роуты подключает через exports без самостоятельного дописывания бизнес-логики.
- A1: `apps/api/app/core/**`, `apps/api/migrations/**`, `apps/api/app/worker/**`, auth/staff modules, `integrations/{delivery,storage}/**`. Один writer миграций.
- A2: `apps/web/src/api/transport.ts`, query keys/QueryClient, общий upload UI, `packages/design-tokens/**`, `apps/web/src/ui/**`, `apps/web/src/app/layouts/**`, `app/navigation.ts`, Storybook foundations.
- Доменные агенты: только `apps/{web,api}/.../<свой module>/**` и тесты модуля. Models — в домене; migrations delta согласует A1. Связи на другие домены используют зафиксированные IDs/DTO/service interfaces.
- A7: `integrations/ai/**` и knowledge/learning modules; A4 использует gateway, не создаёт второго AI-клиента.
- P18A/D: A2 владеет `packages/studio-core/**`, `ui/studio/**`, `features/lesson-recording/**` и recorder entry. P18B: A4 владеет live webinars/studio module, slide-deck APIs/conversion job handlers и `integrations/rtc/**`. P18C: A1 владеет всем backend recording projects/sessions/takes/renders, media jobs/security, A2 подключает renderer только в своих файлах. P18E: A7 владеет lesson preview/publish/Builder entry interfaces; A2 связывает их с recording UI через отдельную последовательную задачу. Общая геометрия всегда у A2, migrations у A1.
- A8: `tests/{e2e,visual,contract}/**`, `infra/**`, workflows CI по договорённости с A0; A0 объединяет root manifests и dependencies.

Списки routes/permission names, общий header, SDK, migrations, dependency versions и tokens не редактируются несколькими агентами. Изменение общего контракта — отдельный короткий integration commit перед feature-ветками.

Работать в отдельных `codex/<package>` ветках/worktrees от известного интеграционного SHA. Не использовать force push общей ветки. Не включать в коммиты текущие незакоммиченные правки прототипа и реальные файлы фонда без отдельной задачи. `prototype/` и архив — reference; product implementation появляется в новых `apps/` и `packages/`.

## Очередь пакетов

| ID | Владелец | Зависимости | Результат |
|---|---|---|---|
| P00 | A0 | — | reference commit, scope/словарь, decisions, contracts v1 и схема ownership |
| P01 | A1 | P00 | workspace API, БД, migrations, auth/session/permissions, audit, assets base, outbox/jobs |
| P02 | A2 | P00 | UI kit, layouts, верхний header, общие controls, fixtures |
| P03 | A3 | P01/P02 | реальная анкета и кабинет, редактирование без потери истории |
| P04 | A7 | P01/P02 | версии знакомства/теста и API прогресса; без блокировки записи |
| P05 | A3 | P03/P04 | очередь кандидатов, анкета/обзор/история, review и вопросы |
| P06 | A4 | P01/P02 (независимо от завершения P04) | доступность, слоты, booking/move/cancel/outcome обеих ролей |
| P07 | A5 | P01/P02 | роли, возможности, каталог и explainable правила подбора |
| P08 | A5 | P07, group IDs P10A | повторы, календарь, отдельные даты, потребности и редактор |
| P09 | A5 | P06/P08 | отклик/приглашение/согласование/подтверждение, факт участия |
| P10A | A6 | P01/P02 | база участников/групп/assets, membership/leader scope и assignment-access interface |
| P10B | A6 | P10A/P09 | доступ волонтёра по реальным event assignments и safe памятка |
| P11 | A3 | P05 | CRM, история связи, резерв, follow-up и исторический импорт |
| P12 | A6 | P09/P10B/P11 | первый выход, рефлексия, запрос помощи и сигналы |
| P13 | A3 | P09/P11 | минуты, ручные запросы, справки/благодарности и профиль |
| P14 | A7 | P04 | академия, уроки, редактор треков/блоков/тестов и публикация |
| P15 | A7 | P14/P17A | knowledge/editor, Mentor, индекс и общий AI gateway |
| P16 | A4 | P06/P14/P15 | Scenarios, Simulator, оценка/appeal; реальный AI вместо fixtures |
| P17A | A1 | P01/P02 | внутренняя переписка, attachments, read cursors, sync, outbox handlers и delivery contract |
| P17B | A1 | P17A | реальные email/прочие согласованные каналы, templates, preferences, webhooks, broadcast preview |
| P18A | A2 | P01/P02 | извлечённые shared stage/types/geometry, Opora brand, render contracts |
| P18B | A4 | P18A/P17A | live RTC, сцена, слайды/доска, host/audience и права |
| P18C | A1 + A2 renderer | P18B/P14 | Egress/composite, media jobs/checkpoints/transfer и приватный recorder |
| P18D | A2 | P18A/P18C | solo projects/preflight/takes, start/stop/retake и processing UI |
| P18E | A7 + A2 UI | P18D/P14 | приватный preview/review, оформление, publish/version/rollback |
| P19 | A3 | P11/P13/P17B, AI settings P15 | отчёты, администрация, integrations/settings UI, real exports |
| P20 | A8/A0 | P01–P19 | сквозная и визуальная приёмка, staging, restore drill, release/rollback |

`P17A` — отдельная проверяемая задача внутренней переписки/sync и consumer contracts; jobs/assets уже готовы в P01. `P17B` завершает внешнюю доставку. P15/P18B не ждут подключения SMS, весь P17 завершён только после A+B. Реальные broadcast и send webinar summary принимаются после P17B. Общая модель availability volunteer фиксируется контрактом P00/P01; реализация доступности и её проверки относится к P11, собственная форма профиля P13 использует тот же API.

## Что конкретно сдаёт каждый пакет

### P00 Основа и reference

Обязательный reuse inventory Общего Дела — platform-reuse.md и studio-recording.md: зафиксировать source SHA/хеши, dependencies, pure/adapt/new границы и тесты.

Зафиксировать текущие утверждённые экраны, состояние незавершённых UX-правок и версии материалов. Проверить [screen-map.csv](screen-map.csv) против `canvas.json`. Объявить `/apply`, `/application`, `/onboarding`, `/fund/*`, канонический каталог и redirect map. Зафиксировать independent state enums, permission names, IDs, UTC/local time policy, API errors, типы readiness/staffing/booking.

**Приёмка:** 41/41 board имеет назначение; нет молча исключённых Simulator/Studio/Reports. Возраст/справка/правила фото оформлены решениями, а не случайно скопированными frontend-константами. Согласованы schema/API stubs, fixtures и выходной SHA для A1/A2.

### P01 Платформа и БД

Сначала адаптировать готовые auth verification/atomic consume, receipts, jobs/fencing, bounded I/O, cache/error/rate-limit и media drain patterns Общего Дела по platform-reuse.md. Cookie-session revoke/CSRF и staff MFA проверить отдельно: текущий OD JWT/refresh не даёт все эти guarantees.

Создать FastAPI/Python workspace, SQLAlchemy/Alembic, PostgreSQL compose, health/readiness/version endpoints и согласованный error handler. Auth: регистрационная сессия, verified contact, own-user resolution, staff grants/MFA, CSRF/session expiry/revocation, rate limits. Audit и idempotency base. Worker с durable jobs/outbox, leases/retries/DLQ. Asset metadata/private storage adapter и dev seed.

**Приёмка:** поднятие из пустого checkout; миграции с пустой БД; два независимых пользователя не читают друг друга; staff grant/revoke работает без перезахода; job переживает worker restart; secrets/сырые анкеты не уходят в логи. Domain tables добавляются линейно A1 по согласованным delta, не единым гигантским JSON.

### P02 UI и навигация

Использовать существующие client/principal-pinning, focus/ErrorBoundary/lazy-recovery и upload/editor mechanics Общего Дела, сохраняя Opora skin. SDK остаётся generated, auth adapters меняются под cookies/CSRF.

Перенести токены и исходные SVG в UI primitives; desktop header с логотипом и меню в одну строку, top selector на узком экране. Создать формы/combobox/date/time, tabs, dialog/drawer, toast, skeleton/empty/error и upload/job states. Storybook показывает states из общих DTO fixtures.

**Приёмка:** 390/768/1050/1440, 200% zoom, keyboard/focus/reduced motion, long labels, отсутствие горизонтального overflow. Sidebar не добавлен, общие widgets не заменены системными popup. Source screenshot и итог сравниваются в одном состоянии; расхождения объяснены или исправлены.

### P03 Анкета и кабинет

Трёхшаговая форма из `content/form.js`: условные поля, маски, schema-driven validations, server draft, согласия, idempotent submit и welcome. Не объявлять SMS отправленным до реального результата. Своя анкета редактируется ревизией; имя/аватар из current user. Связи обучения/встречи используют UUID, смена email их не обрывает.

**Приёмка:** обычный проход без demo-fill; reload/ошибка сети не теряет draft; errors ведут к полю; double submit даёт одну application; edit после booking не сбрасывает встречу и тест; дубликат контакта не раскрывает чужой кабинет. Профиль/предпочтения дополняются в P13. Logout/account switch/401 очищает private query cache; проверен второй человек в том же браузере.

### P04 Знакомство и тест

Знакомство — один экран, подача шага задаётся `mode` (`cards` или `feed`) в материалах; один progress и одна попытка теста без повторного прохождения.

Импортировать актуальные тексты Фёдора/Арама как опубликованную версию из 4 модулей/10 вопросов. Реализовать blocks, сохранение progress, интерактивные разборы, server attempts/score, acknowledgement и прогресс знакомства. Прокрутка не считается серверным доказательством допуска; сервер проверяет завершение теста и не доверяет подмене `done`, но незавершённое знакомство не запрещает бронирование собеседования.

**Приёмка:** пройти реальные шаги и ответы; продолжение после reload; server не доверяет присланному score. Кандидат может сначала записаться и затем пройти знакомство либо наоборот. Завершение теста с любым результатом соответствует текущему согласованному сценарию, проходной процент самовольно не появляется. Новая версия материалов не перезаписывает историю.

### P05 Рабочее место по кандидатам

Поиск по имени/интересам, фильтры и progress/readiness, назначенный координатор. Карточка deep-link с обзором, анкетой и историей. Review/пауза/закрытие/reopen из старой Pipeline входят сюда. Просьба о другом времени и вопрос — реальные requests с ответом/историей, не исчезающий toast.

**Приёмка:** новая submission из другой сессии появляется в очереди; directions и roles не теряются; staff видит свою область; private заметки отсутствуют в self DTO; Back сохраняет query/scroll. Ответ координатора виден кандидату через self GET/history после reload и не копируется во внутреннее поле.

### P06 Собеседования

Два самостоятельных routes: список встреч и доступность. Once/weekly windows, duration/buffer, исключения, pause/unpause, timezone и произвольные недели. Общий BookingPicker используется кабинетом и координатором. Booking, reschedule, cancel, missed/completed, public agreement/private note, next task.

**Приёмка:** запись доступна сразу после анкеты независимо от знакомства; два API-запроса на один слот дают один успех; старое время сохраняется при неудачном переносе; нет пересечений координатора и кандидатских назначений; закрытие окна не отменяет встречи; чужая запись недоступна; изменения другой стороны видны без ручного reload. Напоминания интегрируются с P17 по outbox, не прямым HTTP внутри транзакции.

### P07 Роли и возможности

Разделить `roles.json` на справочник ролей, условия возможности и programme links. CRUD/archive/restore, usage и уникальность имени. Каталог объединяет FundCatalog с полезными состояниями Catalog; детали Opportunity/Participation — один route. Формы аудитории/задач/условий/регулярности/подготовки редактируемы. Matching v1 — причины и missing_data по явным правилам, а не фиктивные 94 балла.

**Приёмка:** роль доступна в новом занятии; archive не ломает историю; defaults копируются при создании, позже не меняют существующую договорённость; published-only public view; неопубликованная возможность не доступна по ID. Фильтры и объяснения опираются на реальные данные.

### P08 Календарь и повторы

Месяц/неделя/список, запрос любого периода, создание серии/отдельной даты. Once/weekly/biweekly/monthly, weekdays, until, exceptions, one/series edits, preview/apply конфликтов, cancel/restore. Origin occurrence ID сохраняется при переносе. Несколько staffing needs по разным ролям на одном занятии.

**Приёмка:** 29 февраля и месяц с отсутствующим 31-м; перенос одной даты не меняет соседнюю; series edit не стирает overrides, факты и подтверждения; concurrent edits дают409; capacity нельзя снизить ниже подтверждённых без явного решения. Никакого продуктового лимита на6 недель.

Включить отдельную карточку занятия `prototype/Event.html`, добавленную Фёдором в `55d7e80`: переход из календаря к экземпляру серии, возврат к той же дате, редактирование/копирование/состав команды. Карточка и расписание используют один occurrence/assignment API; изменение команды в одном месте видно в другом. Это дополнительная HTML-поверхность вне 41 артборда canvas, но внутри обязательного P08/P09 scope.

### P09 Участие и факт

Отклик, review/approval, приглашение, подтверждение/отказ, отмена/перенос, attendance. Пользователь не выполняет staff approval через собственный API. required/invited/confirmed показаны отдельно, capacity и пересечения защищены транзакцией. Отмена занятия приводит к понятному состоянию у всех назначенных людей.

**Приёмка:** приглашённый ещё не confirmed; одновременное подтверждение последнего места — один успех; неподготовленный пользователь получает причины; attendance только уполномоченным сотрудником; неявки не создают часы. Все сценарии из Participation и Shifts сохранены в каноническом модуле.

### P10 Участники и группы

#### P10A База участников и групп

Владеет участниками, группами, group memberships, leader scopes, assets и интерфейсом проверки назначения из P00. Не создаёт собственный volunteer event assignment service: этим владеет P09. P08 зависит только от P10A. Базовая приёмка: staff CRUD/assets/scopes и отрицательный доступ без назначения.

#### P10B Доступ по назначению

После P09 подключить реальные assignments к safe briefing/files API и волонтёрскому экрану. Приёмка двух групп/волонтёров, отзыв назначения и отсутствие private fields относится к P10B. Полный P10 готов только после обеих контрольных задач.

CRUD/archive участника, фото/интересы/практическая памятка/закрытые заметки. Group membership с периодами, состав конкретного занятия, leading staff и volunteer assignments. Private upload/quarantine/processing/error/replace, safe volunteer view по текущему назначению.

**Приёмка:** неназначенный человек не получает карточку/фото; private fields отсутствуют в JSON/поиске/экспорте; отзыв назначения прекращает новый доступ; ошибка upload сохраняет старое фото; актуальный состав и история занятия не смешаны. Проверить как минимум две группы и двух волонтёров, не хардкод `art`.

### P11 CRM, резерв и импорт

Единая карточка из Volunteers/VolunteerRecord: договорённости, контакты, проверенная доступность, follow-up и first-visit outcome. Reserve — очередь старой базы с no-contact. CSV/XLSX: upload/map/dry-run/preview/errors/apply, provenance, дубль/ручное merge, повтор batch без дублирования. Sheets connector — следующий adapter того же pipeline.

**Приёмка:** старый контакт не получает ready/active автоматически; ready требует доступности; импорт не отправляет уведомления; повтор batch идемпотентен; merge сохраняет историю/назначения; спорные строки доступны для решения. Следующее действие имеет owner/due_at/state.

### P12 Первый выход и сопровождение

Памятка: где/когда, кто встретит, задачи, подготовка, состав группы и контакт. Checklist, вопрос, отмена/другая дата. Рефлексия: настроение, текст, неожиданности/помощь/продолжение; если сохраняется voice control исходного дизайна — реальная запись, upload/transcription job и возможность исправить текст. Signals: ответственный, срочность, действие, reason, history, psychological-case scope.

**Приёмка:** вопрос связан с назначением и попадает сотруднику; данные группы только разрешённые; рефлексия не обязательна для часов; ответ «нужна помощь» создаёт follow-up, не просто цвет; sensitive case не раскрывается обычному staff без permission. Ошибки микрофона/загрузки имеют текстовую альтернативу.

### P13 Профиль, часы и признание

Контакты/навыки/интересы/доступность/пауза/notification preferences, подтверждение смены контакта, согласия. Ledger минут, запрос ручных часов и approval, история/коррекция, PDF справки/письма, благодарности и достижения по явным проверяемым правилам. AI-предложения: reviewable diff и accept/reject/revert на versioned profile; P13 реализует ревизии/UI, producer — в P15; общий сценарий с реальным profile API принимается в P20 после P13+P15. Экспорт своих данных/запрос удаления — workflow, не моментальная кнопка удаления всех связанных фактов.

**Приёмка:** повтор attendance не дублирует минуты; коррекция оставляет delta/автора/причину; справка содержит точный период/подтверждённые минуты и открывается реальным файлом; достижения не выданы за неподтверждённые факты. Изменение email не меняет UUID/назначения.

### P14 Академия и Builder

Треки/назначения/доступность, страницы урока/видео/задания/тесты, прогресс и курсные policies. Редактор blocks/versions, preview, validation, review/publish/archive, stable lesson IDs. P14 сдаёт ручной редактор и публикацию без зависимости от AI. AI draft кнопки и их окончательная интеграция относятся целиком к P15: `P14 base → P15 gateway/producer → Builder AI acceptance`; сгенерированный текст не публикуется автоматически от имени фонда.

**Приёмка:** publish неизменяемого release; старый learner progress воспроизводим; новый редактор не теряет блоки; неопубликованный материал закрыт; видео failure/retry/seek states; authoring и learner DTO не смешивают answer key.

### P15 База знаний и Mentor

Общий AI gateway с budgets/timeouts/JSON contracts/provider errors. Источники и версии, ingestion/index jobs, approved Q&A, очередь пробелов, ошибки и переиндексация. Mentor: поиск по разрешённым публикациям, цитаты, неизвестный вопрос/escalation/report. Цифры report/matching не генерировать как факты. Этот пакет также интегрирует AI draft в Builder и сдаёт AI profile suggestion producer по публичному profile revision interface из P00. Producer проверяется contract fixtures без зависимости от ledger/справок P13. Адаптер accept/reject/revert принадлежит A3/P13; сквозное соединение и реальная приёмка назначены P20 после обоих пакетов, с последовательным handoff A3/A7. Это не право объявить AI profile journey готовым до интеграции.

**Приёмка:** ответ цитирует существующий доступный source fragment; unknown честно идёт в очередь; withdrawn/private source не появляется в выдаче; prompt injection в источнике/диалоге не меняет policy; ключи/закрытые данные не уходят в клиент. Budget exceeded/provider down имеют рабочий fallback.

### P16 Scenarios и Simulator

Редактор сценария/рубрик, review специалиста, тестовый прогон и publish. Диалог, hints, pause/resume/finish, структурированный разбор по критериям с доказательствами из turns, повтор попытки, appeal и человеческий review. Методики архива — source input, не автоматически утверждённая политика фонда.

**Приёмка:** оценка не фиксированные6/10; версия prompt/model/rubric сохранена; можно восстановить ход попытки; appeal попадает человеку; результат тренажёра не даёт автоматический допуск/отказ. Прогон утверждённого evaluation dataset с сохранёнными limits.

### P17 Коммуникации

#### P17A Внутренний контур

Messages/membership/read cursors/attachments, две реальные сессии, sync, bounded polling либо SSE, outbox consumer interfaces. Уведомления доступны в inbox; не подключённый внешний канал возвращает unavailable. Это отдельный merge gate для P15/P18B.

#### P17B Доставка

Подключить выбранные реальные providers, preferences/no-contact, templates, webhook/retry/unknown outcomes и broadcast preview. A1 выполняет P17A, P17B, P18C последовательно; при необходимости изменить порядок сначала фиксируется handoff ownership. Ниже полная приёмка P17 A+B.

Внутренние direct/group/system threads, membership, read cursors, attachments и SSE/polling sync. Outbox handlers для booking/invite/cancel/change/follow-up. Email first, остальные channels через реальные adapters. Templates, preferences/no-contact, delivery states, webhook validation. Массовые сообщения с audience preview и подтверждением.

**Приёмка:** две настоящие сессии обмениваются сообщениями; unread обновляется; повтор/crash не создаёт duplicate message и не скрывает неизвестный delivery outcome; отменённая версия встречи не напоминается; нет сообщений после no-contact. Import не активирует broadcast. Неподключённый канал не рисуется доставленным.

### P18 Studio и запись уроков

План переноса кода/данных/commands и приёмка: studio-recording.md. Целевой результат — live занятия и самостоятельная запись урока с той же красивой композицией преподавателя/презентации, дубли, обработка, приватный просмотр и публикация.

#### P18A Shared stage

A2 портирует pure stageComposition/stageGeometry/cameraLayout и тесты в TS, typed StudioScene, Opora brand injection, reusable presenter/slides/board surfaces и headless render contract. Логика геометрии одна. До переноса общего source code зафиксировать dependencies и удалить school course/theme imports.

Приёмка: live/preview/recorder fixtures дают одну композицию; slides не обрезаны, long presenter name не ломает кадр; geometry golden tests и разные aspect ratios.

#### P18B Live Studio

A4 адаптирует LiveKit provider/session/host scopes и webinars UI из существующего room engine, presenter-authoritative scene/revision, optimistic slide flips, board/annotations/screen и shared chat adapter P17. Не переносить Zoom/course/tariff ветки без отдельной необходимости.

Slide upload/conversion и immutable deck versions входят в P18B: общий upload/assets/jobs P01 и отдельный office processor/media worker. P18C использует этот готовый сервис; live slides не ждут recording pipeline.

Приёмка: два браузера с реальным media/board; чужой viewer не patch scene; reconnect/device errors/revoke и token expiry; запись аудитории только по согласованной policy.

#### P18C Recording pipeline

A1 переносит stage journal/timeline и media primitives/checkpoint/Tus/fencing, новые repositories и private Egress/renderer auth. A2 собирает отдельный renderer entry из shared stage в своей области. Обычный web/API worker не получает CPU-heavy ffmpeg/office jobs.

Приёмка: итоговый MP4 содержит согласованный кадр и звук; source/media clocks и длительность проверены, нет controls/chat; restart/lease loss/ambiguous egress/upload/replayed webhook безопасны. Не включать auto-publish и fallback original при privacy failure. Проверить длительную запись и изолированное staging media окружение.

#### P18D Solo authoring

A2 делает отдельный вход «Записать урок», project/target lesson, preflight devices/slides/final-frame, idempotent take start/stop, processing/status, retake и private preview UI через P18C APIs. Не создавать календарную аудиторию или attendance. Frontend recording-project hooks принадлежат A2; все backend project/take/media endpoints входят в P18C/A1. Interfaces и минимальный backend project lifecycle готовы до начала P18D, поэтому pipeline не ждёт собственного будущего UI.

Приёмка: автор без учеников реально пишет дубль, может уйти/вернуться, выбрать готовый take. Error/retry не теряет прошлый дубль. Pause не заявляется без segments; start/stop/retake обязательны.

#### P18E Preview и публикация

A7 адаптирует готовые learner preview/lesson version publish/CAS interfaces; A2 подключает их к recording UI отдельным последовательным изменением. Название/описание/обложка/материалы/аудитория, save draft, explicit approve/publish, replacement/withdraw/rollback. Render готовность не запускает публикацию.

Приёмка: ordinary volunteer не читает draft; preview не меняет progress; publish конкретного render hash/lesson version идемпотентен; новый render требует собственного approval; неудачная замена сохраняет старый primary. После live webinar summary edit→review/publish и audience preview используют delivery contract P17A. Реальная send enrolled audience принимается в P20 после P17B+P18E; она не блокирует private lesson publish и не публикует закрытую запись автоматически.

### P19 Reports и Admin

Данные/периоды/definitions метрик, narrative draft/edit/confirm, реальные CSV/PDF/DOCX, выгрузка Добро.ру через согласованный adapter и gratitude workflows. Staff invites/grants, integration health/config, templates/settings UI, import journal, AI budgets и audit. Admin обращается к сервисам владельцев; не пишет их таблицы напрямую.

**Приёмка:** числа сверяются с контрольными SQL fixtures, scope одинаков у экрана и экспорта; unknown/provider failure видны; secret не читается обратно; настройка влияет на следующий запрос/job с аудитом; понижение доступа применяется к export/файлам. Reports не содержит вымышленных текущих показателей. DOCX открывается как реальный документ; Добро.ру показывает preview/mapping и реальный результат, а до утверждения формата/API — unavailable, не success.

### P20 Независимая приёмка и выпуск

Две явные задачи соединения доменов: (1) A3/A7 последовательно подключают и принимают profile suggestions producer P15 к revisions/accept/reject/revert P13; (2) A7/A1 соединяют summary audience preview P18E с реальной доставкой P17B. A0 назначает короткие handoff-задачи владельцам, A8 принимает результат; граф резервирует A1/A3/A7 для этих интеграций в P20. До этих проверок соответствующие journeys не считаются готовыми; они не задерживают независимые Knowledge/recording пакеты.

Пройти карту43board и список механик каждого пакета; проверить API contracts, ACL, races, idempotency, restore, provider errors, accessibility essentials и visual fidelity. Полный путь двух ролей — в серверных browser contexts, не роль-переключатель. Обязательны оба порядка: анкета → запись → знакомство и анкета → знакомство → запись; редактирование контакта сохраняет идентичность, прогресс и встречу. Telegram reminder preference и подтверждённая привязка бота проверяются раздельно. Проверить изменения после booking и согласования, а не только первый happy path.

**Приёмка:** clean CI, одна Alembic head, поднятие из пустой БД и upgrade с предыдущей схемы, staging smoke, восстановление backup, точный runtime SHA. Разрешение на production deployment — отдельное пользовательское действие; подготовить reviewable release/runbook заранее.

## Волны и интеграционные гейты

1. **Волна0:** A0/P00; затем A1/P01 + A2/P02 + A8/CI/test skeleton. Domain agents могут готовить schemas/fixtures, но не выдумывать несовместимые handlers.
2. **Волна1:** A3/P03–P05, A7/P04, A4/P06; одновременно A5/P07, A6/P10A, A1/P17A. Первый гейт — кандидат и координатор на настоящем API/БД, в том числе двойная запись.
3. **Волна2:** A5/P08–P09, A3/P11–P13, A6/P10B–P12, A7/P14, A1/P17B. Общие dependencies назначений/памяток сначала интегрируются, затем расширяются. Это операционный пилот фонда.
4. **Волна3:** A7/P15, A2/P18A (может начинаться ещё после P02), затем A4/P18B и A1+A2/P18C; A2/P18D и A7/P18E. A4/P16 и A3/P19 идут по освободившимся слотам и контрактам. A2 также закрывает согласованные visual gaps; A8 проверяет full scope. Топологические слои графа показывают готовность зависимостей, а не расписание: один A4 не ведёт P16/P18B одновременно, один A7 — P15/P18E, один A2 — renderer/P18D/visual fixes. Поддержка renderer P18C и UI P18E — отдельные задачи A2 с передачей готового diff, не второй одновременный владелец backend/learning. В work-graph.json приведено консервативное расписание без конфликтов слотов; ускорение возможно только при явном изменении ownership. Слоты можно переназначить только с передачей ownership и отдельным integration commit.
5. **Волна4:** A0+A8/P20, провайдеры/контент/доступы согласованы для запуска. Если AI/RTC выключены, продукт может иметь ограниченный пилот, но «перенесено всё» не заявляется.

Перед каждым merge: base SHA и contracts version, только свой diff, meaningful tests, миграция согласована, нет mock fallback в product path. После merge A0 регенерирует SDK/route registry и запускает сквозной affected journey. Не отправлять всех агентов напрямую в main.

## Общий формат задания агенту

```text
Реализуй пакет Pxx из docs/implementation/work-packages.md.
Base SHA: <интеграционный commit>. Contract version: <версия>.
Владеешь: <точные module/test paths>. Общие файлы не меняй.
Reference boards/states: <строки screen-map.csv и hash manifest>.
Сохрани стиль Опоры и верхнюю навигацию, тексты Фёдора не переписывай.
Backend: API contracts, service invariants, scope queries, real PostgreSQL.
Frontend: typed SDK, все нужные loading/error/empty/conflict states.
Shared schema change: передай delta A1/A0 до реализации клиента.
Не подменяй интеграцию demo state или ложным success.
Сдай: diff, contract/migration delta, tests, screenshots, limits,
reproduction и результат критериев приёмки Pxx.
Не деплой production, не отправляй реальные сообщения, не импортируй
персональные базы без отдельного задания на конкретные данные/канал.
```

## Что означает готовый пакет

Рабочий UI со всеми действиями своего scope, реальный API и storage, права на команды/выборки/файлы, серверные инварианты и негативные тесты, обновлённый контракт, наблюдаемые job/provider outcomes, визуальное сравнение и документация запуска. Красивый экран с `setState`, моковый ответ SDK, скрытая private note или «кнопка скачивания» без файла готовностью не считаются.
