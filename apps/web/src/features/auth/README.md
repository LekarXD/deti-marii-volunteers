# Sign-in UI

`LoginPage` is a public-layout route for `/login?next=/fund/...`. It uses the shared
cookie/CSRF transport and generated `AuthSessionView`, `ChallengeView` and
`MfaSessionView` schemas, with no independent auth store.

`WelcomePage` holds the password form next to the fund's drawing and a short invitation
to the volunteer questionnaire. It is the anonymous entry page `/` and also the password
stage of `/login` (with `next` kept for the return and "Забыли пароль?"); the MFA, link,
legacy-email and already-signed-in stages of `/login` stay compact cards. The public
header is hidden whenever the welcome screen is on the page, because the logo sits in
the sign-in card. A rejected password
(`invalid_credentials`) is shown as one line under the password field and marks both
fields invalid; it clears on the next edit. Other auth failures render the server
message as one line (`FormError`), never the page-level `ErrorState`.

The email command queues a challenge. The UI distinguishes `dev_inbox` from `pending`
and never claims provider delivery. Test-inbox proof is obtained through an operator
CLI outside the product. Link parameters `challenge_id` and `token` populate only an
in-memory pending confirmation: GET does not consume the link. The token is removed
from the address with replacement navigation and never logged or written to storage.
Verification requires the explicit confirmation button.

After verification, `useSession().refresh()` loads the rotated cookie session. The form
remounts for its current principal/MFA state and uses `mfa_required` to choose the next
step. Email possession alone does not grant staff access. Existing authenticator codes
and existing recovery codes both use `/auth/mfa/verify`. This screen does not enroll or
reset a factor. When a factor is unavailable, the page directs the user to the fund
administrator. Logout uses the shared session service.

Return navigation accepts only an application-relative path. External URLs, protocol-
relative paths, backslashes, encoded delimiters, control characters and auth/API loops
are rejected. The default destination is `/fund` for staff or a pending staff MFA step,
otherwise `/application`. Server permissions remain authoritative for every destination.

## Verification

Focused UI tests cover link GET non-consumption/token concealment, principal-changing
refresh into MFA, return navigation after MFA, an existing recovery code, queued test
mail feedback and logout back to the email stage. The transition tests mock only the
transport/session boundary; the product has no mock fallback.

An additional Chrome journey used genuine P01 APIs and an isolated PostgreSQL16 database
with invented staff fixtures: email challenge -> queued dev inbox -> operator fixture CLI
outside the UI -> token verification -> actual cookie/principal rotation -> automatic MFA
stage -> existing authenticator code -> `/fund/groups`. No JS errors occurred. Desktop
1440px and mobile 390px screenshots were inspected; there was no horizontal overflow.
Temporary evidence: `/private/tmp/opora-auth-email-desktop.png`,
`/private/tmp/opora-auth-email-mobile.png`, `/private/tmp/opora-auth-queued-desktop.png`,
`/private/tmp/opora-auth-mfa-desktop.png`. Real external email delivery and MFA enrollment
are outside this UI acceptance boundary.
