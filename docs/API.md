# HTTP API (owner of contracts)

Base `http://localhost:8000/api/v1` or `https://<service>.run.app/api/v1`. JSON UTF-8, ISO 8601 UTC, snake_case. Breaking changes create `/v2`. Demo mode needs header `X-Purvai-Household: <uuid>`; local ignores it.

## Errors
```json
{"error":{"code":"VALIDATION_ERROR","message":"lat must be between -90 and 90","request_id":"r-7f3a"}}
```
200/201/204 OK, created, deleted. 400 bad input. 413 body over 64 KB (import 5 MB). 422 schema error. 404 not found. 409 import version conflict. 429 with `Retry-After`. 502 provider failed, no cache. 503 feature disabled in this mode. No stack traces.

## Endpoints
| Method and path | Purpose | Req |
|---|---|---|
| GET /health | Liveness, mode, DB status | Phase 1 |
| GET /air?lat&lon | Current AQI | FR-02 |
| GET /air/forecast?lat&lon&hours=12 | Forecast | FR-07 |
| GET /air/history?location_id&days=7 | History | FR-12 |
| GET /locations/search?q | Geocoding proxy | FR-01 |
| GET, PUT /household | Members, location, settings | FR-01 |
| POST /plan | Today's plan | FR-06 |
| POST /chat; DELETE /conversations | Ask Purvai; delete history | FR-08, FR-17 |
| POST /home-air/calc | ACH | FR-09 |
| GET, POST /activities; DELETE /activities/{id} | Activity log | FR-11 |
| GET /impact/summary?days=7 | Totals | FR-11 |
| POST /reports/pdf, /reports/csv | Files | FR-13 |
| GET /data/export; POST /data/import?dry_run= | JSON | FR-14 |
| POST /db/backup, /db/restore | Local only, else 503 | FR-15 |
| DELETE /data | Body `{"confirm":"DELETE"}` | FR-16 |

### GET /health
```json
{
  "status": "ok",
  "app": "purvai",
  "version": "0.1.0",
  "mode": "local",
  "database": { "status": "ok", "storage": "persistent", "schema_revision": "0001_initial_schema" },
  "time": "2026-11-27T10:00:00Z"
}
```
Returns `503` with `"status": "degraded"` and `"database": {"status": "error", ...}` if the database integrity check fails.

### GET /air
```json
{"aqi":312,"category":"very_poor","scale":"CPCB_NAQI","source_label":"Measured",
 "source":{"provider":"CPCB","station":"Sector-62, Noida","distance_km":3.1},
 "observed_at":"2026-11-25T03:30:00Z","stale":false,"indicative":true,
 "pollutants":{"pm25":{"value":168,"unit":"µg/m³","sub_index":336}},
 "verdict":{"level":"very_poor","household_level":"severe","headline":"Stay indoors today. Run the purifier."},
 "grap":{"stage":"II","order_date":"2026-11-02"},"attribution":["CPCB","data.gov.in"]}
```
### POST /chat
Request `{"message":"Can my son play outside at 5 pm?"}` (1 to 500 chars). Response: [ChatReply](AI_SCHEMAS.md#chatreply) plus `generated_by` (gemini, groq or template).
### POST /activities
```json
{"kind":"trip","mode":"metro","distance_km":12.5,"replaced_mode":"car_petrol","occurred_at":"2026-11-25T02:30:00Z"}
```
201 with `co2_saved_g` (Estimated, `ITF-2023`) or `null` while A-02 is pending.
### POST /data/import
Body `{"schema":1,"exported_at":...,"household":{...},"activities":[...]}`. `dry_run=true` returns counts. Unknown schema returns 409.

## Rate limits and boundaries
slowapi per IP: AI 20/min, reports 10/min, others 120/min. The browser never calls external APIs or sees keys. Only `providers/` and `ai/` call out, with timeouts and validation.
