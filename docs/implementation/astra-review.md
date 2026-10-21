# Независимое архитектурное ревью Astra

21 октября 2026. Проверен итоговый план, включая все Markdown, обе CSV-карты, граф и manifests. Исправления внесены в сами документы. Приложение, прототип, чужие рабочие изменения и curator-bot не редактировались; commit/push/deploy, provider calls и production-проверки не выполнялись.

## Найденные проблемы и применённые исправления

| Проблема до ревью | Применённое решение и место |
|---|---|
| В тексте существовал `P17 base`, но граф зависел от полного P17. Knowledge/Studio могли ждать внешние каналы без технической необходимости. | P17 разделён на A: внутренние сообщения/contracts и B: доставка. P15/P18B зависят от A. [Пакеты](work-packages.md), [граф](work-graph.json), [карта экранов](screen-map.csv). |
| Shared scene зависела от всего Builder P14; private publish тянул внешнюю доставку, а Knowledge — весь профиль/ledger P13 ради одной интеграции. | P18A стартует после foundation; P18C получает нужную зависимость P14 для lesson target. P18E не ждёт P17B, P15 не ждёт P13. Два реальных cross-package journeys — profile accept/revert и отправка summary — явно принимаются в P20 после обеих сторон, без исключения функциональности. [Пакеты](work-packages.md), [API](api-and-frontend.md), [граф](work-graph.json). |
| Владение backend project wrappers было у A2/P18D после P18C, хотя recording pipeline нуждается в проекте раньше. У слайдов не был определён ранний владелец конвертации. | Projects/takes/renders APIs целиком у A1/P18C, A2/P18D — frontend. Room provisioning и slide-deck/conversion APIs у A4/P18B, уже доступны recording pipeline. [Студия](studio-recording.md), [владение файлами](work-packages.md). |
| Топологические слои выглядели как параллельное расписание, но A4/A7/A2 могли получать пересекающиеся задачи. | Добавлены `required_agents`, исполнимое `resource_schedule` и отдельные cross-package gates. Двойное назначение владельца запрещено; A2 учитывается при renderer/publish UI. [Граф](work-graph.json), [правила команды](work-packages.md). |
| `invitations` и `assignments` дублировали состояния принятия/отказа; `recordings` пересекалась с новыми takes/renders. Отдельная manifest-таблица не имела самостоятельного жизненного цикла. | Одно assignment + events, общая recording-модель live/solo, immutable manifest JSONB/hash внутри render version. Независимые review/publication/history сохранены. Отдельные classes/repositories на каждую таблицу и generic UoW framework не требуются. [Модель](data-model.md), [студия](studio-recording.md). |
| «Связать approved render с lesson version» не различало редактируемый draft и неизменяемую опубликованную версию. Новая обработка могла трактоваться как отзыв approval уже опубликованного старого render. | Явные draft/publication revisions, создание новой immutable version и атомарный pointer swap. Новый render получает собственный approval, старый остаётся историческим фактом. Release snapshots не переписываются; UI показывает фактическую аудиторию новой версии. Publish/discard/cleanup используют согласованный lock protocol. [Студия](studio-recording.md), [модель](data-model.md). |
| Общий lock order не распространялся явно на materializer; attendance начинал с assignment, а series/cancel — с occurrence. Сдвиг нескольких соседних reservations мог конфликтовать на промежуточном состоянии. | Materializer берёт series lock/version; attendance следует общему parent→need→assignment порядку; все ID сортируются. Добавлены DEFERRABLE exclusion для массового сдвига с проверкой до commit, FK consistency need/occurrence, реальные FK reservation source и парные race scenarios. [Модель](data-model.md). |
| API допускал два version conventions; детализация cookie-session/MFA/revoke оставалась в разных местах. | Единый JSON `expected_version` с исключением create, именованные версии для compound publish. Уточнены CSRF/Origin, session rotation, atomic challenge/registration ownership и граница revoke для новых/уже выполняющихся запросов. Staff MFA остаётся собственной реализацией. [API](api-and-frontend.md), [модель](data-model.md). |
| Reuse перечислял несколько клиентов/cache/upload helpers, но не определял единственную целевую реализацию и владельца. | Generated SDK использует один custom fetch transport; один QueryClient и asset/upload lifecycle с разными processors. A2 владеет frontend core, A1 — серверным. Сложный атомарный SQL разрешено сохранить в SQLAlchemy repository, без обязательной переписи в ORM. [Reuse](platform-reuse.md), [API](api-and-frontend.md). |
| Composite + journal мог восприниматься как гарантия точного восстановления. Subscribe-only recorder не ограничивает автоматически состав записываемого звука; provider ready не доказывает приватный playback. | Capture spike фиксирует фактически сохранённые tracks и стоимость dual capture; при отсутствии исходников не обещается re-render. Явные track/audio allowlist, блокировка неизвестной privacy state, private playback gate и сохранение запрета raw fallback при privacy failure. [Студия](studio-recording.md). |
| Карта экранов не отражала участие P19 в Добро.ру/Hours и P15 в AI profile suggestions. | Уточнены пакеты Hours/Profile/Academy; новая механика проекта включает backend P18C. Все исходные 41 board и 5 дополнительных recording mechanics сохранены. [Экраны](screen-map.csv), [новые механики](new-mechanics.csv). |

## Проверка после изменений

Воспроизводимая read-only команда:

```sh
python3 docs/implementation/validate_plan.py --source-root /Users/iliapetri/curator-bot
```

Проверяются: 27 уникальных контрольных задач для 21 основного пакета; известные зависимости и ацикличные слои; полный порядок выполнения без двойного назначения агента; лимит 8 исполнителей плюс интегратор; соответствие таблицы пакетов графу; 41/41 board (35 surfaces, 4 legacy, 2 service); 5 новых механик; ссылки и присутствие всех указанных пакетов; 58 исходных файлов и их SHA-256 через immutable Git objects `38c92cd49b1b6c229ed473de991479ed261e4052`; закреплённые source links и допустимые номера строк.

Исторический reference manifest не обновлялся под параллельные изменения UI. На момент проверки обнаружен drift 40 файлов относительно snapshot; это не дефект реализации плана, но G0 нельзя считать пройденным до утверждённого reference commit. Валидатор сообщает актуальный drift отдельно. Проверка graph/coverage подтверждает структуру и назначение работ, а не реализацию каждого действия, качество дизайна, media performance или зелёные тесты будущего приложения. Исходные OD tests здесь не запускались.

## Решения и ограничения до запуска

Полный список сохранён в [основном плане](README.md). Особенно важны:

- Возрастная policy, роль-зависимая справка, область и срок доступа к фото/памяткам. Отменённое 18+ и неутверждённое 16+ не возвращаются через технический перенос.
- Канал входа/восстановления и фактор staff MFA; реальный sender и владельцы grants/recovery.
- Какие существующие learning assignments получают successor release при замене видео, какие изменения требуют повторного ознакомления. История прогресса остаётся привязанной к первоначальной версии.
- Live recording policy по голосам/камерам/именам, retention и желаемая глубина восстановления. Capture plan, длительность записи, разрешение и A/V budget подтверждаются отдельным media spike в своём окружении; source inspection их не доказывает.
- AI provider/данные/бюджеты, формат Добро.ру, прочие реальные delivery providers, backup/restore и оператор. Неподключённые интеграции не считаются выполненной частью полного scope.

Ни одна из этих неопределённостей не требует сокращения общего объёма. До решений можно реализовать нейтральные contracts и сценарии на обезличенных fixtures; включение для реальных людей проходит соответствующий G4 gate.

После этого ревью интегрированы коммиты Арама до `f7a6f6d`: основная анкета и два дополнительных представления знакомства. Карта и validator теперь учитывают 43 артборда (35 surfaces, 4 legacy, 2 variant, 2 service). Знакомство и запись параллельны; из P06 убрана зависимость от P04. Это последующая синхронизация продуктового scope, не новое независимое ревью Astra.
