# P13 profile and recognition

Pages export from `index.ts` for the shared top layouts:

- `ProfilePage`: `/profile` (tabs `?tab=about|skills|avail|docs|notif|privacy`).
- `HoursPage`: `/hours`.
- `CertificatesPage`: `/hours/documents`.
- `PrizesPage`: `/fund/prizes` (old `/fund/profile-review` redirects), prize requests waiting to be issued and the showcase on one screen, `recognition.manage`.
- `DataRequestsPage`: `/fund/data-requests` in the account menu, data export and deletion requests, `profile.requests.review`. Hours are credited automatically and the coordinator side has no hours or letter queues.

The profile uses generated DTOs and the sole transport. Edits pin the opened version; uncertain retries preserve their receipt. Explicit conflict reload discards the open input only when selected. Registration-only access leads to the real login flow. Contact change uses A1's bound canonical challenge, proves the new email, and refreshes the rotated session; it never adopts an identity by an email match. Notifications embed A6's canonical `PreferencesPanel`.

Availability writes the existing CRM source. Pause stops new invitations through P09's current profile check; previously agreed assignments remain visible. AI proposals only show available server suggestions and their source fragments; accept/reject/revert use versioned revisions. Producer-to-profile integration remains the explicit P20 A3/A7 handoff.

Hours show immutable signed ledger deltas and actual pending counts. Manual requests need another coordinator's decision. All five milestones expose their rules; the 28-day milestone requires four real weeks and no missing/absent agreed visit. Gratitude requires current confirmed service facts. The staff picker returns actual names and work, never a raw UUID input.

Certificates render a real Cyrillic PDF through the shared resource-bound asset store. Letter requests need staff review. PDFs retain their issuance snapshot; later ledger corrections remain in history. Own export is a real private ZIP with allowlisted profile, hours, availability, application, consent and document metadata. The deletion request records review, retention explanation, planned processing date and cancellation; approval does not claim account erasure. Completion is refused until the account has actually been processed (`account_state=deleted`).

Source: current `prototype/Profile.dc.html`, `prototype/Hours.dc.html`; original shared tokens/icons, readable text at least 15px, no new navigation. Backend tests live under the profile module. Browser acceptance is a separate gate from the typecheck and HTTP/component tests.

P20 producer UI: `ProfileAIRunPanel` explicitly POSTs `/me/profile/ai-runs` with the saved profile version, polls the canonical status endpoint only while queued/calling, persists the last run ID under the current principal key for reload, and refreshes suggestions after materialization. Saved field opt-in gates the action. Provider-unconfigured/disabled/budget/unknown/source-change states are visible; no generated proposal is invented. Known terminal results permit a new explicit run with a fresh receipt; network retries preserve the unresolved receipt. Four dedicated producer UI tests pass against the typed producer contract.
