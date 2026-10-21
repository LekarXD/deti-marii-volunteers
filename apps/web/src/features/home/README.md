# Volunteer home

Export `HomePage` from `features/home`. The router supplies `CandidateLayout` and the
verified-user route/landing decision; this feature does not bootstrap a session.

Composition follows `prototype/Home.dc.html`: the greeting and yellow upcoming
class hero, invitation cards in the source `match` grid, learning/preparation cards,
and a coordinator question panel. Colours, fonts, radii, spacing and SVGs reuse the
shared original Opora kit. There is no sidebar or demonstration mode selector.

Data reuse:

- `activities/participationApi.usePersonalSchedule`: a bounded window of 90 inclusive
  Moscow calendar days, with server `state=active`. No historical assignment scan.
  Pagination remains explicit: a partial window asks the user to load another page
  before claiming which event is nearest. An in-progress class remains relevant
  until it ends. Cancelled/postponed occurrences and closed/attended assignments
  never appear as upcoming. Failed pagination is never presented as an empty list.
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
An empty date window does not prove that someone is a newcomer. Its copy names the
90-day window and offers the application/interview path conditionally, alongside
opportunities and the full personal schedule.

`HomePage.test.tsx` exercises these actual hooks with typed DTO fixtures and mocked
sole transport reads, including pagination and recovery. Browser screenshot proof
belongs to the integrated `/home` route; a component test is not a visual gate.
