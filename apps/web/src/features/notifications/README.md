# P17B notification screens

`PreferencesPanel` is the canonical profile panel, exported without props. It uses
`GET/PUT /me/notification-preferences` with CAS and a retained command receipt.
Channel/topic preferences, quiet minutes and IANA timezone come from the backend;
the CRM no-contact flag remains effective independently. `news_consent` is a
read-only projection of the canonical P13 consent ledger. The news topic links to
`/profile?tab=privacy#profile-consents`; this feature never writes consent records.

`NotificationAdminPage` is exported for the root coordinator router. Templates
are authored as drafts, then reviewed and explicitly published as immutable
versions. Only a published template can open the audience workflow. Recipient
search uses the scoped, paginated name/id projection, not a contact/CRM export.
Editing recipient selection discards the old preview and its confirmation.
Previewing never sends. A separate checkbox and button consume the exact server
preview id/hash. Network retries retain the send receipt; HTTP 409 discards the
preview and requires another review. Expired previews cannot be confirmed.

Readiness is per channel. Unconfigured/development email cannot be sent from
this screen; available in-app delivery remains usable. Success means queued.
The paginated journal and older attempts distinguish provider acceptance,
confirmed delivery, local dev-inbox, quiet-hours deferral, suppression and
unknown outcomes. There is no invented retry endpoint or automatic resend.

All DTOs are generated from A1's OpenAPI schemas (`3dd0052` backend checkpoint),
requests use the sole shared cookie/CSRF transport and principal-scoped query
cache. Rendering uses shared Opora controls and the Settings/Messages source
composition. Root routing, profile embedding, backend and migrations belong to
their respective owners.

Validation: eight UI transition tests use fictional fixtures and a mocked API
boundary; no external delivery occurs. Scoped TypeScript passes against the
actual final backend P17B schemas. A1 owns the real PostgreSQL/local SMTP tests;
these UI tests do not claim external provider delivery or webhook configuration.

Telegram proof is a separate `TelegramBindingPanel` («Подключить Telegram»), exported for the profile «Обо мне» tab next to contacts; it is no longer rendered under preferences. It uses the generated Telegram DTOs and current-principal query key, explicitly issues a one-use bot URL, waits for the real server status, supports pending cancellation/linked disconnect with versions, and preserves unresolved retry receipts. The raw link is held only in component state, is never stored in browser storage, and disappears after confirmation/cancel/expiry. The card never enables topics/news consent or claims Telegram delivery. Disabled server configuration displays unavailable with no invented URL.

Four focused Telegram UI tests cover unavailable, issue→pending→confirmed status reads, stable network retry/pending cancellation, and versioned disconnect. Existing eight preference/template/delivery tests isolate that sibling proof component and remain green. Actual Telegram proof persistence and privacy have eleven separate local PostgreSQL/HTTP tests; no real bot was configured or contacted.
