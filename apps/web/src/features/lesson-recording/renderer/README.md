# Private renderer boundary — P18C, A2 checkpoint

This directory is separate from the normal application entry. `transport.ts` imports neutral errors only: no AppProviders, session bootstrap, cookie channel, analytics, service worker, local/session storage or device prompt. Shared Scene/CapturePlan/StudioStage remain the sole schema and layout engine.

`createRendererTransport(purposeTicket)` receives a ticket already handed over by the final verified private orchestration channel. **No URL, fragment, query-string or history-based credential transfer is implemented.** A1 owns the final launch channel, purpose signatures, scopes, revocation, generation fencing, renderer API DTOs and server journal. A4 owns the sole subscribe-only LiveKit adapter; no provider client is duplicated here.

This checkpoint provides only the bounded header-auth transport, not a usable recording entry or capture success. Bootstrap/state/readiness operation names are coordinated with A1. Actual generated RendererBootstrapView/RendererStateView/RendererReadinessInput/RendererReadinessView and endpoint wiring wait for A1's tested schema commit. No parallel response DTOs or guessed commands are introduced.

Requests omit cookies and referrers, never put credentials in URLs, bound deadlines/JSON/errors, clear ticket and abort on rejection/close, and fence old responses. POST commands never retry automatically. Keep the same Idempotency-Key for a logical resend after uncertainty; a new key is a new command. Errors never expose HTTP request config or raw provider messages. No console logging of private responses or credentials.

Before readiness, the eventual entry must verify canonical scope/profile/revision, actual subscribed track/audio inventory, approved immutable asset/checksum projections, loaded fonts/images and onPlaying media. A1 decides whether/when provider capture starts after an acknowledged readiness receipt. Unknown privacy blocks capture; no raw fallback. No capture UI, audience controls, private chat, microphone/camera requests or publication belongs in the hidden renderer.
