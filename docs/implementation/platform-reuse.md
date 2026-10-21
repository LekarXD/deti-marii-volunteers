# Что перенести из рабочего кода Общего Дела

Стратегия реализации «Опоры»: сначала выделять проверяемые механизмы из готового проекта, затем адаптировать границы данных и оформление. Заново писать только то, что специфично для фонда или не соответствует выбранной архитектуре.

Проверен локальный `/Users/iliapetri/curator-bot`, commit `38c92cd49b1b6c229ed473de991479ed261e4052`, только чтение исходников и тестов. Production, секреты, БД и реальные провайдеры не использовались. Наличие теста в исходнике не означает его запуск в этой проверке. Ссылки ниже закреплены на commit; [manifest](reuse-source-snapshot.json) хранит хеши проверенных файлов.

В исходном проекте также React/Vite/FastAPI/PostgreSQL. Главные отличия: JavaScript вместо целевого TypeScript в части frontend, Supabase/PostgREST/RPC вместо выбранного SQLAlchemy/UoW, школьные course/lesson scopes, JWT+refresh и Telegram identity. Это точки адаптации, не причина отказываться от готового кода.

## Приоритет переноса

1. P00: inventory кода и зависимостей, определить владельцев и минимальные переносимые интерфейсы.
2. P01/P02: transport/errors, scope/identity checks, atomic receipts, jobs/fencing, assets/uploads, UI focus/error/lazy boundaries.
3. P03–P17: подключать домены к этим общим механизмам; не размножать собственные варианты retry, client, upload и auth.
4. P18: shared scene, LiveKit, слайды, recorder и media pipeline по [отдельному плану](studio-recording.md).
5. P20: повторить перенесённые regression scenarios в новом окружении и доказать новые guarantees. Старые production-релизы не являются приёмкой «Опоры».

## Сервер, БД и оптимизации

| Механизм и точка в исходнике | Что переносится | Что меняется в Опоре |
|---|---|---|
| [Mutation receipts, SQL:14](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/migrations/488_task_mutation_receipts.sql#L14), [HTTP contract:25](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/routers/web_tasks/receipts.py#L25) | Durable результат команды, actor/operation/key/payload hash, безопасный replay после timeout | UUID пользователя, новые commands, SQLAlchemy transaction. Проверка доступа перед replay; иной payload с тем же key —409 |
| [Reward receipts:40](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/migrations/446_lms_lesson_reward_receipts.sql#L40) | Постоянный факт отдельно от сбрасываемого progress | Minutes/attendance ledger, без школьной игровой экономики. Повтор progress не начисляет часы повторно |
| [Paging:42](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/db/paging.py#L42) | Stable unique order, явная ошибка при превышении бюджета вместо тихого усечения | Keyset pagination для SQLAlchemy; cap1000 специфичен для source PostgREST, его не переносить как лимит продукта |
| [Blocking bulkheads:145](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/utils/blocking.py#L145) | Bounded admission/queue, отдельные I/O pools, корректное освобождение после реального завершения работы | Async SQLAlchemy/HTTPX в API, CPU/ffmpeg/office-conversion в worker/process. Экспорт не вытесняет login/booking |
| [SWR cache:45](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/utils/swr_cache.py#L45) | Bounded cache, single-flight и generation fence против устаревшего in-flight результата | Только для измеренных горячих read projections; ключ включает scope/definition version. Не использовать stale cache для финального permission/capacity/booking решения |
| [Durable lease:29](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/grader_ledger/durable_lease.py#L29), [scheduler:162](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/jobs/main_worker.py#L162) | Claim/expiry/token/renew, persisted cadence, fenced completion | SQLAlchemy jobs/outbox; отдельный budget соединений для heartbeat. Scheduler lease не заменяет fencing конкретной записи |
| [Rate limits:44](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/web/rate_limit.py#L44) | Разделение identity/IP/operation, trusted proxy и bounded backend timeouts | Session UUID вместо JWT/course family. На одной реплике допустим ограниченный режим; distributed guarantees требуют общего limiter state. Redis добавлять осознанно, не скрытой зависимостью |
| [Cache headers:28](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/web/cache_headers.py#L28) | Opt-in public/private/no-store и граница browser/proxy cache | Закрытые анкеты/памятки/booking не получают TTL рейтингов. Shared-cache не хранит self responses |
| [Metrics:45](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/web/metrics.py#L45) | Нормализованные route labels, ограниченная cardinality, очередь отдельно от execution | Стандартный collector, release/worker labels без персональных данных; не усреднять p95 разных процессов |
| [Artifact jobs:50](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_artifacts/execution.py#L50) | Source identity, durable failure, lease heartbeat, completion fence | AI drafts, transcript, export и отчёты; источники по новым lesson/media versions |
| [Source provenance:30](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_artifacts/source_identity.py#L30) | Производные материалы связаны с конкретным видео/версией, не просто lesson ID | Замена записи инвалидирует старые transcript-derived материалы; ручной контент не удаляется автоматически |
| [Media drain:14](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/jobs/_media_drain.py#L14), [readiness:29](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/runtime_readiness.py#L29) | Expiring drain, stop new claims, ожидание текущего render/upload, финальная проверка перед swap, exact release SHA | Небольшой собственный deploy/runbook. Не копировать монолитный OD deploy script, имена сервисов, replica/duel gates и боевые пути |

Оптимизации включаются по измерениям. Для небольшого фонда не нужны сразу все кеши, Redis-кластеры и многорепличная топология Общего Дела. Перенести ограничения ресурсов, идемпотентность, instrumentation и тесты — они полезны с первого запуска. Кеширование и количество workers подбирать после профиля нагрузки.

## Вход, сессии и права

| Исходник | Ценный механизм | Граница адаптации |
|---|---|---|
| [Login:49](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/routers/web_auth/_login.py#L49), [verification tokens:6](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/db/email_verification_tokens.py#L6) | Generic ошибки, dummy password check, hashed one-time token, atomic consume, защищённый email outbox | Verification link не равен готовому OTP login. В Опоре purpose-bound challenges для регистрации/входа/смены контакта; school purchase/Telegram bridges не переносить |
| [Session rotation:158](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/db/refresh_tokens.py#L158), [sessions API:46](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/routers/web_auth/_sessions.py#L46) | Atomic rotate/consume, session list/revoke, replay recovery | Для выбранных server-side cookie sessions достаточно opaque ID hash и проверки expiry/revoked. Полная JWT+refresh конструкция не обязательна |
| [Principal resolver:96](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/web/auth_dependency.py#L96) | DB-authoritative role, single-flight и generation invalidation, outage→503 | Scope `foundation/program/group/assignment`; cache30s source не означает мгновенный revoke между репликами. Начать без authz stale cache |
| [Scope gates:105](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/routers/dependencies.py#L105) | Immutable FK, fresh active membership и fail-closed resource access | Courses/tariffs заменить capabilities и назначением на группу/занятие. Technical admin не получает автоматически private notes |
| [Cookie/Origin:157](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/routers/web_auth/_helpers.py#L157) | Exact Origin allowlist и HttpOnly/Secure cookie настройки | В OD cookie относится к refresh, обычный API Bearer. В Опоре CSRF policy нужна для всех unsafe cookie-auth mutations; свой host-only domain и HTTPS |
| [Asset binding:170](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/routers/lms/lessons.py#L170) | Subject→resource→asset связь до выдачи signed URL | Только asset UUID, связанный с разрешённой группой/lesson version. Не подписывать произвольный storage key; для фото свои proxy/TTL |
| [Transactional audit:47](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/db/staff/content_status_audit.py#L47) | Status transition+audit в одной транзакции, reason/version | Расширить на login/challenge/session/grant и новые entity types. Готового единого auth audit в рассмотренных handlers не подтверждено |

**Ограничения исходной модели, которые не повторять автоматически:** access JWT остаётся действительным до TTL после revoke refresh family при неизменной роли; per-process cache invalidation не гарантирует отзыв на другой replica; fallback limiter может быть только per-process. Эти границы видны в source, это не вывод о текущей production-конфигурации. Для server sessions Опоры проверять revoked/expiry/authz_version и свежие object scopes на каждом чувствительном запросе.

MFA/TOTP/WebAuthn в просмотренных auth/web модулях не найдено. Staff MFA из P01 остаётся отдельной реализацией с recovery/enrollment/revoke. Не объявлять её готовой только из-за зрелости основного проекта.

## Frontend, загрузки и authoring

| Исходник | Переиспользование |
|---|---|
| [HTTP client:35](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/packages/shared/src/api/client.js#L35) | Timeout/error classification, AbortSignal, bounded jitter retry safe/idempotent commands, principal pinning при смене аккаунта. Адаптировать transport под generated OpenAPI SDK и cookie+CSRF |
| [Auth coordinator:27](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/api/index.js#L27) | Multi-tab session-change/refresh coordination. При opaque sessions не переносить ненужный access refresh cycle; transient429/5xx не должен означать logout |
| [Query client:65](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/packages/shared/src/queryClient.js#L65), [auth boundary:31](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/context/WebAuthContext.jsx#L31) | Canonical key factories, mutation retry0, очистка cache на смене identity. TTL/staleTime выбрать отдельно по домену; слоты не получают общий5-минутный staleTime |
| [Video upload:81](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/manage/_components/blockEditors/useVideoUpload.js#L81), [slides:66](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/resumableSlideUpload.js#L66) | Stable entity before upload, acknowledged offset/checksum, attempt generation guard, старый asset до готовности нового. После reload File может требовать повторного выбора — не обещать автоматический доступ к локальному файлу |
| [Adaptive polling:41](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/useStudioData.js#L41) | Poll по состоянию/focus/visibility, stop в terminal states, event hint→refetch. Это основа для interviews/jobs, не готовый универсальный authenticated SSE bus |
| [Chunk recovery:65](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/packages/shared/src/lib/chunkReload.js#L65) | Route lazy loading, один recovery reload на build, retry failed namespace. Board/RTC/recorder/authoring не включаются в bundle анкеты |
| [ErrorBoundary:26](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/packages/ui-core/src/ErrorBoundary.jsx#L26), [modal focus:38](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/packages/ui-core/src/useModalFocusLifecycle.js#L38) | Runtime/chunk recovery, nested modal lifecycle, initial/trapped/return focus и scroll locks. Оформление только токенами Опоры |
| [Autosave:95](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/manage/studio/lesson/LessonPanel.jsx#L95), [publish:37](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/manage/studio/hooks/useLessonPublish.js#L37), [preview:35](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/manage/studio/preview/StudentPreview.jsx#L35) | Debounced dirty/saving/error/conflict guards, explicit publish, preview настоящего learner renderer без progress side effects. Адаптировать на release/lesson versions фонда |

## Один общий механизм на одну задачу

Generated SDK + один custom fetch transport, один QueryClient, один asset/upload lifecycle, одна очередь jobs/outbox и одна SQLAlchemy Session на транзакцию — целевая основа. OD helpers извлекаются внутрь этих реализаций; второй SDK, refresh coordinator для отсутствующих JWT, второй cache engine либо новая очередь для Studio не нужны. Resumable slides и video используют общий intent/ownership/offset/finalize contract с разными processor handlers. ffmpeg/office исполняются изолированным media worker, но используют общие jobs/fencing и assets.

SQLAlchemy не требует переписывать уже проверенный сложный атомарный SQL в ORM: допустим явный SQL в новом repository и чистая Alembic migration с теми же constraints/receipts. Переносить минимальную зависимую часть с тестами, а не весь исходный module tree или школьную историю migrations. Это сохраняет рабочие инварианты при замене PostgREST boundary.

## Договорённость об извлечении

Для каждого переносимого блока зафиксировать source commit/path/hash, список зависимостей, destination module, владельца, изменённые guarantees и перенесённые tests. Pure geometry/selection/retry helpers можно портировать с минимальной типизацией. Auth/DB/storage/RTC/provider boundaries требуют адаптации. Школьные UI skins, платежи, Telegram identity, тарифы, миграционную историю и production config не переносить пакетно.

Зависимости третьих библиотек и их лицензии проверить при P00 extraction. Собственные API/БД/storage/provider projects, signing keys и room namespaces Опоры изолированы. Это не копия production окружения Общего Дела.

До приёмки extracted module обязан пройти тесты в окружении Опоры: duplicate/replayed command; race/lease loss; principal switch; scope revoke; malformed upload; retry/timeout и неизвестный provider outcome. Для performance helpers дополнительно проверить saturation, cancellation, stale in-flight completion и bounded cardinality. Развёртывание старого рабочего проекта не доказывает эти свойства нового приложения.

## Закрытие эксплуатационного переноса, 2026-10-22

Сверка исходников интеграции `6dc1a0e` подтвердила: cookie/CSRF/current grants,
общий HTTP transport, receipts, SQL jobs/fencing/heartbeat pool, outbox, purpose-bound
assets/slides уже подключены к доменам. Они не требуют второй очереди, SDK или
provider adapter. Пакетная сборка календаря устраняет измеренный N+1; кеширование
прав и дополнительных индексов для этого не требуется.

Подтверждённый пробел: рабочий цикл не останавливал новые claims при замене,
не выдавал readiness и получал стандартные 10 секунд Docker перед остановкой.
Из `backend/services/jobs/_media_drain.py` и `_worker_heartbeat.py` на закреплённом
OD commit перенесены только expiring owner gate, небольшой heartbeat и подтверждение
простоя. Destination: `apps/api/app/worker/runtime.py`, подключение к существующему
`worker/main.py`; dependencies только stdlib POSIX. Изменённые guarantees: отдельный
runtime path на процесс с эксклюзивным lock, generation после expiry, acknowledgement
только между jobs, проверка release/freshness и graceful SIGTERM. Нет второго job store.
Хеши обоих исходников включены в source snapshot; source tests не выдаются за
приёмку Опоры. Её `tests/test_worker_runtime.py` проверяет expiry/ownership/release,
ограниченные приватные markers и настоящий дочерний процесс: drain не принимает
новую работу, resume продолжает работу, SIGTERM ждёт текущую задачу.

Инструкция frozen-source build и swap находится в `infra/README.md`. Наличие этой
реализации не закрывает supported-amd64 media build, sandbox и длительную запись:
ARM daemon не исполняет закреплённый amd64 образ без отдельно разрешённого окружения.
API readiness пока доказывает доступность БД и Alembic-таблицы; совместимость схемы
проверяется отдельным сравнением live head с head исходников перед swap.
