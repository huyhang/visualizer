# Security

This document records the security measures **implemented** in `akasha`
and the hardening **still required** before running it as a non-local (shared,
internet- or LAN-reachable) service. The running code is the source of truth; if
this doc and the code disagree, trust the code and fix the doc.

## Threat model & assumptions

- Multi-user service holding documents with per-user access control; some users
  are untrusted relative to each other.
- The current default deployment (`docker/docker-compose.nas.yml`) is aimed at a
  **single-host, localhost or LAN** setup, optionally behind a reverse proxy.
- MongoDB is **never** published to the host — it is reachable only on the Docker
  network. Several defenses below assume that stays true.
- Not in scope of the current code: TLS termination, rate limiting, WAF, secrets
  management, and OS/container hardening (see "Required hardening").

---

## Implemented measures

### Authentication

- **Session-based auth (Flask-Login).** Every document, browse, version and
  admin endpoint is `@login_required`. Unauthenticated requests get `401` (API)
  or a redirect to `/login` (browser). See `auth.py`, `app.py`.
- **Password hashing.** Passwords are stored only as `werkzeug.security`
  hashes (PBKDF2); plaintext is never persisted. Verified with
  `check_password_hash` on login.
- **Login user-enumeration resistance.**
  - *Timing:* a pre-computed dummy hash (`_DUMMY_PASSWORD_HASH` in `auth.py`) is
    compared even when the username is unknown, so a missing account is not
    measurably faster than a wrong password.
  - *Response:* a single, indistinguishable "Invalid username or password" for
    unknown user, wrong password, **and** deactivated account — so the response
    never reveals which case occurred (including that a disabled account's
    password was correct).
- **No default/bootstrap admin.** The first account ever registered becomes the
  admin; there are no built-in credentials to guess.
- **Deactivated accounts are logged out.** The Flask-Login `user_loader` returns
  `None` for inactive accounts, so disabling an account takes effect on its next
  request.
- **Invite-only registration (optional).** An admin can switch registration
  between *open* and *invite-only* (`_auth.settings`, `auth_store.py`). In
  invite-only mode `/register` is refused (`403`) and accounts exist only when an
  admin creates them — except the very first account, which is always allowed so a
  fresh deployment can bootstrap its admin (`registration_allowed`, pure/tested).
- **Password strength policy (NIST SP 800-63B).** Chosen passwords must be 12–128
  characters, are screened against a common-password blocklist, and may not equal
  the username (`passwords.py`, pure/tested). No composition or rotation rules
  (per NIST). Enforced on registration, admin-set/reset, and self-change. A
  breached-password (HIBP) check is intentionally not included (network
  dependency); see hardening below.
- **Forced first-login password change.** Admin-provisioned accounts carry a
  `must_change_password` flag; an admin may leave the password blank to have a
  strong **temporary** password generated and shown once (`generate_temp_password`,
  `secrets`-backed). A `before_request` guard blocks such a user from the rest of
  the app until they set a new password at `/change-password` (browser is
  redirected; API gets `403`).

### Authorization (access control)

- **Server-side enforcement on every endpoint** via `_authorize` /
  `authz.is_allowed`. The browser UI hides actions you can't take, but the
  server is the enforcement point — a crafted request still gets `403`.
- **Fine-grained, allow-only grants** scoped at database / collection / article,
  with `read`/`write`/`delete` permissions and **most-specific-wins** resolution.
  There are no deny rules; anything not granted is denied. Pure, unit-tested
  logic in `authz.py`.
- **Filtered, not just gated, reads.** Search, browse and suggest results omit
  anything the caller can't `read` (`_filter_readable`, `browsing.py`), so they
  don't disclose the existence of unreadable articles/collections/databases.
- **Least-privilege availability guard.** The last remaining admin cannot be
  demoted, disabled, or deleted.
- **Admins are not exempt from grants.** The admin role governs account and
  access *management* (the `/admin` console, gated by `admin_required`), not
  content access. Document and book endpoints authorize every caller — admins
  included — against their grants, so an admin reads another user's content only
  where explicitly granted. (`_authorize`/`_can_read` in both services no longer
  short-circuit on the admin role.)

### Tenant / internal-state isolation

- **Reserved namespaces are unaddressable.** Any `_`-prefixed database (e.g. the
  `_auth` store holding users and grants) is rejected by `_reject_reserved` on
  every document route and hidden from `list_databases`, so the credentials/grants
  store cannot be read or written through the document API.
- **Internal fields cannot be injected or read.** `_`-prefixed keys (`_id`,
  `_rev`, `_history`, `_deleted`) are stripped from incoming bodies (`_sanitize`)
  and from public representations (`_body`). Clients therefore cannot forge a
  revision/history or exfiltrate history via the search text haystack.
- **Optimistic concurrency (integrity).** Conditional `find_one_and_replace` on
  `_rev` prevents silent lost updates between concurrent writers (stale write →
  `409`). Version history records author + timestamp, giving an audit trail.

### Input handling & injection resistance

- **Strict document validation.** Documents must be flat objects of scalars or
  flat arrays of scalars (`validation.py`); nested structures are rejected,
  shrinking the injection/abuse surface.
- **Parameterised MongoDB queries.** All queries use pymongo dict/BSON
  construction, never string concatenation, so classic query-string injection
  does not apply.
- **Email and search-term validation** (`validation.py`).
- **Open-redirect protection.** The post-login `next` redirect only accepts
  same-app relative paths (`target.startswith("/")` in `auth.py`).

### Output handling (XSS)

- **Wikitext is sanitized by construction.** The renderer HTML-escapes all
  user content *first*, then emits only a known, safe subset of tags plus our own
  link anchors (`static/js/wikitext.js`); nothing else reaches the DOM.
- **DOM built without `innerHTML` for untrusted data.** UI helpers use
  `textContent`/`createElement` (`static/js/dom.js`); the one `innerHTML` path is
  the already-escaped wikitext output.
- **Jinja auto-escaping** on the server-rendered `login`/`register`/`admin`
  pages.

### Sessions, cookies & secrets

- **Signed session cookies.** A `SECRET_KEY` is **required** — `create_app` and
  `config.get_secret_key` refuse to start without it (no insecure fallback), and
  compose enforces it via `${SECRET_KEY:?…}`.
- **Cookie flags.** `HttpOnly` (JS can't read the cookie), `SameSite=Lax`
  (blocks cross-site `POST`/`PUT`/`DELETE` — the primary CSRF defense for the
  JSON API), and `Secure` configurable via `SESSION_COOKIE_SECURE`.
- **CSRF tokens** protect the server-rendered forms (login/register/admin) via
  Flask-WTF `CSRFProtect`.

### Rate limiting

- **Per-IP limits on the auth endpoints.** `/login`, `/register` and
  `/change-password` are rate-limited (Flask-Limiter, 5/minute and 30/hour per
  client IP) to blunt brute-forcing, credential stuffing and abuse. The limiter
  is injected into the app factory (`build_limiter`), so tests can disable it and
  a deployment can choose its storage backend. The default is in-memory
  (`memory://`), which suits a single process; set `RATELIMIT_STORAGE_URI` to a
  shared backend (e.g. Redis) so limits hold across multiple gunicorn workers.
  Behind a reverse proxy, configure `ProxyFix` so the real client IP is used (see
  hardening below).

### Network / data exposure

- **MongoDB has no published port** — only the app container can reach it.
- **Soft deletes** keep an auditable tombstone + history rather than destroying
  data.

---

## Required hardening for non-local deployment

Ordered roughly by priority. Items marked *(partial)* have some support already.

### Critical

1. **TLS / HTTPS everywhere.** Session cookies over plain HTTP can be
   intercepted. Terminate TLS at a reverse proxy, set
   `SESSION_COOKIE_SECURE=true`, add **HSTS**, and redirect HTTP→HTTPS.
   *(partial: the cookie flag and a Synology reverse-proxy guide exist; TLS
   itself is not provided by the app.)*
2. **Enable MongoDB authentication + network isolation.** Mongo currently runs
   with **no authentication** (it is only unexposed by network placement). Enable
   SCRAM auth with a least-privilege application user, keep it off the host
   network, and use TLS for the app↔Mongo connection. Without this, anything that
   reaches the Docker network has full DB access.
3. **Rate limiting & lockout on auth endpoints.** *(partial — done: per-IP rate
   limiting on `/login`, `/register`, `/change-password` via Flask-Limiter; see
   "Rate limiting" above.)* Still to do for a hardened deployment: configure a
   **shared storage backend** (`RATELIMIT_STORAGE_URI`, e.g. Redis) so limits hold
   across gunicorn workers, add **per-username** limits and **backoff/lockout** on
   repeated failures, and ensure the real client IP is trusted (item 5).
4. **Run the container as non-root.** `docker/Dockerfile.akasha` has no `USER`
   directive, so the app runs as root. Add a non-root user, and consider a
   read-only root filesystem, dropped Linux capabilities, and resource limits.
5. **Trust the proxy correctly.** Behind a reverse proxy, add Werkzeug
   `ProxyFix` so the real client IP and scheme are honoured (needed for accurate
   per-IP rate limiting and secure-cookie/redirect behaviour), and configure the
   proxy to strip inbound `X-Forwarded-*` from clients.

### High

6. **Security headers.** Add a **Content-Security-Policy** (the templates use an
   inline `<script>`/`<style>`, so use nonces or hashes), plus
   `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` /
   `frame-ancestors 'none'` (clickjacking), `Referrer-Policy`, and
   `Permissions-Policy`. Flask-Talisman can supply most of these.
7. **Request size limits.** Set `MAX_CONTENT_LENGTH` (none is configured) and
   bound field/array/string sizes to prevent memory-exhaustion via oversized
   documents. Listing is already capped (`limit` ≤ 500); keep pagination bounded.
8. **CSRF defense-in-depth for the JSON API.** The API currently relies solely on
   `SameSite=Lax`. Add token- or custom-header-based CSRF (double-submit, or a
   required `X-Requested-With`) so protection survives browser quirks or any
   future loosening of the cookie policy.
9. **Session lifecycle.** Configure `PERMANENT_SESSION_LIFETIME` (idle/absolute
   expiry), rotate the session identifier on login (session-fixation), and
   provide a way to revoke sessions (e.g. on password change / disable).
10. **Registration controls.** *(partial — done: an admin can switch to
    **invite-only**, disabling self-registration; see "Authentication" above.)*
    Still to consider for a shared deployment: admin approval, a CAPTCHA to stop
    bot signups, and **email verification** (emails are stored but not verified).
    Note that `/register` returns `409` on a taken username/email — an enumeration
    vector (unlike the uniform `/login`); prefer a generic response or an
    email-based flow.
11. **Secrets management.** `SECRET_KEY` lives in `docker/.env` on disk. Prefer
    Docker/orchestrator secrets or a vault, restrict file permissions, and plan
    for rotation (rotating invalidates existing sessions). `.env` is git-ignored —
    keep it that way.

### Medium

12. **Audit logging & monitoring.** Add structured security logs for auth events
    (success/failure), grant/role changes, and admin actions, ship them off-host,
    and alert on anomalies. Never log secrets or full document bodies/PII.
13. **Field-name hardening (NoSQL edge).** Constrain document field names and the
    search `key` param to disallow names starting with `$` or containing `.`, and
    constrain database/collection/id path segments to a sane charset + length, to
    avoid odd/abusive Mongo identifiers.
14. **Dependency hygiene.** Pin and scan dependencies (`pip-audit`, Dependabot),
    and keep Flask/Werkzeug/pymongo patched.
15. **Search/suggest cost controls.** Search scans collections and `/suggest`
    iterates every readable namespace; at scale this is a resource-exhaustion
    vector. Add indexes, hard result/time limits, and consider debouncing.
16. **Password policy & recovery.** *(partial — done: a NIST 800-63B length +
    common-password policy is enforced, plus admin reset and forced first-login
    change; see "Authentication" above.)* Still to consider: a **breached-password
    check** (HIBP k-anonymity), **self-service** password change for any logged-in
    user (currently only forced-on-first-login and admin reset), and an
    unauthenticated **password reset**. If you add reset, make it a **tokenised,
    expiring, single-use** email flow — sketch: a `_auth.reset_tokens` collection
    holding hashed tokens; an enumeration-safe `/forgot-password`; a
    `/reset-password?token=…` that verifies the token and reuses the strength
    validator; an injected SMTP/email-sender seam (kept out of the current build to
    avoid an email dependency).
17. **Backups & disaster recovery.** Back up the Mongo data volume and test
    restores; the embedded version history is not a backup.
18. **Keep debug off & errors generic.** Ensure Flask debug mode stays disabled
    in production (it is under gunicorn) so stack traces are never exposed.
19. **Admin-bootstrap race.** On a fresh deployment the first registrant becomes
    admin — register the intended admin immediately after deploy (or pre-provision
    one) so an attacker can't claim it.

---

## Reporting a vulnerability

This is a personal/self-hosted project. If you find a security issue, please open
a private report to the repository owner rather than a public issue.
