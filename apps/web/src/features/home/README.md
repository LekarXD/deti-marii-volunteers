# Volunteer home

Export `HomePage` from `features/home`. The router supplies `CandidateLayout` and the
verified-user route/landing decision; this feature does not bootstrap a session.

Composition follows `prototype/Home.dc.html`: the greeting and yellow upcoming
class hero, invitation cards in the source `match` grid, learning/preparation cards,
and a coordinator question panel. Colours, fonts, radii, spacing and SVGs reuse the
shared original Opora kit. There is no sidebar or demonstration mode selector.

Data reuse:

- `activities/participationApi.useAssignments`: all cursor pages before selecting
  the nearest active invited/confirmed class, ordered by the actual start instant.
  An in-progress class remains relevant until it ends. Closed/attended entries do
  not appear as upcoming; failed pagination is never presented as an empty list.
- `learning/api.usePreparation`: assigned learning tracks and the actual completed
  lesson count. Links use the existing Academy routes; absent lessons never become
  an `undefined` lesson route.
- `followups/api.readPreparation`: the nearest confirmed assignment's contacts,
  location and checklist, on the same `assignment-preparation` key as FirstShiftPage.
  Checklist changes and questions stay on that existing page.

Assignments refresh every 30 seconds and preparation every 15 seconds. All reads
use domain APIs, principal-scoped cache keys and the sole ordinary API transport.
Home never confirms an invitation, modifies a checklist, or invents attendance,
hours, matching scores, personal names or milestones.

`HomePage.test.tsx` exercises these actual hooks with typed DTO fixtures and mocked
sole transport reads, including pagination and recovery. Browser screenshot proof
belongs to the integrated `/home` route; a component test is not a visual gate.
