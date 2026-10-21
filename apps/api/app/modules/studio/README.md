# P18B operational studio

The API exports `router` from this module. It owns webinar enrollment, one resource-neutral `StudioSession`/provider room, server-authoritative scenes and immutable slide decks. P18C owns capture sessions/takes/renders referencing `studio_sessions.id`; P18B does not create competing recording tables or publish recordings.

Main routes:

- `/webinars`: list/create; `/{id}` read/edit; `/{id}/publish`, `/enroll`, `/withdraw`, `/join-token`; host `/{id}/enrollments/{user_id}/revoke`.
- `/studio-sessions`: prepare a resource; `/{id}` read; `/scene` read/CAS patch; `/start`, `/join-token`, `/ready`, `/close`.
- `/studio-sessions/{id}/board-token`, `/board-grants`, `/board-snapshots`; signed sidecar introspection `/studio-board/authorize`.
- `/slide-decks/upload-intents`, `/{id}/status`, `/{id}/retry`; scoped immutable `/slide-pages/{id}/content`.
- Signed provider webhook `/studio-provider/webhook` queues identity/enrollment reconciliation.

Every durable command uses fresh auth, resource scope, idempotency, optimistic versions, audit and commit-before-success. Tokens are short-lived ephemeral POST responses, rate limited and bound to actual auth-session UUID; raw tokens are not saved in receipts. Audience join requires current published resource enrollment and a truly live session. `/start` only creates an opening room; `/ready` requires the provider to list the assigned host. Unconfigured providers return unavailable. Close remains `closing` until its durable provider job confirms deletion. Strict token revocation policy fails closed for providers that do not support it; self-hosted removal is not claimed to invalidate old JWTs.

P18A JSON schemas are the only scene/capture grammar. Install their two files and set `OPORA_STUDIO_SCHEMA_ROOT` in packaged deployments; source checkouts discover the canonical package. The browser cannot change foundation/resource/session/take/presenter identity through scene patch. Page/snapshot IDs, hashes and dimensions must match actual authorized immutable assets. Public audience asset access is limited to the currently broadcast content.

P18C integration exports `ResourceContext`, `register_resource_authorizer`, `create_session(...,resource_authorizer=...)`, `bind_capture_take(...,take_authorizer=...)`, `register_close_guard`, and `register_internal_participant_authorizer`. Take binding and close guards must follow P18C project/take -> operational session lock order; guards only inspect capture state and must not acquire inverse project locks.

Slides use only P01 purpose-bound uploads (`studio.slides`) and the shared fenced job registry. PDF/PPTX and PNG/JPEG/WebP source bytes are sniffed/validated. Pinned source helpers enforce archive limits, isolated LibreOffice profile/macros/proxy settings and bounded page rendering. A dedicated media subprocess receives no API/provider/DB secrets and is killed together with its LibreOffice child on timeout or lost lease. Publish of output rows occurs only after the shared job fence; no automatic lesson publication. Dedicated worker: `python -m app.worker.main --kind slides.convert`; RTC maintenance uses explicit `studio.close`, `studio.revoke`, `studio.reconcile_participant` kinds, not the default outbox worker.

Tests currently cover actual PostgreSQL scene races/ACL/transaction facts, provider-ack state sequencing through a controlled HTTP adapter, current enrollment, real signed token scopes, current auth-session board introspection, purpose-bound upload/image conversion and lost-lease non-publication. They do not prove a real configured LiveKit deployment, physical camera/mic permissions, two-browser audio/video, PowerPoint office deployment or final recording media. Those remain explicit media acceptance gates.

After-live summaries use separate immutable text revisions, never recording assets. Ended-webinar draft/edit, explicit review and explicit publish require current foundation `studio.manage`; audience preview/send additionally require `notifications.send`. Current enrolled users can read only the published text. Editing clears review but retains the prior publication until another reviewed revision is explicitly published.

`GET/PATCH /webinars/{id}/summary`, `POST .../review|publish|audience-preview|send` use version/revision CAS and idempotency receipts. Preview snapshots current enrolled audience, enrollment versions and P17 in-app learning-topic policy for fifteen minutes. Send recomputes the snapshot and enqueues source-bound P17 notices exactly once per publication/recipient. Worker source resolution rebuilds immutable published text under current sender grants and enrollment; withdrawal/revocation, newer publication, no-contact/topic policy or quiet hours are rechecked before actual internal delivery. No email, auto-publication, auto-send or recording access is implied.
