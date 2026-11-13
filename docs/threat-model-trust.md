# Threat model: password reset and data export (phase 4, Trust)

Review session, 13 November 2026, against main b98d351. Nothing here is built yet; it is what the
design must answer before the code. "Must" = a blocker at the pre-promotion read; "should" = a finding.

What we protect: the account (taking it over gives every row of it) and the data in it, which is
health data under GDPR Art. 9 (intake against a goal, body weight from phase 3).

What exists today: HS256 access tokens for 30 minutes, with `sub` and `pwc` (password stamp), no
`typ`/`aud` claim; Argon2 with bounded slots; Nginx limits login, signup, password change and account
deletion per IP (5/min, burst 5); headers nosniff, DENY, strict-origin-when-cross-origin; no CSP;
the token lives in localStorage; signup answers 409 "Email already registered".

## Password reset

Flow: `POST /auth/password-reset {email}` → a link by e-mail (log-only backend until phase 7, decision
on 11 Nov) → `POST /auth/password-reset/confirm {token, new_password}`.

| # | Threat | Control | Level |
|---|--------|---------|-------|
| R1 | A reset token used as an access token. `decode_token` checks only the signature, `exp` and `sub`, so a JWT reset token signed with the same key would open the API | Access tokens get `typ: "access"`, and `decode_token` refuses any other `typ` (a token without `typ` still counts as access, for the tokens already issued). Or the reset token is not a JWT at all (see R2). A test: the reset token on `GET /auth/me` → 401 | must |
| R2 | A replayed or leaked token | Either (a) random 32 bytes (`secrets.token_urlsafe`), only its SHA-256 stored (`password_reset_tokens`: user_id FK CASCADE, token_hash unique, expires_at, used_at), single use, a new request invalidates the old ones; or (b) a JWT with `typ: "reset"`, `exp` 30 min and the current `pwc`: the reset changes `password_changed_at`, so the token dies on use and after any password change, with no table. (b) is simpler and needs no migration | must (one of the two) |
| R3 | Finding out whether an email has an account | The request answers 202 with the same body whether the email exists or not, and does the same work (the log-only backend is cheap, so timing does not give it away). Signup already reveals existence (409): write that down as an accepted risk, or change it at e-mail verification | must for reset, should for signup |
| R4 | Brute force on the confirm step / flooding a victim with e-mails | Both paths go into Nginx's `auth` zone (the map and the location). Per account: at most 3 requests an hour (in the database, not in memory: 2 pods). Confirm runs Argon2, inside the slots | must |
| R5 | The token in logs and in Referer | The link carries the token in the fragment (`/reset#token=...`), not in the query: Nginx does not log it and the browser does not send it. The frontend reads it and POSTs it. Never log the token, except the log-only backend, which logs only the link | must |
| R6 | A forged link through the Host header | The link is built from a setting (`PUBLIC_BASE_URL`), never from `Host` / `X-Forwarded-Host` | must |
| R7 | Sessions still open after the reset | The confirm sets `password_changed_at`, which signs out every token, as change password does today. It returns a fresh token or sends the user to login | must |
| R8 | The log-only backend on prod with real users. Whoever can read the pod's logs (kubectl, a future Loki) takes any account over | A `PASSWORD_RESET_ENABLED` flag, off by default and in the prod overlay, as with body weight; it comes on in prod only together with the real provider (phase 7). The app fails at startup if the backend is log-only and an `ENVIRONMENT=prod` setting is present | must |
| R9 | Someone takes an email that is not theirs (signup with no verification) | A successful reset proves the mailbox: mark the email verified then (when the verification exists), and the reset signs out whoever had taken the account | should |
| R10 | The tokens left over after account deletion | FK ON DELETE CASCADE (variant a) or nothing (b); the delete-account test (every user table empty) covers it on its own if the table exists | must (a) |

## Data export (Art. 15 and 20)

Flow: `POST /auth/me/export {password}` → a JSON file, downloaded, with nothing kept on the server.

| # | Threat | Control | Level |
|---|--------|---------|-------|
| E1 | Another user's data in the export, or a table left out | Every query filtered by user_id from the token. A test mirrored on the deletion one: it fills every user table (`user_tables()`), and each must appear in the export, so a future table that is not exported fails the test | must |
| E2 | A stolen session takes everything at once | Current password asked, as for deletion; the path in Nginx's `auth` zone (Argon2, 5/min) | must |
| E3 | Secrets in the export | Never `password_hash`, tokens, `pwc`; a test on the key list per object | must |
| E4 | Export files left behind (disk, S3, cache) | Generated on the fly, `StreamingResponse`, `Content-Disposition: attachment`, `Cache-Control: no-store`; no file written anywhere | must |
| E5 | The token in a download URL | The frontend downloads with fetch (Authorization header) + a Blob, never `?token=` | must |
| E6 | Memory and time on big accounts (256Mi pod) | Stream per table with `yield_per`; a test with a big account under a memory bound; a timeout under Nginx's | should |
| E7 | CSV formula injection (`=HYPERLINK(...)` in a food name) | JSON only; if CSV comes later, prefix cells that start with `= + - @` with `'` | should |
| E8 | The export in logs or metrics | Nothing from the body in logs; the route stays a template in metrics | must |
| E9 | Body weight while the flag is off | The export includes `body_weights` / `tdee_estimates` regardless of the flag: it is the user's data if it exists (with the flag off in prod, they are empty) | should |

## Across both

- **CSP (should, before real users):** the token in localStorage is readable by any script that gets
  into the page. With the fonts now bundled (design A), a strict CSP is possible: `default-src 'self';
  script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'`.
  Set at server level in nginx.conf.template (an `add_header` in a location drops the others), with a
  check in `check-rate-limit.sh` that the header is there.
- **HSTS and TLS** come with go-live (phase 7); without TLS the reset link travels in clear.
- **Restore after deletion:** the policy of 12 Nov (a deletion log with id + created_at) applies to the
  reset tokens too, if they are rows (variant a): a restore must not bring back valid tokens. Variant
  (b) has no such problem, another reason to prefer it.

## Verdict on the design

Variant (b) for the reset token (a JWT with `typ` + `pwc`, no table, no migration), together with R1
(`typ` on access tokens) and the flag of R8, closes the most risk with the least code. The export can
be built independently; E1 and E2 are the ones I will check line by line.
