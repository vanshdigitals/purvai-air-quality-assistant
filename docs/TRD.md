# Technical Requirements (owner of constraints and external services)

## Stack
| Layer | Choice | Why |
|---|---|---|
| UI | React 19.3.1 + TypeScript 6.0.3 strict + Vite 8.4.0 | Mature; Node at build time only |
| Routing | React Router 8.5.3 (library mode) | Client routing for the SPA shell |
| Styling | Tailwind 4.3.5 (`@tailwindcss/vite` 4.3.5) + CSS-variable tokens + `@fontsource-variable/{instrument-sans,geist}` 5.3.0 | [Design system](design/PURVAI_DESIGN_SYSTEM.md); self-hosted fonts for strict `'self'` CSP |
| Data | TanStack Query 5.108.4 | Cache, retry, stale states |
| Charts / icons | Recharts 3.11.1 / Lucide React 1.81.0 | SVG, open-source; Recharts lazy-loaded |
| API | FastAPI 0.165.0, Uvicorn 0.54.0, Pydantic 2.14.4, pydantic-settings 2.16.3, httpx 0.29.0, google-genai 3.6.1 | Typed validation, OpenAPI, 10 s provider HTTP, Gemini structured output |
| ORM | SQLModel 0.0.50 on SQLAlchemy 2.1.9 | Pydantic-native; Core when needed |
| Migrations | Alembic 1.20.1, `render_as_batch=True` | SQLite ALTER limits |
| Rate limit | slowapi 0.1.10 | One instance is enough |
| PDF | fpdf2 2.8.2 (LGPL-3.0) | No system deps; ReportLab backup; WeasyPrint rejected |
| Tests | pytest 9.2.0, respx 0.23.1, freezegun 1.5.5, Vitest 5.1.2, RTL 16.3.3, Playwright 1.65.1, `@axe-core/playwright` 4.14.1 | [TESTING.md](TESTING.md) |

Next.js rejected (second Node server). Phase 1 versions pinned (A-04); Recharts and fpdf2 deferred to Phases 3 and 5.

## Constraints
TC-01 zero budget. TC-02 no Supabase, Firebase or paid DB. TC-03 no auth in MVP. TC-04 one container, one process, max one instance. TC-05 single branch, repo under 10 MB (unverified rule, followed).

## Runtime and performance
Python 3.12, uvicorn one worker, SQLite at `DATABASE_PATH`, config via pydantic-settings (`.env` locally, Secret Manager on Cloud Run). Settings include `CPCB_TIMEOUT_S` (default `20`, range `5` to `60`), `AI_TIMEOUT_S` (default `15`, range `5` to `30`), `AI_MODEL` (default `gemini-3.5-flash-lite`, verified present in `google-genai` `models.list()` alongside `gemini-3.1-flash-lite`), `AI_FALLBACK_MODEL` (`openai/gpt-oss-20b`; `400` treated as provider failure), and `PURVAI_FAKE_PROVIDERS` (`false` default; local test-only fixture seam, refused in demo mode), and `CO2_ESTIMATES_ENABLED` (`true` default). PERF-01 cached `/air` p95 under 300 ms. PERF-02 AI timeout 15 s, one fallback, then template. PERF-03 JS under 250 KB gzipped. PERF-04 air cache 30 min.

## External services
| Service | Purpose | Status | Key | Limits | Terms | Fallback |
|---|---|---|---|---|---|---|
| CPCB via data.gov.in (3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69) | Measured AQI, hourly | Free with limits | Free key; sample key 10 rows | Not published | GODL-India; credit CPCB, data.gov.in | Open-Meteo |
| Open-Meteo Air Quality (CAMS) | Modelled current, forecast | Free non-commercial | None | Under 10,000/day, 5,000/h, 600/min | CC BY 4.0; commercial needs plan | Cache |
| Open-Meteo Forecast, Geocoding | Wind, place search | Same | None | Same pool | CC BY 4.0 | Manual lat/lon |
| Gemini API | AI wording | Free with limits | AI Studio key | Per project, "not guaranteed", reset midnight Pacific | Unpaid data may be human-reviewed | Groq |
| Groq | AI fallback | Free with limits | No card | 30 RPM, 1K RPD, 8K TPM, 200K TPD per organisation (Groq Rate Limits page; exact values on the console limits page) | Check console | Templates |
| Cloud Run | Demo host | Free tier in billing account | Billing required | 180,000 vCPU-s, 360,000 GiB-s, 2M requests/month per billing account | Pay beyond | Render |
| OpenAQ v3 | History, post-MVP | Free with limits | Free key | 60/min, 2,000/h (baseline) | Per source | none |

Rejected: WAQI (no caching or redistribution), Google Air Quality API (billing; stretch), maps (list plus distance suffices), notifications (out of scope). Time: server clock, UTC stored, IST shown.

## AI providers (25 Nov 2026)
| Provider | Limits | Structured output | Free-data training | Decision |
|---|---|---|---|---|
| Gemini | Per project; third-party AI Studio readings (Oct 2026): Flash-Lite 15 RPM / 500 RPD, Pro 0 | JSON Schema subset | Yes, human review | Primary |
| Groq | As above | Strict `json_schema` on gpt-oss-20b/120b | Check console | Fallback |
| OpenRouter `:free` | 20 RPM; 50 RPD, 1,000 after USD 10 lifetime purchase; failed attempts count (OpenRouter pricing FAQ) | Model-dependent | Varies | Rejected |
| Cloudflare, Mistral, Cerebras, GitHub Models | Not evaluated | Unknown | Unknown | Not used |

## Hosting
| Host | Free type | Persistent SQLite | Sleep | Verdict |
|---|---|---|---|---|
| Cloud Run | Permanent tier, billing required | No: in-memory FS; FUSE and NFS lack locking | Scale to zero | Demo (temporary) |
| Render | Permanent free web service | No: ephemeral; disks paid (USD 0.25/GB), not on free | Spins down after 15 consecutive idle minutes; about a minute to spin back up (Render FAQ) | Backup host |
| Railway | USD 5 trial for 30 days, then USD 1/month credit (secondary) | Paid volumes | n/a | Rejected |
| Fly.io | Conflict: docs (5 Nov) no free tier; 23 Nov post announced USD 5/month Free plan (secondary) | Volumes | n/a | Re-check later |
| HF Spaces | Docker Spaces need a paid plan | No: 50 GB non-persistent | 48 h | Rejected |
| Oracle Always Free | Permanent | Yes: 200 GB block | Idle VMs reclaimable | Post-MVP option |

## Sources (accessed 25 Nov 2026)
Verified: ai.google.dev/gemini-api/docs/rate-limits; ai.google.dev/gemini-api/terms; ai.google.dev/gemini-api/docs/structured-output; console.groq.com/docs/structured-outputs; console.groq.com/docs/rate-limits (Free Plan table via indexed snippet); openrouter.ai/pricing (FAQ); cloud.google.com/run/pricing; Cloud Run Cloud Storage volume docs; render.com/docs/faq; huggingface.co/docs/hub/spaces-gpus; docs.oracle.com FreeTier resourceref; open-meteo.com/en/pricing; data.gov.in AQI catalogue; caqm.nic.in; ITF/OECD LCA India 2023, India GHG Program 2015, CEA CO2 Baseline v22.0 (via subagent). Partially verified: PromptWars rules (Hack2skill pages and posts).
