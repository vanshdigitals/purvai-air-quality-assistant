# HTTP API (owner of contracts)

Base `http://localhost:8000/api/v1` or `https://<service>.run.app/api/v1`. JSON UTF-8, ISO 8601 UTC, snake_case. Breaking changes create `/v2`. Demo mode needs header `X-Purvai-Household: <uuid>`; local ignores it.

## Errors
```json
{"error":{"code":"VALIDATION_ERROR","message":"lat must be between -90 and 90","request_id":"r-7f3a"}}
```
200/201/204 OK, created, deleted. 400 bad input (`HOUSEHOLD_HEADER_REQUIRED` when demo header missing/invalid). 413 body over 64 KB (import 5 MB). 422 schema/region error (`UNSUPPORTED_REGION`). 404 not found (`NOT_FOUND`, `HOUSEHOLD_NOT_FOUND`). 409 conflict / precondition (`HOUSEHOLD_REQUIRED`, import version conflict). 429 (`RATE_LIMIT_EXCEEDED`) with `Retry-After`. 502 provider failed, no cache (`PROVIDER_UNAVAILABLE`). 503 feature disabled in this mode. No stack traces.

## Endpoints
| Method and path | Purpose | Req |
|---|---|---|
| GET /health | Liveness, mode, DB status | Phase 1 |
| GET /air?lat&lon | Current AQI | FR-02 |
| GET /air/forecast?lat&lon&hours=12 | Forecast | FR-07 |
| GET /air/history?location_id&days=7 | History | FR-12 |
| GET /locations/search?q | Geocoding proxy | FR-01 |
| GET, PUT /household | Members, location, settings | FR-01 |
| POST /plan | Today's or tomorrow's plan | FR-06 |
| POST /chat; GET, DELETE /conversations | Ask Purvai; read or delete history | FR-08, FR-17 |
| POST /home-air/calc; GET /home-air/tips | ACH and indoor tips | FR-09 |
| GET, POST /activities; DELETE /activities/{id} | Activity log | FR-11 |
| GET /impact/summary?days=7 | Totals | FR-11 |
| POST /reports/pdf, /reports/csv | Files | FR-13 |
| GET /data/export; POST /data/import?dry_run= | JSON | FR-14 |
| POST /db/backup, /db/restore; GET /db/backups | Local only, else 503 | FR-15 |
| DELETE /data | Body `{"confirm":"DELETE"}` | FR-16 |

### GET /health
```json
{
  "status": "ok",
  "app": "purvai",
  "version": "0.1.0",
  "mode": "local",
  "ai_available": false,
  "database": { "status": "ok", "storage": "persistent", "schema_revision": "0002_location_admin" },
  "time": "2026-11-27T10:00:00Z"
}
```
Returns `503` with `"status": "degraded"` and `"database": {"status": "error", ...}` if the database integrity check fails.

### GET /air
Query: `lat` (-90 to 90), `lon` (-180 to 180), both required. Locations outside India's extent (lat 6 to 38, lon 68 to 98) return `422` with `code: "UNSUPPORTED_REGION"`. Returns `502` (`PROVIDER_UNAVAILABLE`) if both providers fail with no cache, or `429` (`RATE_LIMIT_EXCEEDED`) on rate limit.

```json
{
  "aqi": 312,
  "aqi_is_floor": false,
  "category": "very_poor",
  "scale": "CPCB_NAQI",
  "source_label": "Measured",
  "source": { "provider": "CPCB", "station": "Sector-62, Noida", "distance_km": 3.1 },
  "observed_at": "2026-11-25T03:30:00Z",
  "age_minutes": 40,
  "stale": false,
  "indicative": true,
  "served_from_cache": false,
  "dominant_pollutant": "pm25",
  "pollutants": { "pm25": { "value": 135, "unit": "µg/m³", "sub_index": 312 } },
  "verdict": {
    "level": "very_poor",
    "household_level": "severe",
    "headline": "Stay indoors today. Run the purifier.",
    "action_ids": ["stay_indoors", "purifier_on", "n95_if_out"],
    "actions": [
      { "action_id": "stay_indoors", "text": "Stay indoors today.", "tag": "rule" },
      { "action_id": "purifier_on", "text": "Run the purifier.", "tag": "rule" },
      { "action_id": "n95_if_out", "text": "Wear a well-fitted N95 if you go out.", "tag": "rule" }
    ]
  },
  "grap": { "stage": "II", "order_date": "2026-11-02", "source_url": "https://caqm.nic.in/" },
  "attribution": ["CPCB", "data.gov.in"]
}
```
Modelled fallback returns `source: {"provider":"Open-Meteo (CAMS)","station":null,"distance_km":null}`, `grap: null`, and `attribution: ["Open-Meteo","CAMS"]`.

### GET /air/forecast
Query: `lat`, `lon` (required, India extent else 422 `UNSUPPORTED_REGION`), `hours` (`1..48`, default `12`). Proxies Open-Meteo Air Quality hourly forecast, caches 48 hours for 30 min in `aqi_observation`, computes CPCB NAQI per hour, and returns `scale: "CPCB_NAQI"`, `source_label: "Modelled"`, `indicative: true`, `attribution: ["Open-Meteo","CAMS"]`, `generated_at`, `hours: [{time, aqi, aqi_is_floor, category, dominant_pollutant}]`, and `lowest: {time, aqi, category}`.

### GET /locations/search
Query: `q` (`2..60` chars). Proxies Open-Meteo Geocoding filtered to `IN`, cached in memory for 24 h (rate limited `30/min` per IP). Returns list of `{label, lat, lon, city, admin1, admin2, nearest_station_km}` (`nearest_station_km` computed from cached CPCB stations within 2 h when available, else `null`).

### GET, PUT /household
In `local` mode returns/upserts the single household (`404 HOUSEHOLD_NOT_FOUND` on `GET` before onboarding). In `demo` mode requires valid UUIDv4 `X-Purvai-Household` header (`400 HOUSEHOLD_HEADER_REQUIRED` if missing/invalid). Validates `members` (sum >= 1, unique kinds), `location` (India bounds else `422 UNSUPPORTED_REGION`), and `settings` (`theme`, `commute_mode`, `ai_enabled`, `save_chat`, `reduce_motion`).

### POST /plan
Body `{"day":"today"|"tomorrow","rebuild":false}`. Requires an existing household (`409 HOUSEHOLD_REQUIRED` if not onboarded). Computes 4 IST periods (`morning`, `afternoon`, `evening`, `night`) using worst-hour AQI and persists `daily_plan` (`generated_by`: `rules` | `gemini` | `groq` | `template`) + `plan_item` rows (`tag`: `rule` | `ai_wording`). Reuses stored plans under 30 min when period levels/action IDs match unless `rebuild: true`. Response: `{plan_date, day, generated_by, generated_at, source_label, summary, note, periods: [{period, start, end, level, aqi, past, items: [{action_id, text, why, tag}]}]}`.

### POST /home-air/calc and GET /home-air/tips
`POST /home-air/calc` validates `{length_m, width_m, height_m, cadr_m3h}` and returns `{volume_m3, ach, target_ach: 5, meets_target, cadr_needed_m3h}`. `GET /home-air/tips?lat&lon` returns `{level, generated_by, tips: [{tip_id, text, tag}], ventilation_hour}` where `ventilation_hour` is an ISO 8601 UTC timestamp (`| null`) for the cleanest forecast hour between `08:00` and `20:00` IST.

### POST /chat and GET, DELETE /conversations
- `POST /chat`: body `{"message": str}` (1 to 500 chars trimmed, `extra="forbid"`). Requires an existing household (`409 HOUSEHOLD_REQUIRED`). Rate limit `20/min` per IP (`429 RATE_LIMIT_EXCEEDED` with `Retry-After`). Response includes [ChatReply](AI_SCHEMAS.md#schemas-v10) plus `generated_by` (`gemini` | `groq` | `template`), `note`, `aqi`, `category`, `source_label`, `observed_at`, `age_minutes`, `stale`, and `grap_stage`. Writes 0 DB rows unless `settings.save_chat` is `true`.
- `GET /conversations`: returns `{messages: [{id, role, text, generated_by, created_at}]}` (last 50 messages for the household, oldest first; `409 HOUSEHOLD_REQUIRED` if not onboarded).
- `DELETE /conversations`: deletes all saved conversations and messages for the household and returns `204`.
### POST /activities
```json
{"kind":"trip","mode":"metro","distance_km":12.5,"replaced_mode":"car_petrol","occurred_at":"2026-11-25T02:30:00Z"}
```
201 with `co2_saved_g` (Estimated, `ITF-2023`) or `null` while A-02 is pending.
### POST /data/import
Body `{"schema":1,"exported_at":...,"household":{...},"activities":[...]}`. `dry_run=true` returns counts. Unknown schema returns 409.

## Rate limits and boundaries
slowapi per IP: geocoding `/locations/search` 30/min, AI 20/min, reports 10/min, others 120/min. The browser never calls external APIs or sees keys. Only `providers/` and `ai/` call out, with timeouts and validation.
