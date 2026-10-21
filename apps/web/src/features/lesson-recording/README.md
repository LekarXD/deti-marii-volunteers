# Solo lesson recording — P18D

Exports `RecordingProjectsPage` and `RecordingProjectPage`; root owns routes and the
coordinator layout. Expected routes are `/fund/recordings` and `/fund/recordings/:id`.
The feature imports the existing author-track/lesson picker and the resource-neutral
Studio API, `useLiveKit`, `useStageAsset`, slide uploader and canonical StudioStage.
No separate room client, geometry, scene DTO or capture implementation exists here.

The teacher console follows `prototype/Studio.dc.html`: pill title bar, 20px stage /
380px tool-column gap, source cards, warm palette, original SVGs and Inter. Controls
stay outside the 16:9 recorded composition, which scales intact on small screens.
Body/control/meta text remains at least 15px. There is no audience/chat composite.

This checkpoint supports actual project creation with an optional existing lesson,
settings edits, versioned prepare command, studio connection, explicit camera/mic /
screen controls, explicit device picker, slides processing/selection, and real take
create/start/stop/discard commands. No device is requested on mount. Media errors
use human retry text; project/identity unmount and host revocation disconnect media.

All reads/commands use the sole ordinary API and principal-scoped keys. Commands
preserve their Idempotency-Key after uncertain outcomes, use current expected
versions, and disable unsafe automatic retries. Lists expose cursor pagination.
Server capability flags gate capture; a `capturing` state is not presented as a
confirmed recording until `started_at` exists. There is no fake running timer,
progress percentage, raw fallback, preview URL or success receipt.

Render discovery uses the actual project render page. Ready/degraded files open only
on an explicit private-preview action through the existing authorized asset content
endpoint; video never autoplays. Review requires permission and a manual image/audio
check, then sends the exact version and render hash. An approved result links directly
to its actual target lesson with `recording_render_id`; A7's Builder revalidates the
result and explicitly imports it into the existing draft before review/publication.
No recording-page action publishes a lesson automatically.

Pending authoritative take-policy readback from A1: scoped approval from actual host
tracks must be added before the full start journey is accepted. Capture capability is
read from the server; UI shows its actual unavailable reason while retaining preparation.
Scene/slides can change during capturing, while device publication changes require the
current take to finish. A7 owns the separate publish/withdraw adapter.

Tests use actual generated DTO fixtures and sole-transport mocks. They verify real
lesson selection/versions, unavailable capture, zero automatic device/start calls,
explicit denied-camera recovery, versioned discard and stored-interval semantics.
Screenshots and actual browser media acceptance remain separate integration gates.
