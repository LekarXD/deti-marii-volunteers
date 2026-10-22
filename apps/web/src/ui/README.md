# Shared Opora UI — P02

Import from `../../ui` in features. Original Inter, palette, rounded white surfaces, four-circle brand and SVG paths come from `prototype-src/helmet.html`, candidate header/CSS, extensions and `scripts/coordinator_layout.py` at reference `028a0c3`. No OD skin. UI runtime mechanics adapted from OD client principal pinning/retries and modal focus lifecycle at source `38c92cd49b1b6c229ed473de991479ed261e4052`; no axios/JWT/school dependencies. AppProviders imports tokens once.

## Layout and navigation

Root router alone wraps route trees in `<AppProviders><Outlet/></AppProviders>`, then `<CandidateLayout/>` or `<CoordinatorLayout/>`. Layouts render `Outlet` or optional children; **do not wrap feature pages again**. Navigation stays on top; desktop logo and menu share one row. At 1100px and below it becomes a compact custom section chooser. `app/navigation.ts` is the canonical route map.

`useSession()` from `app/layouts` returns `{session, refresh, logout}`. `refresh()` reboots server identity and clears private cache: call after successful login/challenge verification. `logout()` posts server logout, clears cache, broadcasts invalidation and boots a fresh limited session. Never persist tokens. Staff authorization remains server-side; navigation is not access control.

## Controls

```tsx
import {Button, Card, Field, Input, Textarea, Combobox, DatePicker,
  TimePicker, Segmented, Dialog, Drawer, useToast, EmptyState,
  LoadingState, ErrorState, JobState} from '../../ui';

<Card tone="paper">
  <Field label="Имя" hint="Как к вам обращаться" error={errors.name}>
    <Input value={name} onChange={e => setName(e.target.value)} autoComplete="given-name" />
  </Field>
  <Combobox label="Направление" value={direction} onChange={setDirection}
    options={[{value:'art',label:'Творческие мастерские'}]} />
  <DatePicker label="Дата встречи" value={day} onChange={setDay} min="2026-01-01" />
  <TimePicker label="Начало" value={time} onChange={setTime} min="09:00" max="20:00" />
  <Button loading={saving} type="submit">Сохранить</Button>
</Card>
```

- Button accepts native button props, `variant=primary|accent|secondary|ghost|subtle|danger`, `size=sm|md|lg`, `loading`. Defaults to type=button, use type=submit explicitly.
- Card accepts native div props and `tone=paper|soft|hero|dark`. Default paper.
- Field `{label,htmlFor?,hint?,error?,children,className?}` automatically associates Input/Textarea children through context. Provide explicit id/htmlFor if using custom children. Only one control per Field.
- Input/Textarea forward refs and native attributes. **Never use native select or type=date/time/datetime-local.** Use custom controls below.
- Combobox `{label:string,value:string,onChange(value),options: {value,label,disabled?}[],placeholder?,disabled?,id?,error?,className?}` includes its own label; do not add Field except when sharing hint/error. Arrow, Home/End, typeahead, Enter, Escape and Tab supported; focus stays on trigger via aria-activedescendant.
- DatePicker/TimePicker `{label,value,onChange,min?,max?,disabled?,id?,error?,className?}` include labels. ISO `YYYY-MM-DD` dates and `HH:mm` wall-clock values. Custom month/year navigation permits arbitrary years, no rolling six-week product limit. Calendar supports arrows, Home/End, PageUp/Down. TimePicker selects hours/minutes separately. Server interprets timezone and validates availability.
- Segmented `{label,value,onChange,options,className?}` uses radiogroup with arrow/Home/End keyboard navigation; long labels wrap. It chooses a view/filter, not a navigation route.
- Dialog/Drawer `{open,onClose,title,children,footer?,description?,initialFocusRef?,className?}` portal into body. Topmost-only Escape, nested scroll locks, initial/trapped/returned focus. Keep open on failed save. Close callbacks must not perform destructive commands.
- `useToast().toast(message,tone?)`, tone=info|success|error. Only toast success after a successful server command. Provider owned centrally.
- EmptyState `{title,description?,action?,icon?}`; LoadingState `{label?}`; ErrorState `{error:unknown,retry?:()=>void}`; Skeleton `{className?}`; JobState `{status:queued|processing|ready|failed|unavailable,label?,onRetry?}`. Aliases Loading/Empty/ErrorAlert available.
- UploadControl `{label,accept?,onFile,disabled?,progress?,status?,error?}` shows drag/drop, file selection, progress and server job states. Feature hooks own intent/offset/finalize via the sole transport. Ready must come from the server, never from file selection.
- `Icon` uses original SVG kit paths; `Brand` uses original four circles.

Utility classes preserved from the actual prototype: h1/h2/h3/display/lead/meta/p, head/section/section-head, row/stack/wrap/grow, grid-2/3/4, tag/t-yellow/t-blue/t-green, avatar, bar, chips, art, actions, btn-block. Feature CSS stays in the feature owner directory. Use min-width:0 for grid/flex children, flexible widths, and wrap long Russian labels.

## Server state, transport, and errors

```tsx
import {useQuery, useMutation, useQueryClient} from '@tanstack/react-query';
import {api, ApiError} from '../../api/transport';
import {keys} from '../../api/keys';
// DTO types from generated/schema.ts; root generates after API integration.
const query = useQuery({queryKey:keys.self('application'),
  queryFn:({signal}) => api<ApplicationView>('/me/application', {signal})});
const mutation = useMutation({mutationFn:(command:Command) =>
  api<Result>('/interviews', {method:'POST', body:command,
    idempotencyKey:crypto.randomUUID()})});
```

`api<T>` uniformly prefixes `/api/v1`, sends same-origin cookie and server-issued CSRF for unsafe methods, JSON encodes objects (FormData/Blob/ArrayBuffer/typed arrays remain raw; caller Content-Type is preserved); `responseType` can be json (default), blob or text, supports `signal`, `timeoutMs`, `idempotencyKey`, `retries`. Unsafe commands default retries=0; explicit retries require server receipt + idempotencyKey. Keep the same key for a logical resend after uncertain outcome; generate a new key for a new action. GET retries at most once by default, <=2 by explicit option. Never retry 401/403/409/422/429. Retries and completion are fenced to session generation/principal. Timeout/network/5xx do not log out. A session-level 401 (`session_expired`, `session_invalid`, `session_required`) clears private caches; other 401s (for example `studio_login_required`) only reject. Cross-tab session change aborts active requests and clears cache.

`ApiError` has `status` (alias statusCode), `code`, `message`, `field_errors` (alias fieldErrors), `current_version`, `retryable`, `request_id`. Display field_errors at corresponding fields; 409 requires refetch/review, not silent overwrite. Abort/principal change must not trigger a success toast.

One exported QueryClient in `api/queryClient.ts`, centrally provided; do not create clients or another fetch wrapper. `keys` (alias queryKeys) has `all(domain)`, `list(domain,filters={})`, `detail(domain,id)`, `self(domain)` and `session()`. Private keys include foundation/principal. Slot/capacity queries use staleTime:0 and refetch immediately before commands; server locks decide capacity. Query retries=false; sole transport owns bounded retries.

## Verification

`pnpm --filter @opora/web typecheck` and `pnpm --filter @opora/web test`. Per-file jsdom tests exercise custom controls, nested modal focus and unsafe command/principal boundaries. Root visual QA must compare matching reference and final states at 390/768/1050/1440 and 200% zoom. Screen capture is a separate browser acceptance step, not claimed by unit tests. Storybook lives in `apps/web/.storybook` and `Foundations.stories.tsx`: forms, buttons, nested focus, uploads, API states, and both header roles. `pnpm --filter @opora/web storybook` opens it; `build-storybook` emits the static review bundle. Exact 8.6.19 dependencies/scripts are integrated by A0. `FoundationPreview` also serves an optional `/ui` inspection route.
