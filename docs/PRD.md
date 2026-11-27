# Product Requirements (owner of product scope)

Vision: every family in a polluted city knows what to do about the air today. Mission: turn official air data into safe, explained actions at zero cost.

## Personas
| Persona | Context | Need |
|---|---|---|
| Meera, 36, Noida parent | Child aged 7 | When to go out, windows, purifier |
| Mr. Sharma, 68, Prayagraj | COPD | Early warnings, simple words |
| Ravi, 27, Delhi rider | Works outdoors | Mask and break guidance |

Goals: G1 action within 10 s of opening. G2 transparent sources. G3 working PromptWars demo. Non-goals: diagnosis, login, sync, Hindi UI, push alerts, PWA install, own forecasting.

## Functional requirements
| ID | Requirement | Pri | Acceptance |
|---|---|---|---|
| FR-01 | Onboarding: location, household flags, commute | Must | Under 60 s; skippable after location |
| FR-02 | AQI from nearest CPCB station within 10 km, else Open-Meteo "Modelled" | Must | Label, station, distance, time always shown |
| FR-03 | Stale banner over 2 h | Must | Appears at 2 h 1 min |
| FR-04 | Deterministic household verdict ([rules](ARCHITECTURE.md#rules-engine)) | Must | Matrix tests 100% |
| FR-05 | GRAP banner from manual config | Must | Stage plus CAQM order date; never inferred |
| FR-06 | Daily plan, 4 periods | Must | Items tagged Rule or AI wording; works with AI off |
| FR-07 | 12-hour forecast (Modelled) | Should | Chart plus table |
| FR-08 | Ask Purvai chat | Must | Cites data; 500 chars; cannot change verdict |
| FR-09 | Home Air ACH = CADR / volume, target 5 | Must | Matches worked examples |
| FR-10 | Travel comparison | Should | CO2 "Estimated" (A-02) |
| FR-11 | Activity log and totals | Must | CRUD; totals match factors |
| FR-12 | 7-day history | Should | From stored observations |
| FR-13 | PDF and CSV reports | Must | Opens; matches screen |
| FR-14 | JSON export/import with preview | Must | Round trip identical |
| FR-15 | DB backup/restore (local) | Must | Passes `integrity_check` |
| FR-16 | Clear all data | Must | Type "DELETE" |
| FR-17 | Chat history toggle, off by default | Must | Off stores nothing |
| FR-18 | Demo banner | Must | "Demo data resets. Export to keep it." |

## Non-functional
NFR-01 LCP under 2.5 s on mid-range 4G phone. NFR-02 WCAG 2.2 AA. NFR-03 core works without AI or network (cache). NFR-04 zero mandatory cost. NFR-05 no personal data in prompts. NFR-06 repo under 10 MB.

## User stories
Meera sees "Keep the school run short; mask for your child" before 8 am. Mr. Sharma is told to stay indoors one level earlier. Ravi gets mask and break guidance from Poor.

## Success metrics
Verdict in 10 s or less; zero contradictions in AI safety tests; 80% coverage on aqi, rules, impact; zero serious axe issues; demo up during judging.

## Challenge alignment
Low-emission routines: FR-06, FR-10. Indoor hacks: FR-09. Sustainable alternatives: FR-10. Location and lifestyle: FR-01, FR-02, FR-04. Direct impact: FR-08, FR-11.

## Development phases (authoritative)
| Phase | Scope | Needs | Done when | Docs |
|---|---|---|---|---|
| 0 | These 14 files | none | A-01 to A-06 recorded | all |
| 1 | Repo, React shell, FastAPI, SQLite + Alembic, themes, `/health` | 0 | `/health` green in CI | [TRD](TRD.md), [DATABASE](DATABASE.md) |
| 2 | CPCB, Open-Meteo, AQI maths, verdict | 1 | AQI and rules tests pass | [ARCHITECTURE](ARCHITECTURE.md) |
| 3 | Today, Plan, Home Air, locations | 2 | FR-01 to FR-07, FR-09 | [UX_FLOWS](UX_FLOWS.md) |
| 4 | Gemini, Groq, schemas, chat, guard | 3 | AI safety suite passes | [AI_SCHEMAS](AI_SCHEMAS.md), [AI_SAFETY](AI_SAFETY.md) |
| 5 | Activities, CO2, PDF, CSV, JSON, backup | 3 | FR-10 to FR-16 | [API](API.md) |
| 6 | a11y, security, performance | 4, 5 | Checklist green | [TESTING](TESTING.md), [SECURITY](SECURITY.md) |
| 7 | Cloud Run demo, blog, submission | 6 | Submitted by 28 Nov | [ARCHITECTURE](ARCHITECTURE.md#deployment) |

Roadmap: family profiles, Hindi UI (needs Devanagari font, P-03), alerts, optional auth, desktop package, OpenAQ history.

## Decisions and approvals (research, 25 November 2026)
Source: Purvai Documentation Set v1.0 research. A-01 to A-06 below are the approvals referenced across all documents.

Purvai should run as one FastAPI + SQLite application in two modes: a persistent local mode on the user's machine, and a hosted Cloud Run demo whose SQLite data is temporary and clearly labelled, with Gemini as primary AI and Groq gpt-oss-20b as fallback.

### TL;DR
- Cloud Run cannot hold a persistent SQLite file safely: its Cloud Storage FUSE volume has no file locking, and Render's free filesystem is ephemeral. Persistent SQLite lives in local mode only. The hosted demo is temporary and offers JSON export.
- AI: Gemini Flash-Lite free tier with `response_json_schema`, fallback Groq `openai/gpt-oss-20b` in strict JSON-schema mode, then deterministic templates. The rules engine alone sets the verdict.
- Challenge facts changed: deadline 29 November 2026 (partially verified), Google Antigravity is required, and Delhi-NCR is at GRAP Stage II (effective 2 Nov 2026) after Stage III from 6 to 17 Nov.

### Decisions and changes

| ID | Existing decision | Problem | Evidence | Replacement | Impact |
|---|---|---|---|---|---|
| D-01 | User data in IndexedDB; server SQLite as cache | User now wants SQLite for all data | Google Cloud doc "Configure Cloud Storage volume mounts for Cloud Run services": "Cloud Storage FUSE does not provide concurrency control for multiple writes (file locking) to the same file. When multiple writes try to replace a file, the last write wins and all previous writes are lost."; "Cloud Run does not support NFS locking"; Render free filesystem is ephemeral | One SQLite schema scoped by `household_id`. Local: persistent file. Demo: per-browser household in temporary SQLite, wiped on restart and after 24 h | idb-keyval removed; CRUD, backup, restore endpoints; Alembic in MVP |
| D-02 | Deadline about 28 Nov | Date differs | Hack2skill post: "Submission Deadline: November 29, 2026"; 3 attempts | Submit 28 Nov, hard stop 29 Nov | Phase 7 |
| D-03 | Antigravity unknown | Rule exists | Hack2skill page: "using Google Antigravity is a requirement for all submissions" | Build inside Antigravity | Workflow |
| D-04 | GRAP Stage II from 2 Nov | Stage moved | CAQM: Stage III invoked 06.11.2026, revoked 17.11.2026; "Current GRAP Stage: Stage II, Effective: 02 Nov 2026" | Config `stage: II, order_date: 2026-11-02`, re-checked on demo day | Config |
| D-05 | CO2 disabled | Factors found | ITF/OECD 2023 India life-cycle study; India GHG Program 2015 v1.0 | Enable CO2 as "Estimated" from ITF 2023 | Needs A-02 |
| D-06 | Gemini JSON output | Schema subset | Gemini docs list supported keywords; an SDK issue reports value constraints ignored | Flat schemas, Pydantic re-validation | AI_SCHEMAS |
| D-07 | Groq gpt-oss-20b | Limit conflict | Groq Rate Limits page (console.groq.com/docs/rate-limits, Free Plan table): "openai/gpt-oss-20b · 30 · 1K · 8K · 200K"; the 3 RPM / 2K TPM row there belongs to openai/gpt-oss-safeguard-20b, which likely explains the 6 Oct 2026 archive conflict | Keep; read console limits in Phase 4 | None if limits hold |
| D-08 | React 18 | Versions not re-verified | Search budget exhausted | Pin latest stable React, Vite, Tailwind in Phase 1 (A-04) | Minor |

**Approvals needed:** A-01 hybrid local plus temporary-demo architecture. A-02 CO2 estimates from ITF 2023. A-03 derived context only to Gemini's unpaid tier (human review allowed). A-04 library versions. A-05 P-01 chip colour #CF4040. A-06 brand and domain clearance.
