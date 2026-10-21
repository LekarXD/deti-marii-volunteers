# API и перенос интерфейса

## Единый контракт

Базовый путь `/api/v1`. Pydantic schemas и стабильные `operation_id` собираются в OpenAPI; интегратор генерирует TypeScript SDK и публикует его в `apps/web/src/api/generated`. Компоненты не содержат написанные вручную копии серверных enum/DTO.

Контракт включает не только happy path: пример ответа, разрешения, ошибки, idempotency, expected version и события. При изменении DTO агент сначала согласует schema delta; frontend не подстраивается под незафиксированный словарь произвольных строк.

```json
{
  "code": "slot_unavailable",
  "message": "Это время уже занято. Выберите другое.",
  "field_errors": {},
  "current_version": 8,
  "retryable": false,
  "request_id": "uuid"
}
```

`401` — истекла сессия; `403` — нет права; `404` — ресурс не найден/не раскрывается этому пользователю; `409` — конфликт версии/бизнес-состояния; `422` — ошибки полей; `429` — ограничение запросов; `503` — временная недоступность. Выбор 403/404 для закрытых ресурсов единообразен, не позволяет перечислять чужие записи.

У ресурсов `id`, `version`, `allowed_actions`. Действия вычисляет сервер для текущего пользователя и состояния. Для изменяющих состояние команд — `Idempotency-Key` и JSON `expected_version` для изменяемого агрегата (единое соглашение, без параллельного If-Match). Create без существующего агрегата не требует фиктивной версии; compound publish именует версии каждого проверяемого агрегата явно. Обязательные поля дат имеют тип `Instant`/`LocalDate`/`LocalTime`, timezone отдельным полем. Списки — cursor pagination с детерминированной сортировкой и ограниченным `limit`; календарь — ограниченный диапазон, без бизнес-лимита «6 недель».

### Сессия и граница авторизации

P01 реализует opaque server session в host-only Secure HttpOnly cookie, SameSite=Lax, rotate при login/MFA и смене principal. Unsafe browser requests требуют exact Origin и session-bound CSRF token в header; GET не потребляет login link и не меняет состояние. Challenge purpose, contact, expiry и attempts проверяются при atomic consume. Токены не находятся в localStorage/логах. Проверка подтверждённого контакта и перенос своей registration application в user выполняются транзакционно; совпадение строки email до подтверждения не объединяет пользователей.

Session expiry/revoked и актуальный membership/scope проверяются на каждом запросе; 503 БД не превращается в logout/401. Отзыв действует для запросов, начавших авторизацию после commit revoke; уже скачанные данные не отзываются. Чувствительные mutations дополнительно перепроверяют scope в своей транзакции. Если revoke конкурирует с такой командой, обе используют общий transaction-scoped authz guard по subject/scope, до доменных locks по фиксированному порядку (сами строки assignments не захватываются раньше occurrence). Все команды изменения этих grants/assignments соблюдают тот же протокол; commit определяет порядок результатов. Не обещать мгновенное прерывание любого уже выполняющегося HTTP/stream. SSE/RTC требуют закрытия/revalidation по revocation event и ограниченного heartbeat; при потере проверки fail closed.

Staff MFA — отдельный P01 gate: enrollment, recovery и step-up для изменения grants/MFA, запрет выдачи staff assurance одной лишь email ссылкой. Enrollment/recovery конкретного фактора фиксируется в P00; готового MFA в OD не заявляется.

## Основные endpoints

В таблице перечислен необходимый контракт; создание handlers относится к пакетам реализации.

| Модуль | Контракт |
|---|---|
| Вход | `POST /auth/challenges`, `/auth/challenges/verify`, `/auth/logout`; `GET /auth/session`; staff MFA/role grants отдельными permission-protected endpoints |
| Анкета | `GET/PUT /registration/draft`, `POST /applications/submit`, `GET /me/application`, `POST /me/application/revisions`, `/me/application/withdraw` |
| Кандидаты | `GET /coord/candidates`, `GET /coord/candidates/{id}`, `POST /coord/candidates/{id}/review`, `/reopen`; внутренние заметки отдельным ресурсом |
| Подготовка | `GET /me/preparation`, `/learning/assignments`; `GET /learning/lessons/{version_id}`; `POST /learning/progress/{id}/complete`, `/policy-acknowledgements` |
| Тест | `POST /assessments/{version_id}/attempts`; `POST /assessment-attempts/{id}/answers`, `/submit`; `GET /assessment-attempts/{id}/result` |
| Собеседования | `GET /interview-slots?from&to&timezone`; `POST /interviews`; `GET /me/interviews`; `POST /interviews/{id}/reschedule`, `/cancel`; staff `/complete`, `/mark-missed` |
| Доступность координатора | `GET/POST /coord/interview-availability`; `GET/PATCH /coord/interview-availability/{id}`; `/preview-change`, `/exceptions`, `/pause`; `GET /coord/interviews` |
| Вопросы кандидата | `POST /me/candidate-requests`; `GET /me/candidate-requests`, `/{id}` с публичной историей ответов; `GET /coord/candidate-requests`; `POST /coord/candidate-requests/{id}/respond`, `/resolve` |
| Роли | `GET/POST /coord/roles`; `PATCH /coord/roles/{id}`; `/archive`, `/restore`; `GET /coord/roles/{id}/usage` |
| Возможности | `GET /opportunities`, `/{id}`; staff `POST/PATCH /coord/opportunities`, `/publish`, `/pause`, `/close`; `POST /opportunities/{id}/responses` |
| Решение по отклику | `GET /coord/responses`; `POST /coord/responses/{id}/approve`, `/decline`, `/request-preparation`; own `/responses/{id}/withdraw` |
| Календарь | `GET /event-occurrences?from&to`; staff `POST /coord/event-series`, `/coord/event-occurrences`; `POST /coord/event-series/{id}/preview-change`, `/apply-change` |
| Отдельная дата | `PATCH /coord/event-occurrences/{id}`; `/cancel`, `/restore`; `GET/PATCH /coord/event-occurrences/{id}/staffing-needs` |
| Команда | `GET /coord/staffing-needs/{id}/suggestions`; `POST /coord/staffing-needs/{id}/invitations`; `POST /assignments/{id}/confirm`, `/decline`, `/cancel` |
| Первый выход | `GET /me/assignments/{id}/preparation`, `/group-briefing`; `PUT /me/assignments/{id}/checklist`; вопрос — в contextual conversation/request |
| Факт и часы | `POST /coord/assignments/{id}/attendance`, `/attendance/{id}/correct`; `GET /me/service-time`; `POST /me/time-requests`; staff `/time-requests/{id}/approve|decline` |
| Рефлексия | `GET/PUT /me/assignments/{id}/reflection`; `POST .../reflection/submit`; `GET /coord/reflections`; `POST /coord/reflections/{id}/review` |
| CRM | `GET /coord/volunteers`, `/{id}`; agreements, contact-events, availability-verifications и follow-up-tasks — отдельные collections/commands |
| Резерв | `GET /coord/contact-reviews`; `POST /coord/contact-reviews/{id}/record`; status ready требует актуальной доступности |
| Участники | staff `GET/POST/PATCH /coord/participants`; private-notes отдельным endpoint; `GET /me/assignments/{id}/participants` — только safe DTO |
| Группы | staff `GET/POST/PATCH /coord/groups`; membership add/end; `GET /me/groups/{id}` только по разрешённому назначению |
| Файлы | `POST /assets/upload-intents`, `/assets/{id}/complete-upload`; `GET /assets/{id}/status`, `/content`; attach только обработанный разрешённый asset |
| Сообщения | conversations/members/messages/read-cursor; `POST /messages` возвращает созданное сообщение, не фиктивный внешний delivery status |
| Сигналы | `/coord/signals`, `/{id}/assign`, `/resolve`, `/reopen`, `/dismiss`; permissions для закрытых case details отдельно |
| Обучение и редактор | `/coord/learning/tracks`, `/releases`, `/lessons`, `/assessments`; validate/preview/review/publish/archive по версии |
| База знаний | `/coord/knowledge/sources`, `/questions`, `/answers`, `/index-jobs`; `/knowledge/search`, `/mentor/runs` для разрешённых опубликованных материалов |
| Тренажёр | `/simulator/scenarios`, `/simulation-sessions`, `/{id}/turns`, `/pause`, `/finish`, `/evaluations`, `/appeals`; staff draft/review/publish сценариев и рубрик |
| Вебинары | `/webinars`, `/{id}/enroll`, `/join-token`, `/recordings`; host room controls и board sessions — через RTC adapter с серверными правами |
| Отчёты и справки | `/coord/reports/metrics`, `/coord/report-exports`; `/me/certificates`, `/certificates/{id}/download`; async job/status/download |
| Администрирование | staff members/grants, templates, integration health, settings versions, import batches/preview/apply, audit; secrets write-only/ref |

Списки и детальные ответы ограничены тем же scope, что команды. Экспорт и фоновая задача перепроверяют право, а не наследуют навечно доступ пользователя при старте job.

## DTO, которые нельзя смешивать

```text
CandidateSelfView           собственные ответы, подготовка, публичная встреча и итог
CandidateCoordinatorView    review, assigned coordinator, контакты и внутренние действия
ParticipantBriefingView     разрешённые фото/имя/интересы/практическая памятка
ParticipantStaffView        поля координатора в рамках его scope
InterviewPublicResult      договорённость и разрешённый следующий шаг
InterviewPrivateNote       отдельная закрытая сущность
StaffingSummary            required, invited, confirmed, missing
ReadinessView              fulfilled/waived/pending requirements + причины
MatchSuggestion            критерии, missing_data, ограничения, объяснение, algorithm_version
```

Волонтёрский DTO не строится как «весь ORM-объект минус поле private». Использовать разрешённую проекцию в repository и отдельную Pydantic schema. `response_model` полезен как дополнительный барьер, но не заменяет scope query.

Бронирование собеседования не требует завершения знакомства/теста. API отдаёт прогресс отдельно, а кабинет одновременно показывает выбор времени и материалы. Поля reminder preference и подтверждённого подключения Telegram различаются; Telegram username из анкеты не является доказательством владения.

Для booking POST возвращает authoritative booking/новую версию; при 409 список времён обновляется, выбранный невалидный слот сбрасывается, исходная запись при переносе остаётся. Для series edit preview содержит affected occurrences, confirmed users, conflicts и `preview_hash`; apply повторно проверяет исходную версию.

## Перенос дизайна во frontend

### Компоненты первого этапа

`AppHeader`, `Brand`, `DropdownNav`, `MobileTopSelector`, `Button`, `Field`, `TextInput`, `Textarea`, `Checkbox`, `RadioGroup`, `Combobox`, `DatePicker`, `TimeInput`, `Tabs`, `Drawer`, `Dialog`, `Card`, `StatusBadge`, `Timeline`, `Toast`, `InlineError`, `EmptyState`, `Skeleton`, `FileUpload`, `AsyncJobStatus`.

Использовать токены из [helmet.html](../../prototype-src/helmet.html) и [extensions.css](../../prototype-src/extensions.css), исходные SVG из кита. Inter по возможности self-hosted. Служебные `sc-if`, `sc-for`, `.dc.html`, `support.js` и Python string replacements в production не переносятся. Макет и состояния переводятся в типизированные React components; fixture-пример привязан к тому же API DTO.

На desktop Brand и основная навигация в одной строке. При нехватке ширины включается компактный верхний выбор, а не боковое меню и не случайный второй ряд. Открыт один dropdown; доступны Enter/Space/стрелки/Escape, outside click и возврат фокуса. Текущая страница остаётся понятной после перехода по прямой ссылке.

Календари и списки оформлены общими компонентами; не возвращать системный тёмный popup из прежних скриншотов. Для long list — поиск/no-results, выбранное значение и прокрутка. Месяц и год доступны клавиатурой; дата и время отображаются в timezone события/фонда с явной подписью.

### Layouts и routes

- `PublicLayout`: анкета и публичная часть фонда.
- `CandidateLayout`: кабинет, знакомство и собственная анкета; имя/аватар текущего человека, без демо-Анны и нерелевантных уведомлений.
- `VolunteerLayout`: личные занятия, возможности, обучение, сообщения, профиль.
- `FundLayout`: верхние группы «Волонтёры», «Занятия», «Участники», «Ещё»; реальные страницы по capabilities.
- Полная карта старый board → production route — в [CSV](screen-map.csv). Списки/карточки/drawers должны иметь deep link: reload или копирование URL возвращают ту же сущность, Back возвращает поиск/фильтры/прокрутку.

В production нет переключателя «волонтёр/координатор», выдающего права, reset demo, «заполнить примером» или автоматического `ensureCandidate()` с вымышленной персоной. Эти режимы допустимы в Storybook/dev fixtures и защищённом demo environment.

### Работа с серверным состоянием

- Typed SDK — единственная транспортная точка; generated operations вызывают один custom fetch transport (cookies/CSRF, identity epoch, AbortSignal, errors и bounded retries). TanStack Query управляет loading/cache/refetch и mutation invalidation; форма хранит редактируемый draft отдельно.
- При logout/смене identity/401 отменить private queries, очистить QueryClient/private cache и закрыть SSE/socket. Не включать persist закрытых данных. Второй пользователь в том же браузере не должен видеть cached карточку первого.
- URL хранит фильтры/период/выбранную сущность. Не хранить весь user profile, приватные заметки или session tokens в localStorage.
- Optimistic UI допустим для безопасных обратимых preferences, но не подтверждает booking, место, attendance или часы до ответа API.
- После внешних изменений использовать SSE или bounded polling с query invalidation. Для первого рабочего контура достаточно polling активных списков/карточек; SSE или согласованное bounded polling входит в P17A. Storage events не заменяют синхронизацию между настоящими пользователями.
- Autosave сообщает pending/saved/error; несохранённые изменения не теряются при network failure. При 409 редактор показывает конфликт и актуальные данные, не молча перезаписывает.
- Длительная операция — job с ID/status/retry, а не бесконечный spinner или мгновенная надпись «скачано».

Каждый экран сдаётся с состояниями: initial/loading, empty, no results, success, validation error, permission denied, expired session, unavailable/deleted resource, network retry и conflict. Для mutations также double-click prevention, in-flight, cancelled/changed externally. Не все состояния обязаны занимать отдельную страницу, но все должны иметь fixture и проверенный путь восстановления.

## Интеграции по блокам

### Уведомления и сообщения

Сначала internal inbox и email. Для SMS/Telegram/Max/WhatsApp — отдельные adapters, credentials и подтверждённая привязка. Указанный username в анкете не считается authenticated chat identity. Канал без подключённого провайдера имеет состояние unavailable, не delivered.

Бизнес-транзакция пишет outbox. Worker выбирает job с lease, перед отправкой сверяет актуальную запись и version, уважает preferences и no-contact. Reminder key включает сущность/версию/тип напоминания; перенос аннулирует старые задания. Webhooks сверяют подпись и повторный event ID. Provider retry и неизвестный исход отражаются в журнале.

Массовое сообщение: draft → preview/frozen audience → отдельное подтверждение координатора → queue. Import commit не запускает массовую рассылку. Внешнее уведомление содержит минимум информации и ссылку после входа, без закрытых фото/памяток.

### Фото и документы

Upload intent проверяет permission/лимит/назначение; файл идёт в quarantine. Worker проверяет содержимое, перекодирует изображение, удаляет метаданные, создаёт thumbnail. При ошибке прежнее фото остаётся. Произвольные HTML/SVG/полиморфные файлы не обслуживать как доверенные inline assets.

Для строго закрытых фото — авторизованный proxy `/assets/{id}/content` с проверкой scope на запрос. Для допустимых случаев — короткоживущая подписанная ссылка. Отзыв назначения запрещает новые ссылки; уже выданная ссылка действует до TTL, скачанный файл технически не отзывается. Политика cache/private headers учитывает это ограничение.

### AI, подбор и знания

Общий AI gateway: provider config, таймауты, лимит параллельности/стоимости, version prompt/model, JSON-schema output, telemetry без частных анкет в логах, fallback и retry policy. Ключи только на сервере. Private notes и реальные характеристики участников не передаются автоматически модели.

Matching сначала rule-based с явными причинами и `missing_data`; искусственный процент не показывать. LLM может формулировать объяснение на основе проверенных критериев. Результат не даёт допуск и не меняет assignment. Автоотправка приглашений выключена до отдельного решения фонда.

Mentor использует только опубликованные разрешённые источники. Ответ хранит конкретные source_version/chunk IDs и доступные пользователю цитаты. Неизвестный ответ создаёт вопрос сотруднику. Документ/диалог — данные, не команды для смены policy или вызова инструментов. Переиндексация и отзыв публикации инвалидируют доступность источника.

Simulator: вымышленные сценарии, версия рубрики, turns, hint/pause/finish, оценка по критериям с фрагментами самого диалога, appeal и review специалиста. Эталонный dataset проверяет согласованность оценок и отсутствие автоматического «допуска по AI». Builder/Scenarios публикуют только reviewed versions; AI generation создаёт draft.

### Studio, онлайн-занятия и запись уроков

Основа — готовый LiveKit/media/stage код Общего Дела, source map и границы адаптации в studio-recording.md. Общие typed StudioScene/geometry и brand injection используются live host/viewer и headless recorder. Не писать две независимые геометрии сцены; Python ffmpeg fallback проходит cross-language geometry golden tests.

Два режима: `live_event` с enrollment/host и `lesson_recording_project` без аудитории. Solo автор из Builder видит готовый кадр, проверяет devices/slides, записывает take, получает приватный preview, выбирает дубль, оформляет материал и публикует конкретный ready render в lesson version. Этот путь не создаёт calendar attendance и audience notifications.

Включить contracts из studio-recording.md: recording project, capture session/takes, scene journal, render manifest/version, review/publication; idempotent start/stop/retry/publish, private preview, replacement/rollback. Source auto-publish при readiness не переносится. Capture ready/render ready/published — разные состояния.

P18A: extraction/shared scene, без зависимости от готового редактора P14. P18B: live/media adapter и права. P18C: recording pipeline и hidden renderer. P18D: solo authoring/takes/preflight/recovery. P18E: learner preview/review/publish и Builder integration. Подробные команды и приёмка — в отдельном документе и work-packages.md.

Join tokens короткоживущие. Отзыв enrollment удаляет active room member и закрывает chat/board, не только выдачу следующего token. Проверить revoke после выдачи до join и во время соединения. Для recorder отдельные subscribe-only credentials, не learner/host token. Publish проверяет rights в текущем scope; выводы о production-коде OD не считаются готовностью развёртывания Опоры.

Запись общего занятия не включает личный чат/служебные controls; policy по камерам/именам/голосам участников задаётся явно. На cosmetic failure — degraded/review; на privacy failure — blocked, исходник не автопубликуется. Source/checkpoint retention позволяет восстановление и повторный render до решения автора.

### Отчёты и доступность

Отчёт строится по server query с definition version метрик: активный волонтёр, подтверждённые минуты, нужные/приглашённые/подтверждённые места, отклики и события. Для каждой метрики фиксируются период, timezone, фильтры, distinct entity и исключённые статусы. Не суммировать invitations как реальные участия.

PDF/CSV/DOCX и справки — server export jobs с permission-aware dataset и реальными assets. AI-текст отчёта — редактируемый draft с исходными числами, а не источник метрик. Пользовательский экспорт данных и запрос удаления обрабатываются отдельным workflow со scope, сроком и зависимостями истории.

Предложения AI к профилю — отдельные `profile_change_suggestions` с reviewable diff, источником и состояниями proposed/accepted/rejected/reverted. API: `GET /me/profile/suggestions`, `POST /me/profile/suggestions/{id}/accept|reject|revert`. Принятие требует expected_version, создаёт ревизию профиля; отмена не перезаписывает последующие ручные изменения без проверки конфликта. P13 создаёт основу UI/ревизий, AI producer относится к P15; окончательная cross-package интеграция принимается в P20 после P13+P15.

Добро.ру: отдельный export/integration adapter, preview периода/подтверждённых минут, mapping и журнал результата. Формат/API/учётная запись запрашиваются у владельца интеграции; не предполагать существование публичного API и не имитировать передачу успешным toast. До согласования provider contract показывать unavailable. Реальная выгрузка/передача и отрицательные ответы — обязательная приёмка этого состояния Hours/Admin в P19.

После вебинара Studio поддерживает команды `edit summary draft → review/publish → send enrolled audience` через P17, с версиями и preview получателей. Итоги и запись — разные сущности; публикация итогов не публикует закрытую запись автоматически.

## Извлечение общей платформенной основы

P02/A2 владеет `apps/web/src/api/transport.ts`, query keys/QueryClient и общим upload UI; A0 только генерирует SDK/контракт, A1 владеет серверным asset/upload service. Не оборачивать OD client, SDK и fetch в три независимых retry/cache слоя. TanStack mutations по умолчанию retry=0; transport повторяет безопасный GET либо конкретную идемпотентную команду с тем же key. Identity epoch проверяется и при завершении старого запроса, чтобы поздний ответ не заполнил cache другого пользователя. Resumable upload — один lifecycle (intent/offset/checksum/finalize); image/document/slides/video добавляют validation/processing handlers, не вторые auth/transport/upload engines.

До написания новых transport/cache/auth/upload/helpers использовать platform-reuse.md: API retries/principal pinning, QueryClient/cache isolation, error/focus/lazy recovery, resumable upload, lesson autosave/preview/publish. A0 закрепляет interfaces/contract fixtures, A1 адаптирует auth/DB/jobs/delivery/assets, A2 переносит UI mechanics под стиль Опоры. Cache TTL, rate budgets и token guarantees исходника не копируются без проверки новой domain policy.

Карточка занятия из `prototype/Event.html` переносится на `/fund/events/:id` вместе с P08/P09: идентичность occurrence передаётся явно, возврат сохраняет дату/фильтры календаря, состав команды общий с расписанием.
