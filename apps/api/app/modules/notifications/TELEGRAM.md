# Telegram identity proof

Mount `app.modules.notifications.telegram_router.router`. It implements proof binding only: no outbound Bot API calls, messages, Telegram delivery state or automatic notification/news consent.

- GET `/api/v1/me/notification-channels/telegram` returns current verified user's status without chat/Telegram IDs or raw tokens.
- POST `.../link-tokens` takes `{}` and an Idempotency-Key. It binds a 10-minute `bind_` bearer to the exact user/session/purpose, invalidates previous pending tokens and returns a `t.me` start URL. Receipt stores only token UUID; transient bearer is encrypted and is cleared after consumption/revocation. Retry responses normalize expiry to UTC.
- POST `.../disconnect` takes `expected_version` (0 for pending-only cancellation) and a key. It revokes the active binding and all outstanding tokens without changing channel preferences or consents.
- POST `/api/v1/integrations/telegram/webhook` verifies the constant-time secret header before bounded 8KiB parsing. Only a private, non-bot sender whose chat ID equals sender ID can consume the exact purpose token. Current user/account, verified email, original session, expiry, revocation and one-use state are rechecked under canonical authorization/token locks. A second user cannot take an occupied Telegram identity. Replay/expired/unrelated updates return terminal ignored, without creating messages.

The optional module-local configuration is disabled by default: `OPORA_TELEGRAM_LINK_ENABLED`, `OPORA_TELEGRAM_BOT_USERNAME`, `OPORA_TELEGRAM_WEBHOOK_SECRET` (32–256 allowed secret characters). No real credentials or webhook registration were configured during implementation. Binding remains explicitly unavailable until an operator configures the bot/webhook. Even then `delivery_available=false`: binding alone does not enable a delivery adapter.

Models are in `telegram_models.py`; A1 owns combined migration20 and its session/user/foundation scope trigger. The canonical notifications model loader imports the two tables. CI needs guarded `OPORA_TELEGRAM_TEST_DATABASE_URL` ending `/opora_telegram_test`.

Validation: 11 actual PostgreSQL/local HTTP cases cover disabled/anonymous, stable encrypted receipt replay, one-use/concurrent callback, expiry/other-purpose token, revoked session/disabled user/removed email/session-owner change, occupied identity, stale version/disconnect/pending cancellation, wrong webhook secret/private-chat/sender/body, and cross-user/session receipt isolation. These fixtures send no external request or message.

Design sources: the shared OD token pattern (`backend/db/email_verification_tokens.py`: hash + encrypted transient bearer + atomic consume) is adapted to Opora cookie-session ownership and row/advisory locks; no school roles, JWT or course data were copied. Telegram's documented [bot deep links](https://core.telegram.org/bots/features#deep-linking) permit a base64url payload up to64 characters, and [setWebhook](https://core.telegram.org/bots/api#setwebhook) supplies the `X-Telegram-Bot-Api-Secret-Token` callback header. The generated payload is48 allowed characters.

## Bot sessions (server-to-server)

`app.modules.notifications.telegram_bot.router` lets the @-bot act for a volunteer who completed the proof above. The bot process holds `OPORA_TELEGRAM_BOT_API_SECRET` (32–256 allowed characters; the API only, never the web app or git) and sends it as `Authorization: Bearer …` on every call.

- POST `/api/v1/integrations/telegram/bot/sessions` `{"telegram_user_id": …}` returns `user_id`, `display_name`, a `session_token` and `expires_at` (12 h) for the active binding of that Telegram user, or 404 `telegram_not_linked`. A new session revokes the previous bot session of that user.
- The token is an ordinary `sessions` row with `channel='telegram_bot'`. The bot sends it as the `opora_session` cookie and calls the same `/api/v1` routes as the web app (`/me/schedule`, `/assignments/{id}/confirm`, …). For this channel `get_session_row` additionally requires the service secret (a leaked token alone is rejected), browser Origin/CSRF checks are skipped, and `resolve_principal` never grants staff permissions, even for a coordinator or with demo codes. A CHECK constraint keeps such sessions user-owned and without MFA.
- Disconnecting Telegram in the profile revokes the binding and every bot session of that user. Disabled accounts are rejected by the usual principal resolution.

Validation: `tests/test_telegram_bot_sessions.py` covers missing/wrong/unconfigured secret, unknown and revoked bindings, acting without Origin/CSRF, revocation on disconnect, rotation, a stolen token without the secret (including `/auth/session`) and a staff member's bot session without grants.
