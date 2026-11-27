# Purvai
**Know the air. Act in time.** Purvai (Hindi purvāī, "the eastern breeze", poor-VAI) is an AI-powered urban air quality and personal safety assistant. It answers: "What should my family do right now to stay safer?"

## Vision and problem
Families in polluted Indian cities see AQI numbers, not decisions. Purvai turns official air data into a daily plan and shows what each choice changes. See [PRD.md](PRD.md).

## Features and differentiators
Live AQI with a source label (Measured, Modelled, Estimated), deterministic verdict, daily plan, Ask Purvai, Home Air, travel options, impact tracking, 7-day history, PDF/CSV/JSON reports, backup and restore. The rules engine, not the AI, decides the verdict ([AI_SAFETY.md](AI_SAFETY.md)). Official CPCB data first. No account, no paid services.

Screenshots: none yet; added after Phase 3.

## Stack and requirements
React 19 + TypeScript + Vite + Tailwind; FastAPI, Pydantic v2, SQLModel, Alembic on Python 3.12; SQLite; Gemini with Groq fallback; Recharts; fpdf2 ([TRD.md](TRD.md)). Needs Python 3.12, Node.js LTS, Git, 1 GB disk. Docker optional.

## Install and run
Bash (Linux / macOS):
```bash
git clone <repo-url> purvai && cd purvai
cp .env.example .env
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && alembic upgrade head   # optional: startup also runs migrations and creates data/purvai.db
uvicorn app.main:app --reload --port 8000
cd ../frontend && npm ci && npm run dev   # http://localhost:5173
```

PowerShell (Windows):
```powershell
git clone <repo-url> purvai; cd purvai
Copy-Item .env.example .env
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend; alembic upgrade head   # optional: startup also runs migrations and creates data\purvai.db
uvicorn app.main:app --reload --port 8000
cd ..\frontend; npm ci; npm run dev   # http://localhost:5173
```

## Environment configuration
| Variable | Required | Example |
|---|---|---|
| PURVAI_MODE | yes | local or demo |
| DATABASE_PATH | no | empty (defaults to `<repo>/data/purvai.db` in local, `<temp>/purvai.db` in demo; relative paths resolve from repo root) |
| DATA_GOV_IN_API_KEY | no (Phase 2) | free key |
| CPCB_TIMEOUT_S | no | 20 |
| PURVAI_FAKE_PROVIDERS | no | false (test-only in local mode; refused in demo) |
| AI_PROVIDER / AI_MODEL | no | gemini / gemini-3.5-flash-lite |
| AI_FALLBACK_PROVIDER / AI_FALLBACK_MODEL | no | groq / openai/gpt-oss-20b |
| AI_TIMEOUT_S | no | 15 (5 to 30) |
| GEMINI_API_KEY, GROQ_API_KEY | no | AI off without them |
| CORS_DEV_ORIGIN | no | http://localhost:5173 |
| LOG_LEVEL | no | INFO |

## Build, test, reports, data
`npm run build` (FastAPI serves `frontend/dist` on port 8000). Tests: `pytest`, `npm test`, `npm run test:e2e` ([TESTING.md](TESTING.md)). Reports: Reports & Data, 1 or 7 days, PDF or CSV ([API.md](API.md)). Backup (local): writes `data/backups/purvai-YYYYMMDD-HHMM.db`. JSON export and import with preview in any mode.

## Structure
```
backend/app/{api,aqi,providers,rules,db}/  backend/app/{config.py,main.py}  backend/alembic/  backend/tests/
config/grap.json  frontend/src/{app,components,features,lib,styles}/  frontend/tests/  frontend/e2e/  data/ (gitignored)
```

## Status and limitations
Phase 4 complete; Gemini + Groq + deterministic template gateway, SAF-01..05 guard, Ask Purvai (`/ask`, `POST /chat`, `GET`/`DELETE /conversations`), Plan/Home Air AI wording, and Settings AI & Save Chat toggles ready. Demo data resets. Free AI limits are account-specific and not guaranteed. Open-Meteo free use is non-commercial. No Hindi UI. CPCB colour codes unverified.

## Documentation research report (25 November 2026)
1. **Structure:** `purvai/` with 13 root files plus `design/PURVAI_DESIGN_SYSTEM.md`, exactly 14.
2. **Summary:** README entry and setup; PRD FR-01 to FR-18 and phases; TRD stack, services, hosting, sources; ARCHITECTURE modes, pipelines, AQI tables, rules; API contracts; AI_SCHEMAS JSON contracts; AI_SAFETY guard; SECURITY controls; DATABASE 13 tables, PRAGMAs, backup; UX_FLOWS journeys; ACCESSIBILITY A11Y-01 to 15; TESTING layers and checklist; CONTRIBUTING workflow; design system v1.1 unchanged.
3. **Technology:** React, TypeScript, Vite, Tailwind; FastAPI, Pydantic v2, SQLModel, Alembic batch, slowapi; SQLite; fpdf2; Recharts; pytest, Vitest, Playwright, axe-core.
4. **AI and data:** Gemini primary, Groq gpt-oss-20b strict fallback, templates last. CPCB via data.gov.in (Measured) first; Open-Meteo CAMS (Modelled) fallback and forecast; Open-Meteo geocoding. No maps, no notifications.
5. **Database:** SQLite for everything, scoped by household; persistent locally; temporary and labelled on Cloud Run because FUSE and NFS lack locking.
6. **Authentication:** deferred; `household_id` scoping keeps the path open.
7. **Unresolved:** A-01 to A-06; Gemini model ID and project limits; Groq limit conflict; official judging criteria, repo and hosting rules; CPCB colour codes; gas breakpoints; BIS IS 9473 marking; Fly.io and Oracle A1 conflicts.
8. **Limitations:** search budget ended before SQLite docs, Nominatim, OpenAQ, library versions and other free AI providers were re-checked. Some quotas come from secondary sources. Hack2skill pages render by script and could not be read in full.
9. **Order:** approvals, then Phases 1 to 7, submitting by 28 Nov 2026, one day before the 29 Nov deadline.
