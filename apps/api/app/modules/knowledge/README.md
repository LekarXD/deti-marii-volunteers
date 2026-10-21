# Knowledge and shared AI gateway

Knowledge sources are editable drafts with CAS versions. Review and publication create immutable source versions; the separate index job makes a publication searchable. Editing or importing a replacement PDF preserves the previous publication. Archive immediately removes a source from retrieval and citations; old Mentor responses and command replays recheck access. Report evidence is a private immutable snapshot for authorized review.

`seed_knowledge(db, foundation_id)` explicitly imports the four already-published introduction modules after `seed_introduction`; it does not invent foundation facts or import assessment answer keys. It is idempotent and queues real index jobs. No runtime fallback populates missing production data.

Run the shared worker with explicit bounded kinds:

```sh
python -m app.worker.main --kind knowledge.index --kind knowledge.ingest --kind ai.generate
```

The default worker only handles notifications. A queued source or AI run is never displayed as completed before its handler commits. PDF ingestion uses the authorized private asset service, a 200-page/200,000-character budget and a 30-second extraction timeout. Scanned PDFs without text remain failed drafts and require replacement or manual text.

AI uses one server-only OpenAI-compatible adapter. Configure `OPORA_AI_BASE_URL` (API base, such as an endpoint ending in `/v1`, without `/chat/completions`), `OPORA_AI_API_KEY`, `OPORA_AI_MODEL`, and optionally `OPORA_AI_ENABLED=true`. No key is returned through APIs. `ai.manage` can change persisted token/request/concurrency/time limits; provider credentials stay in the environment. No provider is configured by default. Local search, manual source authoring and coordinator answers work while AI is unavailable.

The gateway validates registered Pydantic JSON outputs, records model and prompt versions, bounds responses, reserves daily budgets and uses a circuit breaker. A durable `calling` marker is committed before outbound IO. After a crash or lost lease, a possibly billed call becomes `unknown` and is conservatively charged, without automatic repetition. Provider calls never receive participant records, contacts or private notes from repositories. Mentor and Builder use only selected currently published fragments. New Builder text stays a draft until explicit apply, review and publication.

P16 registers source-controlled task contracts and an idempotent `on_complete(db, run, context)` callback; final application must check its own frozen version and owner. P13 profile production returns only a reviewable suggestion payload for `about`, `skills` and `interests`; actual accept/reject/revert integration is a separate P20 gate.

Tests require `OPORA_KNOWLEDGE_TEST_DATABASE_URL` ending in `/opora_knowledge_test`. All provider tests use `httpx.MockTransport`; no external AI requests or real personal datasets are used. Actual provider/model compatibility, limits and answer quality remain a separate configured-provider acceptance gate.
