# Messages UI

Exports `MessagesPage` (also CandidateMessagesPage / CoordinatorMessagesPage). Mount inside the shared AppProviders + candidate/coordinator layout. Routes should be `/messages` and `/fund/messages`; A0 owns route wiring.

All DTOs import generated `components` and all requests use shared `api`; no private fetch client or QueryClient. Root regenerates the SDK after mounting the backend router. The local generated schema used for compilation is not part of this feature commit.

Prototype reference: `prototype/Messages.dc.html`. Preserves 300px dialogue list, rounded white chat, selected yellow row, avatar stack, message bubbles, composer, read-only system state and mobile single-column layout. Adds actual loading/error/empty states and persisted messages. AI summary and face blur remain explicitly unavailable; raw images require a no-people confirmation before send. PDFs and PNG/JPEG/WebP up to 10MB use the common acknowledged upload lifecycle.

Three focused UI tests cover draft isolation between threads, image policy gating and retrying an unknown send outcome with the same key. Backend HTTP tests separately establish two actual authenticated sessions, ACL revoke, unread, attachment links, and receipts; mocked UI tests alone do not prove browser/backend integration. Visual/mobile and two-context browser integration are the A0/A8 acceptance gate.
