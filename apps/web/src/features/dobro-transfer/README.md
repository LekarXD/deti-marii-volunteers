# Manual Добро.рф transfer

`DobroTransferPage` (named and default export) expects the root coordinator route
`/fund/integrations/dobro/transfers`; the root owns permission routing/navigation.
The server requires `hours.review`. All DTOs come from the generated actual API.
This feature owns no ledger calculation, delivery adapter or external CRM session.

The page selects a month with existing custom controls, shows the server summary,
activity groups, deadlines and separate daily-cap/overlap/duration notes. Rows show
cumulative recorded hours, signed due amounts, carry and immutable history.
`not_needed` rows collapse within their activity. Participation is never changed.

Individual/bulk marks require explicit confirmation of prior manual CRM work.
Partial signed integer amounts are allowed within the current due amount; negative
corrections require a note. Applied enrollment approval is part of the same server
mark command. The page waits for its receipt and never claims Добро.рф delivery.
The API's 200-row bound is visible; there are no silent background batches.

A `dobro_snapshot_changed` conflict preserves amounts/note, reloads authoritative
rows only on an explicit action and requires new consent. Command keys survive
uncertain outcomes in memory, with unsafe retries disabled. Reads/mutations share
canonical principal-scoped `keys` under the `dobro` domain. No PII is persisted.

Copy-list creates a TSV from current actionable rows only. Reminder text comes
from the actual configured server template and is copied, never sent. Clipboard
failure opens selectable text. External links are restricted to trusted HTTPS
Добро hosts; no external page is automated. The existing Opora controls, Inter,
SVGs, palette and top-level coordinator layout are reused. At narrow widths each
semantic table row becomes a readable record without shrinking below 15px.

Focused tests cover actual command snapshots/receipts, signed corrections, bulk
selection, conflict review, command-key reuse, copy-only reminders/TSV, source
notes and trusted links. Actual API/Postgres and browser screenshots are separate
integration gates owned by the module owner/root.
