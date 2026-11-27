# Testing Strategy (owner of verification)

Test safety logic hardest. Never call real quota-limited APIs; mock all providers with recorded fixtures.

| Layer | Tool | Covers |
|---|---|---|
| AQI | pytest | Every breakpoint edge, interpolation, 3-pollutant and PM rules, units |
| Rules | pytest parametrised | 6 categories x member flags x outdoor worker; escalation; strictest member |
| Impact | pytest | Factor maths; null without factor |
| API | pytest + TestClient | All endpoints, error format, 413, 422, 429, demo scoping |
| Database | pytest, temp file | Migrations from empty, cascades, CHECKs, backup + integrity_check, restore, quick_check failure |
| AI schema | pytest | Valid fixtures pass; each rejected example fails |
| AI safety | pytest | Contradiction discarded, injection strings, banned claims, number grounding |
| Fallbacks | pytest + respx | Gemini timeout to Groq; both fail to template; CPCB down to Modelled; all down to cache |
| Import/export | pytest | Round trip, 5 MB, 409, CSV escaping |
| PDF | pytest | Starts `%PDF`, pages, AQI text |
| Frontend | Vitest + RTL | Verdict card, labels, form errors, theme |
| E2E | Playwright | Onboarding, Today, mocked chat, report, import |
| a11y | @axe-core/playwright | Zero serious |
| Security | pytest, gitleaks, pip-audit, npm audit | Headers, no traces, traversal blocked |

Fixtures in `backend/tests/fixtures/`: CPCB rows for Noida, Delhi, Prayagraj; Open-Meteo JSON; valid and invalid AI replies. freezegun for time.

CI (GitHub Actions, every push): ruff, mypy --strict, pytest + coverage, eslint, tsc, Vitest, build, Playwright + axe. No secrets needed. Coverage: 80% on `aqi/`, `rules/`, `impact/`; 70% backend; 100% verdict rows.

## Release checklist
- CI green, coverage met.
- One manual run with real keys in local mode.
- Demo banner live; `/health` shows `mode=demo`.
- GRAP config checked against caqm.nic.in on release day.
- Attribution visible: CPCB, data.gov.in, Open-Meteo/CAMS.
- Repo under 10 MB; no `.env` committed.
