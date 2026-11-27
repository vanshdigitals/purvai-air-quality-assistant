# Security (owner of controls)

Least data, least privilege, fail closed, no secrets in the client. Authentication is not implemented.

## Threats and controls
| Threat | Control |
|---|---|
| Key leakage | Server-side keys; `.env` gitignored; `.env.example`; Secret Manager; gitleaks |
| AI quota abuse | slowapi; 500 chars; one instance |
| Prompt injection | [AI_SAFETY.md](AI_SAFETY.md#prompt-injection) |
| Demo cross-visitor exposure | Random UUIDv4 token; every query filtered by `household_id`; 24 h purge; banner says demo is not private storage |
| Malicious import | 5 MB, JSON only, schema check, record caps, no paths from content |
| Path traversal | Server-generated backup names, resolved inside `data/backups/` |
| SQL injection | ORM and bound parameters only |
| XSS | React escaping; no `dangerouslySetInnerHTML`; AI text as text |

## Validation, CORS, headers
Pydantic `extra="forbid"`, ranges, lengths; streaming chunked body limit 64 KB (5 MB on `POST /data/import`); outputs validated. Same-origin in production; dev allows `http://localhost:5173`. `TRUST_PROXY_HEADERS` (default `false`) enables `X-Forwarded-For` first-IP rate limiting behind Cloud Run / Render. Headers: CSP `default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, HSTS (hosted/demo), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(self)`.

## Data at rest and exports
DB file mode 0600 where supported, under `data/`, not encrypted (full-disk encryption advised). Backups stay local. Exports are built in memory with `Content-Disposition: attachment`. CSV cells starting with `= + - @` get a `'` prefix.

## Logging and dependencies
JSON logs to stdout. Never log prompts, chat, household flags, coordinates beyond 2 decimals or keys. Errors carry `request_id`. Pinned lockfiles, `pip-audit`, `npm audit`, `.github/dependabot.yml` (pip, npm, github-actions weekly).

## Privacy
No accounts, analytics or third-party scripts. Location rounded before caching.

## Future authentication
OIDC or passkeys via a vetted library, HttpOnly SameSite cookies, CSRF tokens, user-to-household mapping, per-user limits, audit log. MVP code must not assume a logged-in user.
