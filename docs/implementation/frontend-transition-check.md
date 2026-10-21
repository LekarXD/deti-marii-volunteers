# Bounded frontend transition check

Scope: integrated routes at `6dc1a0e`, P12–P17 and the existing P19 Admin entry. Static inspection and component tests; browser acceptance remains with the shared CUA pass. No external channels or provider actions were exercised.

| Journey | Inspected connection | Result |
| --- | --- | --- |
| P12 preparation/reflection/voice | Assignment preparation and reflection routes; recorder upload/status/retry/cancel; staff signal/reflection review | Existing source-bound routes and text fallback connected; no additional confirmed transition defect in this pass. |
| P13 profile/hours/documents | Profile tabs, confirmed hours, manual requests, documents/downloads, consent and data-request controls | Existing pages route to real operations and surface failed writes/downloads. Profile review is reachable from reporting letters; no missing-route finding claimed. |
| P14 Academy | Track → lesson → quiz/task → completion → assessment | Fixed stale cached-lesson quiz feedback/completion notice and assessment attempt retained across assignment transitions. |
| P15 Mentor | Ask → queued result polling → source dialog → coordinator escalation/report | Existing result/source error and coordinator fallback paths connected. Provider availability is not claimed by static inspection. |
| P16 simulator | Direct scenario → retry; cached attempt navigation | Fixed retry targeting the list instead of failed scenario detail and local text crossing into another cached attempt. |
| P17 messages/notifications | Unverified sign-in → messages; composer retry; template publication → preview → explicit send → journal | Fixed sign-in CTA targeting nonexistent `/account`; it now uses `/login?next=%2Fmessages`. Existing composer retries retain their receipt. |
| P19 Admin | Staff grants/invites, integration health, notification and audit panels | Existing operational panels connected. The assigned signal-threshold follow-up now has real settings, five canonical-source detectors and an internal review queue; see the followups module README. Reports backend/export closure is outside this pass. |

Focused reproductions: 8 passing component tests across `AcademyPage.test.tsx`, `SimulatorPage.test.tsx`, and `MessagesPage.test.tsx`. They exercise actual route/hook transitions with synthetic API fixtures, including already-cached destinations; they are not live CUA or provider proof.

Signal-rules closure: source defaults remain 2/21/14/3/7; settings save/reset/evaluate use CAS and current foundation permissions. Admin numeric validation/cancel/reset and derived-queue reason-required closure have component coverage. Canonical PostgreSQL source fixtures cover all five detector matches, changed thresholds, unknown source facts, explicit source corrections, current group/domain access, revoked owner and no-message behavior. These tests supplement, rather than replace, root CUA and release acceptance.
