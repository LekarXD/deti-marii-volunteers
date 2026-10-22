# Solo lesson recording — P18D

Exports `RecordingProjectPage`, `CreateRecordingDialog` and `AttachLessonDialog`; root owns
routes and the coordinator layout. `/fund/recordings` is the «Эфиры и записи» page
(`features/broadcasts`) filtered to lesson videos; `/fund/recordings/:id` is the project page.
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
The duration limit comes from the current take or project capabilities, including
the server's reason. `duration_limit` distinguishes automatic stopping from an
actually captured result; the UI never simulates completion or sends a local
deadline-based stop command. Finished takes retain the same private review path.

Render discovery uses the actual project render page. Ready/degraded files open only
on an explicit private-preview action through the existing authorized asset content
endpoint; video never autoplays. Review requires permission and a manual image/audio
check, then sends the exact version and render hash. An approved result links directly
to its actual target lesson with `recording_render_id`; A7's Builder revalidates the
result and explicitly imports it into the existing draft before review/publication.
No recording-page action publishes a lesson automatically.

Take approval uses the generated policy command and authoritative take readback.
The teacher explicitly agrees to the current published source inventory; the command
binds both the take version and scene revision. Changed sources clear local consent,
and Start requires the server-approved exact inventory plus active own narration.
Optional muted sources remain listed without becoming required. Approval can be
withdrawn explicitly during capture; the server owns stopping and revocation.
Capture capability is read from the server while preparation remains available.
Scene/slides can change during capturing, while device publication changes require the
current take to finish. A7 owns the separate publish/withdraw adapter.

Tests use actual generated DTO fixtures and sole-transport mocks. They verify real
lesson selection/versions, unavailable capture, zero automatic device/start calls,
explicit denied-camera recovery, versioned discard, scoped source approval/withdrawal,
stale-consent rejection and stored-interval semantics.
Screenshots and actual browser media acceptance remain separate integration gates.

Live host recording reuses the connected `LiveRoomPage` controller and stage.
`LiveRecordingControls` makes no request for viewers and binds a recording project
only after the host's explicit action. Take approval/start/stop use the same API and
own-source checks as solo recording; guests and chat are excluded. Active capture
locks local publication changes and room exit/close controls. Live project detail
is a review surface with a link back to the existing room, never another RTC client.
The private renderer pins resource kind/id separately from the recording project;
solo still requires project and resource IDs to coincide.
