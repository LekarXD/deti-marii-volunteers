# Студия занятий и записи уроков

Дополнение к P14/P18: один движок сцены для **онлайн-занятия с участниками** и **записи урока автором без аудитории**. Пользователь видит готовую композицию «презентация + плашка преподавателя» до старта и получает такую же композицию в итоговом видео, а затем может просмотреть и опубликовать материал в обучение фонда.

Основа — текущий код Общего Дела, commit `38c92cd49b1b6c229ed473de991479ed261e4052`. Проверка read-only; новые звонки/записи/provider тесты в этой работе не выполнялись. Отдельный законченный solo-authoring workflow в просмотренных studio/manage/API файлах не найден: `soloScene` означает camera-only layout, `/recorder/state` — скрытый Egress renderer. Новый пользовательский сценарий строится поверх существующего media ядра.

## Два входа в один движок

| Вход | Путь |
|---|---|
| «Провести онлайн-занятие» | Выбрать занятие/вебинар → настройки и устройства → загрузить презентацию → репетиция сцены → открыть комнату → провести/при необходимости записать → итог и материалы |
| «Записать урок» | Builder/Академия → создать draft recording project → название и место в треке → камера/микрофон/презентация → проверить готовый кадр и звук → записать дубль → обработка → приватный просмотр → оформить → опубликовать |

Запись без аудитории не создаёт занятия в календаре волонтёров, enrollment, attendance или массовых уведомлений. Транспортно это может быть закрытая LiveKit-комната автора и recorder. Это не обещание записи без интернета.

В иммерсивной студии остаётся понятный выход в редактор с сохранением проекта. Верхняя навигация платформы и логотип на одной линии сохраняются в обычных layouts; controls/меню не включаются в записываемую сцену.

## Что уже есть в исходном коде

| Источник | Перенос |
|---|---|
| [stageComposition.js:71](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/stageComposition.js#L71) | Каноническое состояние сцены: screen → board → slides → camera; layout/theme/presenter_size; типизировать как `StudioScene` |
| [stageGeometry.js](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/stageGeometry.js), [cameraLayout.js](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/cameraLayout.js) | Pure geometry contain/fit, presenter frame, side/overlay, mobile views; единое ядро для live и recorder |
| [StudioStage.jsx:78](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/StudioStage.jsx#L78), [RecordingStage.jsx:11](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/recording/RecordingStage.jsx#L11) | Presenter tile/name, slides/annotations/screen/board; отдельный headless renderer использует ту же геометрию |
| [useSlideFlip.js:48](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/useSlideFlip.js#L48) | Быстрые/coalesced flips, optimistic index ведущего, expected_revision и409 refetch. Server остаётся source of truth |
| [slides_convert.py:1](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/slides_convert.py#L1), [resumable_slides.py:32](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/resumable_slides.py#L32) | Загрузка с offsets/checksums, sniff содержимого, office→PDF→slide images, отключение макросов/внешних relationships; адаптировать на новые assets/jobs |
| [LiveKitBoard](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/studio/media/livekit/board/LiveKitBoard.jsx), [board_snapshots.py:41](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/board_snapshots.py#L41) | Yjs/Excalidraw, shared board, scopes, snapshots и timestamps; свой namespace и assets |
| [Stage journal:26](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/migrations/839_lms_studio_stage_events.sql#L26), [recording_timeline.py:33](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/recording_timeline.py#L33) | Версии/события сцены и media clock, pause/resume source timeline. Перенести инварианты в новые Alembic schema/services |
| [livekit_composite.py:31](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/livekit_composite.py#L31), [recorder_auth.py:46](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/recorder_auth.py#L46) | Custom-template Egress записывает готовую browser-сцену; подписанный layout ticket + hidden subscribe-only recorder grant |
| [recording_compose.py:12](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/recording_compose.py#L12), [recording_stage.py:58](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/recording_stage.py#L58) | ffmpeg fallback/re-render, согласованная геометрия, media timestamp offsets и A/V clock |
| [media_checkpoint.py:66](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/media_checkpoint.py#L66), [media_transfer.py:108](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/media_transfer.py#L108) | Persistent spool/hash/flock, fenced job, resumable upload/ambiguous outcome, provider processing readiness |
| [media_recordings.py:236](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/media_recordings.py#L236), [useLessonPublish.js:37](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/apps/web/src/pages/learn/manage/studio/hooks/useLessonPublish.js#L37) | Stable media attachment, provider readiness, optimistic lesson version, реальный learner preview/publish; заменить автоматическое прикрепление явной командой |

Composite в source-документе отмечен как opt-in/off by default. Проверка исходников не подтверждает нынешнюю production-конфигурацию, длинную запись или вместимость сервера. В P18B/P18C проверить выбранные версии LiveKit/Egress и выполнить свой длительный media test; не выбирать второй RTC provider без причины после уже найденного LiveKit ядра.

## Контракт сцены

```text
StudioResource = live_event | lesson_recording_project
StudioScene = {
  resource_id, session_id, take_id?, revision, render_profile_version,
  content_kind: slides | screen | board | camera,
  deck_version_id?, slide_id?, board_snapshot_id?,
  presenter_identity, presenter_display_name,
  layout: side | overlay | camera_only,
  presenter_size, theme_id, recording_policy_id
}
```

Имена layouts можно расширить, но не копировать брендовые «арку/онлайн-школу/Общее Дело» как обязательный стиль. Пользовательская плашка, подпись и фон соответствуют Опоре. Фото/маска/размер камеры не перекрывают значимые части слайда. Branding и геометрия параметризованы одинаково для preview/live/recording.

Слайд привязан к immutable deck version. Подмена презентации в проекте не меняет старую запись. Только host может менять общую сцену; data channel сообщает revision/refresh hint, не предоставляет право переписать state. Renderer получает минимальную projection сцены, без чата, анкет и внутренних заметок.

## Путь автора

1. Создать запись в Builder или Академии, выбрать целевой урок/раздел либо сохранить независимый draft project.
2. Preflight: устройства/уровень микрофона, camera off/avatar, загрузка и готовность slides, выбор композиции, короткая проверка звука. До старта показывается будущий кадр16:9.
3. «Начать запись»: сервер идемпотентно создаёт take/generation. Состояние «идёт запись» показывается после подтверждения capture pipeline, не по локальному нажатию.
4. В процессе: слайды, pointer/аннотации, доска, демонстрация экрана и смена композиции. Видны elapsed time, capture status и понятная проблема при разрыве.
5. «Завершить» закрывает capture; UI показывает finalizing/processing и может уйти в список проектов. Падение HTTP не теряет job. Retake создаёт новый take, предыдущий остаётся до явного удаления.
6. Готовый дубль — приватный draft: настоящий player, seek, проверка звука/начала/середины/конца, выбор дубля, название, описание, обложка, материалы и аудитория.
7. Автор/методист с permission выбирает «Опубликовать». Проверяются конкретный render hash, текущая lesson version и разрешённая аудитория. До этой команды recording не видна обычному волонтёру.
8. Замена опубликованной записи не убирает прежний primary asset до готовности и подтверждения нового. Rollback возвращает конкретную прошлую publication version.

В базовом пакете есть start/stop/retake. «Пауза/продолжить» добавляется только вместе с take segments и корректной склейкой media clocks; смена иконки не считается паузой записи. Простая обрезка начала/конца может быть отдельным derived render с сохранением оригинала; полноценный видеоредактор не является условием этого сценария.

## Capture, processing и публикация разделены

```text
project: draft → prepared → has_takes → archived
take: created → capturing → stopping → captured / failed / discarded
render: queued → rendering → provider_processing → preview_ready / degraded / failed
review: pending → approved / rejected
publication: published → withdrawn (append-only events; current pointer в lesson)
```

Сам автор может иметь и review, и publish permissions; отдельный reviewer не обязателен для каждого урока. Approval относится к точному render hash, а не к проекту вообще. Новый render/trim требует собственного approval; approval старого неизменённого render остаётся историческим фактом и не переносится на новый. Publish проверяет target lesson draft/publication revisions. P14 определяет, создаёт ли это новый release или обновляет текущую доступную publication; существующий progress всегда ссылается на исходную immutable version.

**Не копировать source defaults:**

- [Worker:48,114](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/jobs/lms_studio_media.py#L48) автоматически публикует ready recording, в том числе после рестарта. В Опоре ready создаёт preview/task, не publish.
- [Compose fallback](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/services/lms_studio/recording_compose_plan.py#L291) может использовать original при проблеме сборки. Cosmetic degraded output требует review. При нарушении recording privacy policy raw fallback блокируется полностью; нельзя опубликовать лишние лица/голоса/имена.
- [Stage trigger](https://github.com/Petrimaze/curator-bot/blob/38c92cd49b1b6c229ed473de991479ed261e4052/backend/migrations/839_lms_studio_stage_events.sql#L125) сохраняет journal best-effort. Для восстановленной записи полнота manifest проверяется; потерянное событие не даёт обещать точную сцену.
- `course`, тарифы, school enrollments, OD storage prefixes/provider project IDs и старые issuer/keys заменяются Opora UUID/scopes/adapters.

## База данных и API дополнения

| Сущность | Что хранит |
|---|---|
| `recording_projects` | owner/foundation, mode, target lesson draft, metadata, recording policy, scene preset, version |
| `studio_capture_sessions` | resource/session kind, room, host, start/end, active generation; solo отдельно от attendance |
| `recording_takes`, `recording_source_files` | project, take number, session/generation, capture state, исходные asset/provider IDs и clocks |
| `recording_stage_events` | monotonic sequence/revision, server/media timing, точные версии slides/board/layout |
| `recording_render_versions` | take, immutable manifest JSONB/hash (sources/checksums/scene/profile/policy/completeness), job, output checksum/asset, quality/degraded/error, duration |
| `recording_reviews`, `recording_publications` | reviewer/approval render hash, lesson_version/target block, visibility, publish/withdraw events |
| `slide_decks`, `slide_deck_versions`, `slide_assets` | upload/conversion state и immutable pages с порядком/размерами |

Backend projects/sessions/takes/renders принадлежат A1/P18C; slide-deck APIs/conversion принадлежат A4/P18B и используют общие assets/jobs P01; P18D/A2 владеет UI и использует уже готовые APIs. P18B/A4 предоставляет resource-neutral room/session operations для live и solo, не зависит от нового solo UI. Live запись тоже получает recording project; `GET /webinars/{id}/recordings` — scoped projection publications этих проектов.

`jobs` и `media_assets` общие с P01. Raw, spool, rendered output, provider copies, thumbnails, board snapshots и transcript имеют явную retention policy. Не удалять исходники автоматически сразу после processing ready; они нужны до review/retake/повторной сборки. `flock` защищает только общий filesystem; при нескольких media hosts нужны distributed DB fences и доступные checkpoints.

API:

```text
POST /recording-projects
GET/PATCH /recording-projects/{id}
POST /recording-projects/{id}/prepare
POST /recording-projects/{id}/takes
POST /recording-takes/{id}/start|stop|discard
GET  /recording-takes/{id}
POST /recording-takes/{id}/renders
GET  /recording-renders/{id}/status|preview
POST /recording-renders/{id}/approve|reject
POST /recording-projects/{id}/publish|withdraw
POST /slide-decks/upload-intents
GET  /slide-decks/{id}/status
GET/PATCH /studio-sessions/{id}/scene
```

У всех изменяющих команд ownership, permission и idempotency; expected_version требуется для существующего изменяемого агрегата, create использует правила общего API-контракта. `publish` принимает render_id/hash, target lesson ID, expected_draft_revision и expected_publication_revision. В одной транзакции блокирует project/render и stable lesson в общем для всех publication commands порядке, повторно проверяет права/approval/readiness, создаёт новую immutable lesson version с одним canonical video block, обновляет publication pointer и пишет audit/outbox. Опубликованную lesson version не редактирует. P14 release snapshot ссылается на точные lesson versions: изменение lesson pointer не меняет уже выданное обучение. При публикации в опубликованный трек создаётся successor release; назначение новой версии существующим пользователям — явная policy с сохранением progress, а не скрытое изменение release. Publish response/UI показывает созданную version/release и фактическую доступную аудиторию; одно сохранение lesson pointer не выдаётся за обновление всех назначений.

Проверка approved/render hash, отсутствие discard/delete и swap publication атомарны. Discard, retention cleanup и publish используют один порядок project → render/asset → lesson; cleanup не удаляет опубликованный или удерживаемый активным review/job asset. Удаление provider copies выполняется отдельной fenced job после проверки ссылок, не внутри DB transaction. Media provider readiness само по себе не открывает публичный доступ: draft asset/playback авторизуется через текущий scope, provider privacy settings проверяются до preview_ready. Если provider не обеспечивает нужную приватность, использовать закрытое storage/playback, не публичный draft URL.

Потерянный ответ и повтор не дублируют блок. Старый webhook относится к точному session/take/generation, никогда не меняет «последний проект» по приблизительному поиску.

## Media pipeline

Предпочтительный кандидат — browser composite Egress на общем renderer: он захватывает тот кадр, который автор проверил. Source tracks+stage journal и ffmpeg остаются механизмом recovery/повторной сборки при наличии полных исходников. Наличие room-composite файла само по себе не означает, что сохранены отдельные camera/screen/audio tracks. P18C spike фиксирует выбранный capture plan и реальные артефакты; dual capture добавляется только при выбранном требовании восстановления, с измерением CPU/storage/cost. При отсутствии источника доступен retake/повтор передачи готового composite, но не обещание точного re-render. Качество fallback показывается явно; приблизительный board snapshot не выдаётся за точный replay.

Два web entry: обычное приложение и отдельный recorder без App/auth UI/analytics/service worker. Его доступ — signed scene ticket + hidden subscribe-only media grant, scoped на foundation/project/session/take/generation. Subscribe-only ограничивает право публикации, но не выбирает разрешённые к записи tracks: серверный capture plan задаёт allowlist identities/track IDs и audio routing. Hidden recorder не допускается к private chat/data channels. Неизвестный track/privacy state блокирует готовность; это проверяется в итоговом файле, а не только в скрытом UI. Secret/query не логировать, credentials только в памяти. Запись не включает host controls, личный чат и служебные меню.

Цепочка: capture → finalize → durable media job → проверка manifest/источников → render или validated precomposed output → private storage/provider transfer → readiness и media QA → preview_ready → явный publish. Kinescope adapter может быть переиспользован, если он выбран фондом; контракт storage/processing/playback не должен заставлять использовать школьный provider project.

Отдельный media worker с CPU/disk quotas, persistent spool, checksum/fencing и drain перед заменой. UI завершения комнаты не ждёт тяжёлый import. Неизвестный результат StartEgress/Tus init сначала сверяется с provider/job identity, повторный старт вслепую запрещён.

## Обязательная приёмка P18

- Реальный live: два браузера, host controls, camera/mic/screen, slides/annotations/board, reconnect, permissions, leave, revoke до join и во время звонка.
- Реальный solo: создать проект из Builder → preflight → take → stop → processing → preview → retake → выбрать дубль → publish → открыть как волонтёр. Ни календарной рассылки, ни learner join в private session.
- Итоговый **файл**, а не screenshot UI, содержит имя/плашку преподавателя, читаемую презентацию, нужные смены сцены и звук. В нём нет controls/chat. Проверить начало/середину/конец и длительную запись; выбранный целевой профиль1080p и A/V-sync budget утвердить после media spike.
- Host preview, audience view и recorder используют одну scene schema/геометрию. Проверить16:9/4:3slides, camera off/avatar, long name и screen audio. Desktop/mobile обзор не меняет скрытно композицию записываемого кадра.
- Ready/restart не публикует автоматически; preview не отмечает чужое обучение пройденным. Чужой user не получает draft/player/asset.
- Concurrent publish/lesson edit возвращает409. Approval предыдущего hash не действует на новый render. Неудачная замена сохраняет опубликованный primary.
- Restart в download/render/upload, stale lease, два workers, late/replayed/missing webhook, corrupt checkpoint, disk full, provider timeout, неизвестный upload outcome и degraded output имеют безопасное recovery.
- Privacy compose failure не публикует original. Live recording policy определяет участие камер/голосов аудитории заранее; solo по умолчанию записывает только автора и разрешённый контент.

Переносимые тесты: `test_studio_recording_compose.py`, `test_live_recording_composite.py`, `test_lms_studio_media.py`, `test_lms_studio_import_crash_cap_real_pg.py`, `RecordingStage.test.jsx`, `StudioStage.test.jsx`, `useSlideFlip.test.jsx`, `LessonPanel.publish.test.jsx`, `StudentPreview.sandbox.test.jsx`. Их сначала адаптировать к новым contracts; факт наличия в OD не является зелёным результатом для Опоры.
