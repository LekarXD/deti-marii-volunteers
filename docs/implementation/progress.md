# Реализация

Исходный reference `7d07222` опубликован в `main`. После проверки параллельных правок в реализацию включён `62fd0a1`: 41 board plus `Event.html`; два варианта знакомства объединены в один экран с mode по шагам. Предыдущие хеши сохранены в reference-7d07222.json. Реализация собирается отдельно в `codex/implementation`. Незакоммиченные изменения прототипа в основном checkout сохранены.

Один интегратор A0, восемь исполнителей в отдельных worktrees. 21 октября P16 передан от A4 к A5 после сдачи P09; A4 продолжает Studio. Контракты генерируются из фактического FastAPI, миграции пишет только A1. Общая геометрия live/solo/renderer находится в `packages/studio-core`.

| Пакет | Текущее состояние | Проверка / граница доказательства |
|---|---|---|
| P00 | Контракты, workspace и reference зафиксированы | active-reference.json, work graph; ongoing integration |
| P01 | API, session/MFA, права, assets, jobs/outbox подключены | PostgreSQL, concurrency/revoke/receipt tests; production не развёрнут |
| P02 | Токены/SVG/локальный Inter, controls, верхняя навигация подключены | компонентные проверки, Storybook build; полный responsive matrix ещё не принят |
| P03–P05 | Анкета, кабинет и очередь кандидатов подключены; знакомство обновлено по source62fd | серверные тесты; обычные 3 шага формы, draft reload и network retry проверены в браузере; после явного разрешения пользователя вымышленная анкета v5 отправлена через обычный UI и открыла кабинет |
| P06 | Слоты, запись/перенос/отмена, исход и следующий контакт подключены | 6 PostgreSQL тестов; следующий шаг использует единый CRM task store |
| P07–P09 | Роли, возможности, повторы, календарь, участие и attendance подключены | 16 PostgreSQL тестов; CUA: подтверждение/reload, счётчики координатора, отмена, attendance и корректировка; ledger P13 подключён в той же транзакции; корректировки дают delta |
| P10A/B | Участники/группы/фото и памятка подтверждённого назначения подключены | PostgreSQL scope/revoke/compound FK; JSON и фото закрываются при отмене/отзыве; private note не входит в памятку |
| P11 | CRM, резерв, импорт и единые follow-up подключены | 8 PostgreSQL тестов; CUA: импорт двух вымышленных контактов, dry-run/apply, договорённости и следующее действие с reload; mobile351px без горизонтального overflow |
| P12 | Текстовый контур подключён | 11 PostgreSQL + 3 UI проверки; подготовка/рефлексия/restricted Signals, голосовая запись и редактируемая ASR расшифровка подключены через общий gateway, внешний ASR без настройки недоступен; общий браузерный проход ещё нужен |
| P13 | Профиль, часы, документы и review UI подключены | 9 PostgreSQL + 4 UI проверки; реальный PDF/ZIP и scope; общая браузерная приёмка продолжается |
| P14 | Ручной Builder и Academy подключены | версии/review/publish, private attachments, progress и задания проверены PostgreSQL; 2 компонентных проверки |
| P15 | Knowledge/Mentor/Builder AI подключены | published-only FTS/citations, durable provider outcomes, 5 PostgreSQL + 2 UI проверки; реальный внешний AI не вызван |
| P16 | Редактор, приватные диалоги и человеческий review подключены | 7 PostgreSQL проверок; AI gateway подключён, provider unconfigured явно; визуальная приёмка ещё нужна |
| P17A | Внутренние сообщения и outbox подключены | серверные ACL/receipt tests и 3 компонентных теста; двухсессионная браузерная приёмка ещё нужна |
| P17B | Backend A1 и frontend A6 подключены | topics/quiet hours/consent, templates и audience preview; 8 UI + PostgreSQL/loopback SMTP; реальная внешняя доставка не включена |
| P18A | Shared stage подключён | 26 тестов geometry/readiness; CUA desktop и 390px, переключение live/solo и custom layout; это не запись видео |
| P18B | API и UI подключены | PostgreSQL, реальные PDF/PPTX→JPEG, Yjs/WebSocket и LiveKit signaling проверены; настоящее A/V и браузерная приёмка ещё нужны |
| P18C/D/E | В работе A1/A2/A7 | Private renderer kernel и approval/publication guard подключены; реальный короткий SharedStage→RTC→private capture→H264/AAC MP4 получен; кабинет solo подключён; смена материалов/recovery/сквозной UI ещё проверяются |
| P19 | API и экраны отчётов/администрации подключены | PDF/DOCX реально отрендерены и осмотрены; weekly digests, staff scopes и UI проверки; CUA: черновик → review разделов → подтверждение → реальный PDF download; compact settings desktop/mobile390 и журнал проверяются; child attendance unknown без отдельного факта |
| P20 | Независимая QA идёт с начала; общий гейт открыт | Полная карта экранов, обе роли, внешние providers/media/staging и точный release SHA ещё не приняты |

## Проверено на объединённом коде

- Последняя завершённая frontend серия: 211 tests, typecheck и production build. После следующих модулей проверка повторяется по изменённому составу.
- Расширенная серверная серия на 64f4f88: 183 passed, zero skips; после неё focused gate c5f4b92: 32 passed (capture/worker/publication/digests/summary), audit35ccedf: 6 passed. Последующие voice/AI/reporting изменения проходят focused PG проверки; полная серия на итоговом SHA ещё нужна. Независимая QA нашла два attendance edge case; владелец исправил их с 7 focused PostgreSQL проверками. Это не доказательство полного P20.
- Дополнительная объединённая серия voice/AI/learning/followups/recordings: 41 passed, zero skips на 978997a; один pytest process с canonical extensions и запретом внешней сети. Физический микрофон и внешний ASR не использовались. Подробности: infra/evidence/voice-ai-learning-integration-2026-10-21.json.
- G1: 26 обычных HTTP сценариев на API/PostgreSQL (29f5048), без тестовых обходов аутентификации. CUA: вымышленная анкета → запись на 22 октября до знакомства → 4 модуля и тест → координатор видит завершённое знакомство и прежнюю встречу.
- Native PostgreSQL16 используется в отдельных dev/test кластерах, существующие сервисы и SSH tunnel не изменяются. Миграции dev БД по head19 и `alembic check` прошли.
- Восстановление БД и приватного PNG проверено в отдельном QA кластере; детали и ограничения в `infra/evidence/`. Docker compose config проверен, сами образы/контейнеры не запускались ; выделенный media image готовится отдельно, launch/sandbox proof ещё не получен.
- CUA screenshots общей сцены сохранены в `infra/evidence/screenshots/`. Камера выключена, все имена/материалы вымышлены.

## До запуска

Реальный AI, email и RTC/recording providers должны быть настроены и отдельно приняты. Отсутствие интеграции возвращает unavailable/unknown, без ложной доставки/оценки/готового видео. Внешние сообщения, импорт реальной базы и production deployment не выполнялись.

Нет минимального возраста; справка рекомендована, пока роль явно не задаёт иное; знакомство и запись на собеседование независимы; исторический контакт не означает готового волонтёра. Новые разрешения не включают в себя автоматическое согласие на запись аудитории.

## Оставшиеся контрольные пакеты

Открыты P18C (capture/recovery), P18D (полная приёмка кабинета записи), P18E (сквозная запись → review → publish), P19 (общая браузерная приёмка отчётов/администрации), P20 (финальная сквозная и визуальная приёмка). Наличие реализации не равнозначно приёмке. Voice и AI producer уже интегрированы; их общий регрессионный прогон продолжается.

## Обновление дизайна `16f8850`

По прямому уточнению пользователя текущий интерактивный прототип в `codex/interview-journey-ux` — визуальный эталон. Отдельный агент переносит новую недельную компоновку, редактор, карточку события и общие controls/navigation. Технические агенты продолжают capture/длительную запись, связки и проверки. Старая frontend серия211PASS предшествует этому обновлению; новая визуальная приёмка ещё не заявляется.

CUA: email claim сохранил заявку/встречу/4 завершённых модуля; приватное generated MP4 preview → explicit add to Builder → review → publish прошло. Это синтетический fixture публикации, отдельно от native capture proof. Итоги вымышленного вебинара edit → review → publish → audience preview → send доставлены второму тестовому пользователю через настоящий P17 worker, результат delivered и реальный Message.
