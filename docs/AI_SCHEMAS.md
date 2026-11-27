# AI Data Contracts (owner of structured AI I/O)

## Interface
```python
class LLMProvider(Protocol):
    name: str
    async def generate(self, system: str, context: AIContext, user: str | None,
                       schema: type[BaseModel], timeout_s: float = 15) -> StructuredReply: ...
```
`GeminiProvider`: `google-genai==3.6.1`, `types.GenerateContentConfig(system_instruction=..., temperature=0.2, response_mime_type="application/json", response_json_schema=build_provider_json_schema(Model))` (verified `AI_MODEL` default: `gemini-3.5-flash-lite`; `GEMINI_API_KEY` absent locally so live `models.list` check deferred). `GroqProvider`: OpenAI-compatible `https://api.groq.com/openai/v1/chat/completions`, `response_format={"type":"json_schema","json_schema":{"name":...,"strict":true,"schema":...}}` with `openai/gpt-oss-20b` (`400` treated as provider failure). `StructuredReply` = `{data, provider, model, latency_ms}`.

## Compatibility rules
Gemini supports a subset: `$ref`, `$defs`, `anyOf`, `properties`, `additionalProperties`, `required`, `minimum`, `maximum`; value constraints may be ignored. Groq strict needs all fields required and `additionalProperties:false`. So: S-1 max 2 levels. S-2 all fields required; optional means nullable. S-3 string enums. S-4 no `pattern` or `format`. S-5 Pydantic re-validates with `extra="forbid"` and lengths.

## Context
Context v1.1 (minor update for SAF-02 number/time/staleness grounding):
```json
{"schema_version":"1.1","aqi":312,"category":"very_poor","source_label":"Measured",
 "dominant_pollutant":"pm25","forecast_trend":"worsening","grap_stage":"II",
 "household":{"has_child":true,"has_older_adult":false,"has_heart_lung":false,"outdoor_worker":false},
 "verdict":{"level":"severe","action_ids":["stay_indoors","purifier_on","n95_if_out"]},
 "local_time":"08:10","city":"Noida",
 "stale":false,"age_minutes":40,"age_hours":0,"observed_time_ist":"07:30",
 "pollutants":{"pm25":{"value":135.0,"sub_index":312}},
 "forecast":[{"time_ist":"09:00","aqi":330,"category":"very_poor"}],
 "plan_periods":null}
```
No names, addresses, station names, counts, commute mode, past chat, or exact coordinates. User text sits in a separate `<user_input>` block (control chars stripped, capped at 500 chars).

## Schemas v1.0
- **Recommendation:** `{action_id: enum(catalogue), title: str<=60, why: str<=200, tag: enum[rule, ai_wording]}`
- **DailyPlanWording:** `{schema_version, verdict_level: enum[good,satisfactory,moderate,poor,very_poor,severe], summary: str<=160, periods: exactly 4 of {period: enum[morning,afternoon,evening,night], items: Recommendation[1..4]}}`
- **ChatReply:** `{schema_version, verdict_level, answer: str<=600, data_cited: enum[aqi,category,pollutant,forecast,grap,source][1..6], recommendations: Recommendation[0..3], needs_doctor_note: bool, out_of_scope: bool}`
- **IndoorAdvice:** `{schema_version, verdict_level, tips: {tip_id: enum, text: str<=160}[1..5], ach_explanation: str<=200 | null}`
- **ImpactExplanation:** `{schema_version, sentence: str<=200, basis: enum[ITF-2023-lifecycle], label: enum[Estimated]}`

## Valid ChatReply
```json
{"schema_version":"1.0","verdict_level":"severe","answer":"Not today. PM2.5 is very high at the Sector-62 station. Play indoors and keep windows closed.",
 "data_cited":["aqi","pollutant","source"],"recommendations":[{"action_id":"stay_indoors","title":"Play indoors","why":"Children breathe more air per kg of body weight.","tag":"ai_wording"}],
 "needs_doctor_note":false,"out_of_scope":false}
```
## Rejected
`verdict_level` differs from rules; `action_id` not in context; extra field `"aqi":150`; answer with "cures" or a dosage.

## Versioning
Semver `schema_version`: minor adds a nullable field, major changes meaning. Prompts and schemas live in `ai/schemas/v1/`.
