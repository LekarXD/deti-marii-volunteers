# Shared Opora stage — P18A

One provider-free TypeScript composition/geometry implementation for live host preview, solo preview and the future hidden recorder. Source commit `38c92cd49b1b6c229ed473de991479ed261e4052`, provenance/hashes in `reuse-source.json`; independent pinned-source golden outputs in `geometry-reference.json`. Reuses screen→board→slides priority and pure side/overlay fit, camera-size and pip calculations. School arch/themes, Zoom flags, audience grids, chat and school API code are excluded.

## Immutable wire contracts

- `scene.schema.json`, `capture-plan.schema.json` are canonical version-1 serialization schemas (JSON Schema 2020-12). P18B/P18C backend validates these exact files, then performs authorization and database binding checks. No independent competing field lists.
- `parseStudioScene`, `parseCapturePlan` validate JSON strictly, reject extra fields, validate semantic refs, copy and deep freeze. `serializeStudioScene`, `deserializeStudioScene`, `serializeCapturePlan` roundtrip with stable key order.
- Required nullable keys stay explicit null. A prepared live/solo scene may have take_id:null before take creation; an actual CapturePlan requires a nonnull take UUID. Capture readiness stays blocked until the server binds a real take and the matching scene revision. All entity refs are UUIDs. Scene stores immutable asset id/checksum/dimensions and exact deck-version/page or board-snapshot refs; never provider URLs, auth tokens, chat, private notes or audience DTOs.
- Schema version 1 and render profile `opora-stage/1` are immutable contracts. Changing meaning/geometry needs a new profile; old event journals remain replayable with the old profile. Server authority owns revision/CAS, IDs, presenter identity, take/generation and approved source refs. Data-channel hints never authorize changes.
- `canonicalSerialize` uses sorted object keys and ECMAScript JSON number/string serialization, UTF-8 and no whitespace. A backend hashing the same scene must use equivalent canonical JSON (for example RFC 8785), not ordinary Python JSON defaults. Scene serialization does not itself sign or authenticate JSON.
- The virtual profile is 1920×1080, margin 24. This defines geometry only; codecs, FPS, A/V budgets and media duration guarantees await P18C media spike. Browser widths scale this same frame uniformly. Mobile controls/view zoom must never rewrite the stored/captured composition. No second mobile recording engine.

## Privacy boundary

`CapturePlan` pins foundation/resource/session/take, generation, exact scene revision/profile and recording policy. Its strict allowlist names each identity + track ID + source + video/audio kind + required status. Signature verification happens on the server/ticket boundary; the frontend parser is not an authorization check. Recorder room grant must be hidden, subscribe-only, autoSubscribe=false, without private data/chat channels. Only allowlisted tracks are explicitly subscribed. `ObservedTrack` means actual subscribed/captured inventory, not every advertised room participant.

`captureReadiness(scene,plan,observed)` fails closed for scope/revision mismatch, unapproved policy, unknown/blocked track privacy, extra/duplicate tracks, missing required tracks or missing visible presenter/screen. `sceneTracks` returns no render/audio inputs on failure. Never publish/fall back to a raw source after privacy failure. Approved participant audio is possible only as an explicit policy-bound audio tuple; there is no audience video grid or chat projection in the shared scene.

Backend additionally binds asset hashes/dimensions to immutable processed private assets, verifies current grants/revocation and signatures, and ensures the adapter reports actual subscriptions/audio routing. Client metadata cannot prove final-file privacy. P18C must inspect the resulting media file and report real clocks/completeness before preview_ready. P18A performs no room join, capture, external delivery, media upload, recording or publication.

## React surface

`apps/web/src/ui/studio/StudioStage.tsx` exports `StudioStage`, `StudioStageProps`, `StageTrackBinding`, `ResolvedStageAsset`. Scene and approved asset URL projection stay separate; URLs never enter serialized manifests.

`StageTrackBinding` adds `media_revision` and `attach(HTMLMediaElement)=>cleanup` to observed metadata. Increment media_revision whenever reconnect/replacement changes the actual stream; onPlaying readiness is fenced to this revision. Preview mutes its own elements; render routes only explicitly approved audio tracks. A preview/live stage may omit CapturePlan and show approved presenter-only visual slots, with no Stage audio. Callback `onReadiness` then reports `visual_ready` independently and `ready:false/capture_plan_required`. Render mode without plan is blocked. With a capture plan, readiness requires privacy, exact asset metadata, loaded image dimensions, self-hosted Inter font readiness and actual media onPlaying; mounting a component is not readiness.

Both live and solo fixtures use the same `StudioStage`. `StudioPreviewFixture` is provider-free, camera-off, fictional SVG slide/person data. Storybook `Опора/Студия` shows shared composition, camera-off and unknown-privacy block. No audience controls are in the recorded canvas.

Root integration owns workspace manifests/aliases and lazy route wiring. This package needs no new runtime dependencies. Tests live in `apps/web/src/ui/studio/core.test.ts` and run under the existing web Vitest suite. Browser visual acceptance is a separate gate; no media output/capture claim is implied by green geometry tests.

`BoardStageBinding` lets A4 mount an approved read-only continuous Yjs surface in the same canonical content rect for preview/live. Its snapshot_id and scene_revision must match, read_only=true and privacy approved. It carries surface_revision plus mount/cleanup; Excalidraw controls are hidden using the source renderer rules and drawing controls stay outside Stage. Dynamic board preview reports visual_ready separately and capture ready=false/live_board_capture_unavailable. Render mode rejects this live binding until the signed read-only recorder board adapter and complete source-clock/manifest contract are integrated; immutable authorized board snapshots remain supported.
