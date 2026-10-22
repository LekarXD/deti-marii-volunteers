# Volunteer home

Export `HomePage` from `features/home`. The router supplies the volunteer layout and the
verified-user route/landing decision; this feature does not bootstrap a session.

Composition follows the canvas board `Home.dc.html` on desktop and `Phone.dc.html`
(phone 1) at ≤720px: greeting, one hero, the state section, «Тебя приглашают»,
«Подобрано для тебя», the «Обучение» and «Мой путь» cards and the link to
«Что делать, если…». Shared blocks come from `ui/volunteer.css`; `home.css` holds
only the board's own rules, scoped by `.volunteer-home`.

Hero states (`model.ts`, all from real data):

- **Сегодня**: the nearest confirmed занятие starts today in the event timezone or is
  in progress. Time range, place and «{имя} встретит у входа» when the memo has a
  contact. «Открыть памятку» and «Опаздываю»; the latter posts an ordinary question
  (`POST /me/assignments/:id/questions`, text «Опаздываю на занятие») and the note
  «Координатор знает, что ты задержишься» stays while that question exists. Below it,
  «Сегодня в группе» shows the confirmed group briefing and the meeting contact.
- **Ближайшее занятие**: the nearest confirmed занятие. «Подготовиться» and «Не смогу».
- **Тебя приглашают**: the nearest item is a coordinator's invitation (always answered
  by the volunteer, even when the role needs approval). «Я приду» confirms
  (`POST /assignments/:id/confirm`), «Не смогу» declines.
- **Твой первый выход**: there is no confirmed занятие that already ended in the past
  year of `/me/schedule` (read page by page until one is found; `/me/hours` is not
  used for this). An invitation offers «Я приду» and «Подробнее»; the page adds
  «Как проходит начало», whose current step follows the status (invited → step 2,
  confirmed → step 3).
- **Ждёт ответа координатора** / **Освободилось место из резерва**: a self sign-up or a
  freed reserve place (`participationApi.awaitingCoordinator`) has nothing to answer;
  a calm hero with «Подробнее» and «Отменить заявку» / «Не смогу» (decline).
- Nothing ahead, an incomplete schedule or a just declined занятие get a calm (paper)
  hero; the yellow one is for a real занятие.

«Не смогу» always asks inline first (FirstExit.dc.html) and then calls
`/assignments/:id/decline` for an invitation or `/cancel` for a confirmed занятие with
`expected_version`. Rows in «Тебя приглашают» answer inline and keep the answer
(«Ты придёшь» / «Ты не придёшь»).

Data reuse:

- `activities/participationApi.usePersonalSchedule`: 90 inclusive Moscow calendar
  days, server `state=active`. Pagination stays explicit: a partial window asks to
  load the next page before claiming which занятие is nearest. Failed pagination is
  never shown as an empty list.
- `followups/api.readPreparation`: contacts and questions of the confirmed hero item,
  on the same `assignment-preparation` key as the preparation page.
- `participants/api.readAssignmentBriefing`: the group on the day of the занятие, only
  when the memo says the briefing is available.
- `activities/eventsApi.useEventFeed`: the first three open events in server order,
  without ones that are full, conflicting or already the volunteer's, drawn with the
  feed's own `EventTile` (places and «Баллы ×1,5» exactly as in «Все мероприятия»).
- `learning/api.usePreparation`: the current track and completed lessons.
- `profile/api.useHours`: level, hours and points exactly as `HoursView` returns them.
- `profile/api.useProfile`: the first name for the greeting; without one it is «Привет!».

Home never invents names, dates, hours, points, levels or matching scores.
`HomePage.test.tsx` exercises the real hooks with typed DTO fixtures and a mocked
transport, including pagination, recovery and every command the page sends.
